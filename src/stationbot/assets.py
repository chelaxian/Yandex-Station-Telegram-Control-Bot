"""Private application assets and bounded, validated, transactional ZIP restores."""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import tempfile
import threading
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from .errors import InvalidInput

KINDS = {"sounds", "scripts", "firmware", "settings", "dialogs"}
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 256 * 1024 * 1024


def filename(name: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,95}", name):
        raise InvalidInput("Имя: 1–96 латинских букв, цифр, _, -, .; без путей")
    return name


class Assets:
    def __init__(self, root: Path):
        self.root = root / "assets"
        self.lock = threading.RLock()
        self.root.mkdir(mode=0o700, parents=True, exist_ok=True)

    def path(self, kind: str, name: str) -> Path:
        if kind not in KINDS:
            raise InvalidInput("Неизвестный тип файла")
        directory = self.root / kind
        if self.root.is_symlink() or directory.is_symlink():
            raise InvalidInput("Ссылки в хранилище запрещены")
        path = directory / filename(name)
        if path.is_symlink():
            raise InvalidInput("Ссылки в хранилище запрещены")
        return path

    def inventory(self, kind: str | None = None) -> list[dict]:
        with self.lock:
            return [{"kind": p.parent.name, "name": p.name, "bytes": p.stat().st_size}
                    for p in sorted(self.root.glob("*/*"))
                    if p.parent.name in KINDS and (kind is None or p.parent.name == kind)
                    and p.is_file() and not p.is_symlink() and not p.parent.is_symlink()]

    def put(self, kind: str, name: str, data: bytes, *, replace: bool = False) -> dict:
        if not data or len(data) > MAX_FILE:
            raise InvalidInput("Файл: 1 байт — 64 МиБ")
        with self.lock:
            path = self.path(kind, name)
            if path.exists() and not replace:
                raise InvalidInput("Файл уже существует; сначала удалите его")
            if sum(i["bytes"] for i in self.inventory()) + len(data) > MAX_TOTAL:
                raise InvalidInput("Квота файлов 256 МиБ исчерпана")
            path.parent.mkdir(mode=0o700, exist_ok=True)
            temporary = path.with_name(".pending-" + uuid.uuid4().hex)
            try:
                with temporary.open("xb") as stream:
                    os.chmod(temporary, 0o600)
                    stream.write(data)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
            return {"kind": kind, "name": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}

    def get(self, kind: str, name: str) -> bytes:
        with self.lock:
            path = self.path(kind, name)
            if not path.is_file() or path.stat().st_size > MAX_FILE:
                raise InvalidInput("Файл отсутствует или превышает лимит")
            return path.read_bytes()

    def delete(self, kind: str, name: str) -> None:
        with self.lock:
            self.path(kind, name).unlink(missing_ok=True)

    def backup(self) -> bytes:
        with self.lock:
            output, manifest = io.BytesIO(), {}
            with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
                for item in self.inventory():
                    data = self.get(item["kind"], item["name"])
                    name = f"{item['kind']}/{item['name']}"
                    archive.writestr(name, data)
                    manifest[name] = hashlib.sha256(data).hexdigest()
                archive.writestr("manifest.json", json.dumps({"format": 1, "files": manifest}))
            if output.tell() > MAX_TOTAL:
                raise InvalidInput("Архив превышает лимит")
            return output.getvalue()

    def restore(self, data: bytes) -> int:
        if len(data) > MAX_TOTAL:
            raise InvalidInput("Архив превышает лимит")
        with self.lock, tempfile.TemporaryDirectory(prefix="restore-", dir=self.root.parent) as temp:
            stage = Path(temp) / "assets"
            stage.mkdir(mode=0o700)
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as archive:
                    items = archive.infolist()
                    if len(items) > 512 or sum(i.file_size for i in items) > MAX_TOTAL:
                        raise InvalidInput("Слишком много файлов или распакованных данных")
                    names = [i.filename for i in items]
                    if len(names) != len(set(names)):
                        raise InvalidInput("Повторяющиеся имена в ZIP")
                    manifest = json.loads(archive.read("manifest.json"))
                    if manifest.get("format") != 1 or set(manifest["files"]) != set(names) - {"manifest.json"}:
                        raise InvalidInput("Некорректный манифест резервной копии")
                    for item in items:
                        if item.filename == "manifest.json":
                            continue
                        parts = PurePosixPath(item.filename).parts
                        if len(parts) != 2 or parts[0] not in KINDS or item.file_size > MAX_FILE:
                            raise InvalidInput("Недопустимый путь или размер файла в ZIP")
                        name = filename(parts[1])
                        if ((item.external_attr >> 16) & 0o170000) == 0o120000:
                            raise InvalidInput("Ссылки в ZIP запрещены")
                        body = archive.read(item)
                        if hashlib.sha256(body).hexdigest() != manifest["files"][item.filename]:
                            raise InvalidInput("SHA-256 файла не совпал")
                        path = stage / parts[0] / name
                        path.parent.mkdir(mode=0o700, exist_ok=True)
                        path.write_bytes(body)
                        os.chmod(path, 0o600)
            except (zipfile.BadZipFile, KeyError, ValueError, TypeError, OSError) as e:
                raise InvalidInput("Не удалось проверить резервную копию") from e
            previous = self.root.with_name("assets-previous-" + uuid.uuid4().hex)
            self.root.rename(previous)
            try:
                stage.rename(self.root)
            except BaseException:
                previous.rename(self.root)
                raise
            # Previous data is retained for rollback rather than silently destroyed.
            return len(items) - 1

    def cleanup(self) -> dict:
        # Only owned converter/restore leftovers; never guessed vendor cache paths.
        with self.lock:
            removed = 0
            for path in self.root.glob("*/.pending-*"):
                if path.is_file() and not path.is_symlink():
                    path.unlink()
                    removed += 1
            return {"temporary_files_removed": removed}

    @staticmethod
    def import_legacy(data: bytes) -> bytes:
        """Convert the exact 2.7 application-backup layout; never extract or run it."""
        output, manifest, seen = io.BytesIO(), {}, set()
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as old, zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as new:
                items = old.infolist()
                if len(data) > MAX_TOTAL or len(items) > 512 or sum(i.file_size for i in items) > MAX_TOTAL:
                    raise InvalidInput("Слишком большой архив")
                for item in items:
                    if item.is_dir():
                        continue
                    parts = PurePosixPath(item.filename).parts
                    if item.file_size > MAX_FILE or ".." in parts or "\\" in item.filename or ((item.external_attr >> 16) & 0o170000) == 0o120000:
                        raise InvalidInput("Недопустимый legacy ZIP")
                    if len(parts) == 2 and parts[0] == "sounds":
                        kind, name = "sounds", parts[1]
                    elif len(parts) == 2 and parts[0] == "configs" and parts[1] in {"custom_actions.json", "dialog_history.json", "suggestions.json", "camera_settings.json"}:
                        kind, name = "settings", "legacy_" + parts[1]
                    elif len(parts) == 3 and parts[:2] == ("station", "custom_scripts") and parts[2].endswith(".sh"):
                        kind, name = "scripts", parts[2]
                    else:
                        raise InvalidInput("Неизвестный файл в резервной копии 2.7")
                    name = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
                    if not name or name.startswith("."):
                        name = "import_" + name
                    target = f"{kind}/{filename(name)}"
                    if target in seen:
                        raise InvalidInput("Имена в архиве конфликтуют")
                    seen.add(target)
                    body = old.read(item)
                    new.writestr(target, body)
                    manifest[target] = hashlib.sha256(body).hexdigest()
                new.writestr("manifest.json", json.dumps({"format": 1, "files": manifest}))
        except (zipfile.BadZipFile, OSError, ValueError) as e:
            raise InvalidInput("Не удалось прочитать резервную копию 2.7") from e
        return output.getvalue()
