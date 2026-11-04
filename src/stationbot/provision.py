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
RUNTIME_COMMIT = "0f2393e4d613472c79755b358abc3047a9466963"
PROFILES = {
    "yandexmini_3_pro": {
        "label": "Мини 3 Про",
        "board": "Yandex Pickle EVT",
        "firmware": ".50.4795647264.",
        "binary": "luna-pickle",
        "sha256": "c32925698f185242099f005a236893802df3d24416b185f576037013bb604b62",
        "audio_pcm": "speakers",
    },
    "yandexstation_2": {
        "label": "Станция 2",
        "board": "Yandex Station Midi",
        "firmware": ".50.4794649087.",
        "binary": "luna-yandexstation_2",
        "sha256": "3c046cd1ac3937830e89e739a7067a6c32c9b79993125d65b16e37ca3b04eaca",
        "audio_pcm": "dmix_spk_plug",
    },
    "yandexplum": {
        "label": "Лайт 2 (экспериментально)",
        "board": "Yandex Plum EVT2",
        "firmware": ".50.4795647582.",
        "binary": "luna-yandexplum",
        "sha256": "1c0f9ac2d5baa3d214b5a5ff5f744ec2c6d4096a073a177641875a12ebe3a4b4",
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
        source = f"printf '{marker}\\n'; ( set -e; {command} ); rc=$?; printf '\\n__STATIONBOT_EXIT__%s\\n' \"$rc\""
        result = self.run(["-s", self.serial, "shell", "/bin/sh -c " + shlex.quote(source)])
        if marker + "\n" not in result or "\n__STATIONBOT_EXIT__0" not in result:
            raise ProvisionError("Проверка или установка на колонке не завершена; чужие процессы не останавливались")
        return result.split(marker + "\n", 1)[1].rsplit("\n__STATIONBOT_EXIT__", 1)[0].strip()

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

    def forward(self, port: int):
        if type(port) is not int or not 1024 <= port <= 65535:
            raise ProvisionError("Некорректный локальный порт")
        expected = [self.serial, f"tcp:{port}", f"tcp:{REMOTE_PORT}"]
        entries = [line.split() for line in self.run(["forward", "--list"]).splitlines()]
        if expected in entries:
            return
        if any(len(e) > 1 and e[1] == expected[1] for e in entries):
            raise ProvisionError("Локальный порт занят другим ADB-подключением; оно сохранено")
        self.run(["-s", self.serial, "forward", "--no-rebind", *expected[1:]])

    def start(self):
        # flock belongs to this installation. No vendor boot hooks, broad pkill,
        # mixer changes or reset of the shared ADB server.
        return self.shell(f"test -f {ROOT}/managed-v1 || exit 1; chmod 700 {ROOT}/start.sh; nohup /bin/busybox setsid {ROOT}/start.sh >/dev/null 2>&1 </dev/null & sleep 1")

    def install(self, binaries: Path, port: int, owner_tools: bool = True):
        model = self.probe()
        profile = PROFILES[model]
        binary = binaries / profile["binary"]
        if not binary.is_file() or hashlib.sha256(binary.read_bytes()).hexdigest() != profile["sha256"]:
            raise ProvisionError("Бинарник LUNA отсутствует или SHA-256 не совпадает с закреплённым runtime")
        # Refuse an unrelated directory and reserve space before transferring.
        self.shell(f"if [ -e {ROOT} ] && [ ! -f {ROOT}/managed-v1 ]; then exit 1; fi; test $(df -Pk /data | tail -n 1 | awk '{{print $4}}') -ge 16384")
        self.shell(f"umask 077; mkdir -p {ROOT}/data; touch {ROOT}/managed-v1; mkdir -p /tmp/stationbot-luna-audio; if [ ! -e {ROOT}/data/audio-jobs ] && [ ! -L {ROOT}/data/audio-jobs ]; then ln -s /tmp/stationbot-luna-audio {ROOT}/data/audio-jobs; fi")
        self.run(["-s", self.serial, "push", str(binary), ROOT + "/luna.next"], timeout=60)
        self.shell(f"test $(sha256sum {ROOT}/luna.next | cut -d' ' -f1) = {profile['sha256']}")
        start = starter(owner_tools, profile)
        # Write fixed generated text through a literal quoted shell argument.
        self.shell(f"umask 077; printf %s {shlex.quote(start)} >{ROOT}/start.sh.next; chmod 700 {ROOT}/start.sh.next; if [ -f {ROOT}/start.sh ]; then cp -p {ROOT}/start.sh {ROOT}/start.sh.previous; fi; if [ -f {ROOT}/luna ]; then cp -p {ROOT}/luna {ROOT}/luna.previous; fi")
        self.stop()
        try:
            self.shell(f"mv {ROOT}/luna.next {ROOT}/luna; chmod 700 {ROOT}/luna; mv {ROOT}/start.sh.next {ROOT}/start.sh")
            self.start()
            self.forward(port)
            for _ in range(15):
                try:
                    device = device_json(port)
                    required = {"audio.jobs.v1"} | ({"owner.tools.v1", "owner.speech.phase.v1"} if owner_tools else set())
                    if device.get("model") == model and required <= set(device.get("features", [])):
                        return {"serial": self.serial, "port": port, "model": model, "sha256": profile["sha256"]}
                except (OSError, ValueError):
                    pass
                time.sleep(1)
            raise ProvisionError("Новая LUNA не прошла проверку готовности")
        except Exception:
            self.stop()
            restored = self.shell(f"if [ -f {ROOT}/luna.previous ] && [ -f {ROOT}/start.sh.previous ]; then cp -p {ROOT}/luna.previous {ROOT}/luna; cp -p {ROOT}/start.sh.previous {ROOT}/start.sh; printf restored; fi")
            if restored == "restored":
                self.start()
            raise

    def stop(self):
        # Only a process whose executable is exactly our managed binary.
        self.shell(f"for p in $(pidof luna); do if [ \"$(readlink /proc/$p/exe)\" = {ROOT}/luna ]; then kill \"$p\"; fi; done; sleep 1")


def starter(owner_tools: bool, profile: dict) -> str:
    audio_pcm = profile["audio_pcm"]
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", audio_pcm):
        raise ProvisionError("Некорректный ALSA PCM для профиля LUNA")
    return f"""#!/bin/sh
set -eu
umask 077
mkdir -p /tmp/stationbot-luna-audio
exec 9>/tmp/stationbot-luna-start.lock
/bin/busybox flock -n 9 || exit 0
for p in $(pidof luna); do
    [ "$(readlink /proc/$p/exe)" != {ROOT}/luna ] || exit 0
done
export LUNA_ENABLE_OWNER_TOOLS={'1' if owner_tools else '0'}
export LUNA_AUDIO_PCM={audio_pcm}
exec {ROOT}/luna --listen 127.0.0.1:{REMOTE_PORT} --data-dir {ROOT}/data > /tmp/stationbot-luna.log 2>&1
"""
