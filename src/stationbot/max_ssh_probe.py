"""Read-only identity check for the experimental Android Max SSH transport.

This is not an installer and does not establish root or alter ADB.
"""
from __future__ import annotations

import argparse
import ipaddress
import re
import subprocess
import sys
from dataclasses import dataclass

from .provision import ProvisionError

_COMMAND = (
    "printf 'MAX_PROBE_V1\\n'; id -u; uname -m; "
    "cat /sys/class/graphics/fb4/name /sys/class/graphics/fb4/virtual_size "
    "/sys/class/graphics/fb4/bits_per_pixel /sys/class/graphics/fb4/stride "
    "/sys/class/graphics/fb5/name /sys/class/graphics/fb5/virtual_size "
    "/sys/class/graphics/fb5/bits_per_pixel /sys/class/graphics/fb5/stride"
)
_EXPECTED = ["0", "aarch64", "YNDX LED screen", "25,16", "24", "75", "YNDX LED ring", "24,1", "24", "72"]


@dataclass(frozen=True)
class MaxSshTarget:
    host: str
    user: str
    port: int = 22
    ssh_config: str | None = None

    def __post_init__(self):
        try:
            ipaddress.ip_address(self.host)
        except ValueError as exc:
            raise ProvisionError("Для SSH укажите IP-адрес колонки") from exc
        if not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", self.user) or type(self.port) is not int or not 1 <= self.port <= 65535:
            raise ProvisionError("Некорректные пользователь или порт SSH")


def probe_max_ssh(target: MaxSshTarget, ssh: str = "ssh") -> bool:
    """Verify an existing root login and reported geometry without remote writes."""
    args = [ssh, *( ["-F", target.ssh_config] if target.ssh_config else []), "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8", "-p", str(target.port), "--", f"{target.user}@{target.host}", _COMMAND]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProvisionError("SSH недоступен или превышено время ожидания") from exc
    if result.returncode != 0:
        raise ProvisionError("SSH-проверка не выполнена; проверьте ключ и подтверждённый ключ хоста")
    lines = [line.strip().strip("\x00") for line in result.stdout.splitlines()]
    if lines.count("MAX_PROBE_V1") != 1 or lines[lines.index("MAX_PROBE_V1") + 1:] != _EXPECTED:
        raise ProvisionError("SSH не предоставил root или аппаратные признаки не совпали; установка не выполняется")
    return True


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Проверить существующий root SSH Станции Макс без записи")
    parser.add_argument("--host", required=True, help="IP-адрес колонки")
    parser.add_argument("--user", required=True, help="Имя пользователя для существующего SSH")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--ssh-config", help="Путь к существующему SSH-конфигу")
    args = parser.parse_args()
    try:
        probe_max_ssh(MaxSshTarget(args.host, args.user, args.port, args.ssh_config))
    except ProvisionError as error:
        print(str(error))
        return 1
    print("Root SSH и признаки Станции Макс подтверждены; изменений не внесено.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
