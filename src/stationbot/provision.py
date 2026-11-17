"""Qualified, managed LUNA installation over existing root ADB. No unlocking."""
from __future__ import annotations

import hashlib
import ipaddress
import json
import re
import shlex
import subprocess
import time
import urllib.request
from pathlib import Path

from .network import is_lan_address

ROOT = "/data/local/stationbot-luna"
REMOTE_PORT = 18100
RUNTIME_RELEASE = "v0.2.23"
RUNTIME_COMMIT = "b6ddd7f4e70f985256d01343899697a076f6ce05"
PROFILES = {
    "yandexmini_3_pro": {
        "label": "Мини 3 Про",
        "board": "Yandex Pickle EVT",
        "firmware": ".50.4795647264.",
        "binary": "luna-pickle",
        "sha256": "f953d7d80c64e71822839d01933ba4a97254c9d974710f911edfe9d16f01668d",
        "audio_pcm": "speakers",
    },
    "yandexstation_2": {
        "label": "Станция 2",
        "board": "Yandex Station Midi",
        "firmware": ".50.4794649087.",
        "binary": "luna-yandexstation_2",
        "sha256": "5659c67c8d40fd0091173a186cf2ed7de4ff047cfb107c8cac932c64b13b6cdb",
        "audio_pcm": "dmix_spk_plug",
    },
    "yandexplum": {
        "label": "Лайт 2 (экспериментально)",
        "board": "Yandex Plum EVT2",
        "firmware": ".50.4795647582.",
        "binary": "luna-yandexplum",
        "sha256": "442028c98420d42dd9a61ff21c70f638c48644a41b524c1025afd6a753b9a5af",
        "audio_pcm": "plug:dmix_spk",
        "experimental": True,
    },
}


class ProvisionError(RuntimeError):
    pass


def serial_address(value: str) -> str:
    host, separator, port = value.partition(":")
    try:
        address = ipaddress.IPv4Address(host)
    except ValueError as e:
        raise ProvisionError("Нужен IPv4-адрес колонки в домашней сети") from e
    if not is_lan_address(address):
        raise ProvisionError("Нужен LAN IPv4: 10.x, 172.16–31.x или 192.168.x. VPN fake-IP 198.18.x не является адресом колонки; проверьте адрес в роутере.")
    if separator and port != "5555":
        raise ProvisionError("Укажите существующий root ADB на порту 5555")
    return f"{address}:5555"


def identify(uid: str, architecture: str, board: str, firmware: str) -> str:
    clean_uid = uid.strip() or "(пусто)"
    clean_architecture = architecture.strip() or "(пусто)"
    if uid.strip() != "0" or architecture.strip() != "aarch64":
        raise ProvisionError(
            "Root ADB или архитектура не подходят: нужен UID 0 и aarch64, получено "
            f"UID {clean_uid}, архитектура {clean_architecture}. Установка остановлена; прошивка не меняется."
        )
    matches = [model for model, p in PROFILES.items() if board.strip("\0 \r\n") == p["board"] and p["firmware"] in firmware]
    if len(matches) != 1:
        clean_board = board.strip("\0 \r\n") or "(пусто)"
        clean_firmware = firmware.strip("\0 \r\n") or "(пусто)"
        supported = ", ".join(
            model
            + (" [экспериментально]" if profile.get("experimental") else "")
            + " (" + profile["board"] + ", " + profile["firmware"] + "*)"
            for model, profile in PROFILES.items()
        )
        raise ProvisionError(
            "Модель/прошивка не квалифицирована для автоматической установки. Найдено: "
            f"board={clean_board}, firmware={clean_firmware}. "
            f"Автоматически поддерживаются: {supported}. Установка остановлена до записи файлов; чужой бинарник не подставляется."
        )
    return matches[0]


def device_json(port: int):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(f"http://127.0.0.1:{port}/api/device", timeout=3) as response:
        return json.loads(response.read(1024 * 1024))


def required_features(owner_tools: bool, model: str = "") -> set[str]:
    # The separately qualified experimental Max runtime currently has no
    # audio backend. Do not require an unsupported feature for its ring-only
    # contract; owner tools remain explicitly required when enabled.
    baseline = {"led.ring.rgb", "led.ring.24"} if model == "yandexstation_max" else {"audio.jobs.v1"}
    return baseline | ({"owner.tools.v1", "owner.speech.phase.v1"} if owner_tools else set())


def missing_features(device: dict, model: str, owner_tools: bool) -> set[str]:
    if device.get("model") != model:
        return {"model"}
    missing = required_features(owner_tools, model) - set(device.get("features", []))
    if model == "yandexstation_max" and (not isinstance(device.get("led"), dict) or device["led"].get("ring_count") != 24):
        missing.add("led.ring_count=24")
    return missing


def apply_update_policy(port: int):
    """Enable upstream updates while the host supervisor keeps a qualified rollback."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = f"http://127.0.0.1:{port}/api/settings"
    with opener.open(url, timeout=5) as response:
        settings = json.loads(response.read(1024 * 1024))
    updates = settings.setdefault("updates", {})
    updates["enabled"] = True
    interval = updates.get("interval_minutes", 360)
    if type(interval) is not int or not 5 <= interval <= 1440:
        updates["interval_minutes"] = 360
    request = urllib.request.Request(url, data=json.dumps(settings).encode(), method="PUT", headers={"Content-Type": "application/json"})
    with opener.open(request, timeout=5):
        pass
    with opener.open(url, timeout=5) as response:
        persisted = json.loads(response.read(1024 * 1024)).get("updates", {})
        if persisted.get("enabled") is not True or not 5 <= persisted.get("interval_minutes", 0) <= 1440:
            raise ProvisionError("Не удалось применовать управляемую политику обновлений LUNA")


def suspend_updates(port: int):
    """Disable a bad upstream release after rollback until a new bot release qualifies it."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    url = f"http://127.0.0.1:{port}/api/settings"
    with opener.open(url, timeout=5) as response:
        settings = json.loads(response.read(1024 * 1024))
    settings.setdefault("updates", {})["enabled"] = False
    request = urllib.request.Request(url, data=json.dumps(settings).encode(), method="PUT", headers={"Content-Type": "application/json"})
    with opener.open(request, timeout=5):
        pass
    with opener.open(url, timeout=5) as response:
        if json.loads(response.read(1024 * 1024)).get("updates", {}).get("enabled") is not False:
            raise ProvisionError("Не удалось приостановить автообновление LUNA")


class Adb:
    def __init__(self, executable: str, serial: str):
        self.executable, self.serial = executable, serial_address(serial)

    def run(self, args, timeout=30):
        try:
            result = subprocess.run([self.executable, *args], capture_output=True, text=True, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise ProvisionError("ADB недоступен или превышено время ожидания") from e
        if result.returncode:
            details = [line.strip() for line in result.stderr.splitlines() if line.strip()]
            suffix = f"; ADB: {details[-1]}" if details else ""
            raise ProvisionError("Команда ADB не выполнена; проверьте доступ к колонке" + suffix)
        return result.stdout

    def shell(self, command: str):
        marker = "__STATIONBOT_RESULT__"
        # Some station ADB transports unescape and destroy backslash sequences in
        # printf format strings. Literal echo calls keep the protocol readable on
        # Plum, Pickle, and Station 2 alike.
        source = f"echo {marker}; ( set -e; {command} ); rc=$?; echo __STATIONBOT_EXIT__$rc"
        result = self.run(["-s", self.serial, "shell", "/bin/sh -c " + shlex.quote(source)])
        # A file-ending command such as cat(1) may have no trailing newline on the
        # remote side, so require the exact terminal sentinel without assuming one.
        if marker + "\n" not in result or "__STATIONBOT_EXIT__0" not in result[-64:]:
            raise ProvisionError("Проверка или установка на колонке не завершена; чужие процессы не останавливались")
        return result.split(marker + "\n", 1)[1].rsplit("__STATIONBOT_EXIT__", 1)[0].strip()

    def connect(self):
        self.run(["connect", self.serial])
        state = self.run(["-s", self.serial, "get-state"])
        if state.strip() != "device":
            raise ProvisionError("Подтвердите существующий ADB-доступ; установщик не получает root и не прошивает колонку")

    def probe(self):
        self.connect()
        fields = self.shell("id -u; uname -m; cat /proc/device-tree/model; printf '\\n'; cat /system/vendor/quasar/version_full").splitlines()
        values = [field.strip("\0 \r\n\t") for field in fields if field.strip("\0 \r\n\t")]
        observed = "; ".join(value[:160] for value in values) or "(пусто)"
        grouped = {
            "UID": [value for value in values if re.fullmatch(r"[0-9]+", value)],
            "architecture": [value for value in values if value in {"aarch64", "arm64", "armv7l"}],
            "board": [value for value in values if re.fullmatch(r"Yandex(?: [A-Za-z0-9_-]+)+", value)],
            "firmware": [value for value in values if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+\.[0-9]{8}\.[0-9]+", value)],
        }
        if any(len(candidates) != 1 for candidates in grouped.values()):
            raise ProvisionError(
                "Не удалось однозначно прочитать идентификацию колонки. Безопасный вывод: "
                f"{observed}. Установка остановлена до записи файлов."
            )
        # Extra non-empty adapter banners are tolerated only when each expected field is
        # unique. Exact profile matching below remains the sole authorization for a write.
        return identify(*(candidates[0] for candidates in grouped.values()))

    def forward(self, port: int, *, refresh: bool = False):
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ProvisionError("Некорректный локальный порт")
        expected = [self.serial, f"tcp:{port}", f"tcp:{REMOTE_PORT}"]
        entries = [line.split() for line in self.run(["forward", "--list"]).splitlines()]
        present = expected in entries
        if present and not refresh:
            return
        if any(len(e) > 1 and e[1] == expected[1] and e != expected for e in entries):
            raise ProvisionError("Локальный порт занят другим ADB-подключением; оно сохранено")
        # ADB can retain a mapping after the transport drops. Reconnect must replace
        # only this installation's exact serial/local-port/remote-port triple.
        if present:
            self.run(["-s", self.serial, "forward", "--remove", expected[1]])
        self.run(["-s", self.serial, "forward", "--no-rebind", *expected[1:]])

    def start(self):
        # flock belongs to this installation. No vendor boot hooks, broad pkill,
        # mixer changes or reset of the shared ADB server.
        return self.shell(f"test -f {ROOT}/managed-v1 || exit 1; chmod 700 {ROOT}/start.sh; S=; for c in setsid /bin/busybox; do command -v $c >/dev/null 2>&1 || continue; if [ $c = setsid ]; then S=setsid; else S='/bin/busybox setsid'; fi; break; done; nohup $S {ROOT}/start.sh >/dev/null 2>&1 </dev/null & sleep 2")

    def install(self, binaries: Path, port: int, owner_tools: bool = True):
        model = self.probe()
        profile = PROFILES[model]
        binary = binaries / profile["binary"]
        if not binary.is_file() or hashlib.sha256(binary.read_bytes()).hexdigest() != profile["sha256"]:
            raise ProvisionError("Бинарник LUNA отсутствует или SHA-256 не совпадает с закреплённым runtime")
        # Refuse an unrelated directory and reserve space before transferring.
        self.shell(f"if [ -e {ROOT} ] && [ ! -f {ROOT}/managed-v1 ]; then exit 1; fi; test $(df -Pk /data | tail -n 1 | awk '{{print $4}}') -ge 8192")
        self.shell(f"umask 077; mkdir -p {ROOT}/data; touch {ROOT}/managed-v1; mkdir -p /tmp/stationbot-luna-audio; if [ ! -e {ROOT}/data/audio-jobs ] && [ ! -L {ROOT}/data/audio-jobs ]; then ln -s /tmp/stationbot-luna-audio {ROOT}/data/audio-jobs; fi")
        for attempt in (1, 2):
            try:
                self.run(["-s", self.serial, "push", str(binary), ROOT + "/luna.next"], timeout=120)
                break
            except ProvisionError:
                self.shell(f"rm -f {ROOT}/luna.next")
                if attempt == 2:
                    raise
                time.sleep(3)
                self.connect()
        self.shell(f"test $(sha256sum {ROOT}/luna.next | cut -d' ' -f1) = {profile['sha256']}")
        self.shell(f"ln -f {ROOT}/luna.next {ROOT}/luna.qualified.next; test $(sha256sum {ROOT}/luna.qualified.next | cut -d' ' -f1) = {profile['sha256']}")
        start = starter(owner_tools, profile)
        # Write fixed generated text through a literal quoted shell argument.
        self.shell(f"umask 077; printf %s {shlex.quote(start)} >{ROOT}/start.sh.next; chmod 700 {ROOT}/start.sh.next; if [ -f {ROOT}/start.sh ]; then cp -p {ROOT}/start.sh {ROOT}/start.sh.previous; fi; if [ -f {ROOT}/luna ]; then ln -f {ROOT}/luna {ROOT}/luna.previous; fi")
        self.stop()
        try:
            self.shell(f"mv {ROOT}/luna.next {ROOT}/luna; chmod 700 {ROOT}/luna; mv {ROOT}/luna.qualified.next {ROOT}/luna.qualified; chmod 700 {ROOT}/luna.qualified; mv {ROOT}/start.sh.next {ROOT}/start.sh")
            self.start()
            self.forward(port)
            device = {}
            for _ in range(30):
                try:
                    device = device_json(port)
                    if not missing_features(device, model, owner_tools):
                        apply_update_policy(port)
                        return {"serial": self.serial, "port": port, "model": model, "sha256": profile["sha256"]}
                except (OSError, ValueError):
                    pass
                time.sleep(1)
            raise ProvisionError("Новая LUNA не прошла проверку готовности. " + self.diagnose(model, device, owner_tools))
        except Exception:
            self.stop()
            restored = self.shell(f"if [ -f {ROOT}/luna.previous ] && [ -f {ROOT}/start.sh.previous ]; then cp -p {ROOT}/luna.previous {ROOT}/luna; cp -p {ROOT}/start.sh.previous {ROOT}/start.sh; printf restored; fi")
            if restored == "restored":
                self.shell(f"ln -f {ROOT}/luna {ROOT}/luna.qualified; chmod 700 {ROOT}/luna.qualified")
                self.start()
            raise

    def restore_qualified(self, port: int, model: str, owner_tools: bool = True):
        """Roll back a failed upstream auto-update to the last qualified binary."""
        profile = PROFILES[model]
        digest = profile["sha256"]
        self.shell(
            f"test -f {ROOT}/luna.qualified; "
            f"test $(sha256sum {ROOT}/luna.qualified | cut -d' ' -f1) = {digest}"
        )
        self.stop()
        try:
            self.shell(f"mv {ROOT}/luna {ROOT}/luna.rejected; ln {ROOT}/luna.qualified {ROOT}/luna; chmod 700 {ROOT}/luna")
            self.start()
            self.forward(port, refresh=True)
            for _ in range(15):
                try:
                    device = device_json(port)
                    if not missing_features(device, model, owner_tools):
                        suspend_updates(port)
                        self.shell(f"rm -f {ROOT}/luna.rejected")
                        return device
                except (OSError, ValueError):
                    pass
                time.sleep(1)
        except Exception:
            self.shell(f"if [ -f {ROOT}/luna.rejected ]; then rm -f {ROOT}/luna; mv {ROOT}/luna.rejected {ROOT}/luna; fi")
            raise
        raise ProvisionError("Не удалось откатить LUNA на квалифицированный runtime")

    def promote_qualified(self):
        """Keep the last contract-passing binary as the no-extra-space rollback link."""
        self.shell(
            f"test -f {ROOT}/luna; test -f {ROOT}/luna.qualified; "
            f"a=$(sha256sum {ROOT}/luna | cut -d' ' -f1); "
            f"b=$(sha256sum {ROOT}/luna.qualified | cut -d' ' -f1); "
            f"[ \"$a\" = \"$b\" ] || ln -f {ROOT}/luna {ROOT}/luna.qualified"
        )

    def diagnose(self, model, device, owner_tools):
        """Safe read-only summary for support; contains no secrets."""
        required = required_features(owner_tools)
        parts = []
        if device:
            parts.append(f"модель={device.get('model')}; нет функций: {', '.join(sorted(required - set(device.get('features', [])))) or '-'}")
        else:
            parts.append("LUNA не отвечает на /api/device")
        try:
            info = self.shell("printf 'pid:'; pidof luna || echo none; printf 'aplay:'; command -v aplay || echo none; printf 'log:'; tail -n 8 /tmp/stationbot-luna.log 2>&1 | cut -c1-160")
            parts.append(re.sub(r"\s+", " ", info)[:700])
        except ProvisionError:
            pass
        return "Диагностика: " + " | ".join(parts)

    def stop(self):
        # Only a process whose executable is exactly our managed binary.
        self.shell(f"for p in $(pidof luna); do if [ \"$(readlink /proc/$p/exe)\" = {ROOT}/luna ] || tr '\\0' ' ' </proc/$p/cmdline | grep -q -- '--data-dir {ROOT}/data'; then kill \"$p\"; fi; done; sleep 1")


def starter(owner_tools: bool, profile: dict) -> str:
    audio_pcm = profile["audio_pcm"]
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", audio_pcm):
        raise ProvisionError("Некорректный ALSA PCM для профиля LUNA")
    return f"""#!/bin/sh
set -eu
umask 077
mkdir -p /tmp/stationbot-luna-audio
exec 9>/tmp/stationbot-luna-start.lock
if command -v flock >/dev/null 2>&1; then flock -n 9 || exit 0; elif [ -x /bin/busybox ]; then /bin/busybox flock -n 9 || exit 0; fi
for p in $(pidof luna); do
    [ "$(readlink /proc/$p/exe)" != {ROOT}/luna ] || exit 0
done
export LUNA_ENABLE_OWNER_TOOLS={'1' if owner_tools else '0'}
export LUNA_AUDIO_PCM={audio_pcm}
exec {ROOT}/luna --listen 127.0.0.1:{REMOTE_PORT} --data-dir {ROOT}/data > /tmp/stationbot-luna.log 2>&1
"""
