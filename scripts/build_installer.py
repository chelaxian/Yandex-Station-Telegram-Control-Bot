"""Create an offline-code bundle; OS/Python dependencies are installed online."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import zipfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--luna-source", type=Path, required=True)
    parser.add_argument("--notices", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    import sys
    sys.path.insert(0, str(root / "src"))
    from stationbot import __version__
    from stationbot.provision import PROFILES, RUNTIME_COMMIT, RUNTIME_RELEASE
    output = root / "dist" / f"stationbot-{__version__}-installer"
    output.mkdir(parents=True, exist_ok=True)
    wheel = root / "dist" / f"telegram_control_luna-{__version__}-py3-none-any.whl"
    copies = ["install.cmd", "install.ps1", "install.sh", "deploy/bootstrap.py", "requirements.lock.txt", "README.md", "NOTICE.md", "CHANGELOG.md", "docs/TELEGRAM_RELEASE_POST.md", "docs/assets/telegram-main-menu.png"]
    for name in copies:
        target = output / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / name, target)
    for source in (root / "docs").rglob("*.md"):
        target = output / source.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    shutil.copy2(wheel, output / wheel.name)
    runtime = output / "runtime"
    runtime.mkdir(exist_ok=True)
    for profile in PROFILES.values():
        source = args.runtime / profile["binary"]
        if hashlib.sha256(source.read_bytes()).hexdigest() != profile["sha256"]:
            raise RuntimeError("Runtime does not match the pinned qualified source")
        shutil.copy2(source, runtime / source.name)
    shutil.copy2(args.luna_source / "LICENSE", runtime / "LUNA-LICENSE.txt")
    shutil.copy2(args.luna_source / "Cargo.lock", runtime / "Cargo.lock")
    if not (args.notices / "INDEX.json").is_file():
        raise RuntimeError("Third-party notices are required")
    shutil.copytree(args.notices, runtime / "third-party", dirs_exist_ok=True)
    crates = ", ".join(profile["binary"].removeprefix("luna-") for profile in PROFILES.values())
    (runtime / "SOURCE.txt").write_text(
        f"LUNA source: https://github.com/nyakokitsu/luna/tree/{RUNTIME_COMMIT}\n"
        f"LUNA official release: {RUNTIME_RELEASE}\n"
        "Build: aarch64-unknown-linux-musl\n"
        f"Station crates: {crates}\n"
        "Third-party notices: third-party/INDEX.json; crate versions: Cargo.lock\n",
        encoding="utf-8",
    )
    files = {p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.rglob("*")) if p.is_file() and p.name != "bundle.json"}
    (output / "bundle.json").write_text(json.dumps({"version": __version__, "wheel": wheel.name, "runtime_commit": RUNTIME_COMMIT, "runtime_release": RUNTIME_RELEASE, "files": files}, indent=2), encoding="utf-8")
    with zipfile.ZipFile(Path(str(output) + ".zip"), "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as archive:
        for p in sorted(output.rglob("*")):
            if p.is_file():
                archive.write(p, arcname=f"{output.name}/{p.relative_to(output).as_posix()}")
    with tarfile.open(Path(str(output) + ".tar.gz"), "w:gz") as archive:
        for p in sorted(output.rglob("*")):
            if p.is_file():
                info = archive.gettarinfo(p, arcname=f"{output.name}/{p.relative_to(output).as_posix()}")
                info.uid = info.gid = 0
                info.uname = info.gname = ""
                info.mode = 0o755 if p.name == "install.sh" else 0o644
                with p.open("rb") as stream:
                    archive.addfile(info, stream)
    print(f"Installer archives created: {output.name}")


if __name__ == "__main__":
    main()
