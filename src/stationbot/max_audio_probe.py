"""Read-only ALSA inventory for the experimental Android Station Max.

The probe never opens a PCM device, changes a mixer, or plays sound. It only
reads procfs metadata after the separate root/geometry identity check passes.
"""
from __future__ import annotations

import argparse
import subprocess
import sys

from .max_ssh_probe import MaxSshTarget, probe_max_ssh
from .provision import ProvisionError

_MARKER = "MAX_AUDIO_PROBE_V1"
_COMMAND = (
    f"printf '{_MARKER}\\n'; "
    "for f in /proc/asound/cards /proc/asound/devices /proc/asound/pcm; do "
    "printf '%s\\n' \"--- $f\"; cat \"$f\" 2>/dev/null || printf 'unavailable\\n'; "
    "done; "
    "printf '%s\\n' '--- pcm devices'; "
    "for f in /dev/snd/pcmC*D*; do "
    '[ -e "$f" ] || continue; printf \'%s\\n\' "${f##*/}"; '
    "done; "
    "printf '%s\\n' '--- quasar audio services'; "
    "for n in maind aliced yio_audio; do "
    'if pidof "$n" >/dev/null 2>&1; then printf \'%s running\\n\' "$n"; '
    "else printf '%s stopped\\n' \"$n\"; fi; "
    "done; "
    "printf '%s\\n' '--- quasar audio files'; "
    "for f in /system/vendor/quasar/maind /system/vendor/quasar/quasar.cfg; do "
    '[ -f "$f" ] && printf \'%s present\\n\' "$f" || printf \'%s missing\\n\' "$f"; '
    "done; "
    "printf '%s\\n' '--- android audio tools'; "
    "for n in app_process cmd media service dumpsys; do "
    'if command -v "$n" >/dev/null 2>&1; then printf \'%s present\\n\' "$n"; '
    "else printf '%s missing\\n' \"$n\"; fi; done; "
    "for f in /proc/asound/card*/pcm*/sub0/status /proc/asound/card*/pcm*/sub0/hw_params; do "
    '[ -r "$f" ] || continue; printf \'%s\\n\' "--- $f"; cat "$f"; '
    "done"
)


def probe_max_audio(target: MaxSshTarget, ssh: str = "ssh") -> str:
    """Collect non-secret ALSA metadata without opening any audio device."""
    probe_max_ssh(target, ssh)
    args = [
        ssh,
        *(["-F", target.ssh_config] if target.ssh_config else []),
        "-o",
        "BatchMode=yes",
        "-o",
        "StrictHostKeyChecking=yes",
        "-o",
        "ConnectTimeout=8",
        "-p",
        str(target.port),
        "--",
        f"{target.user}@{target.host}",
        _COMMAND,
    ]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=15, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProvisionError("SSH недоступен или превышено время ожидания") from exc
    if result.returncode != 0:
        raise ProvisionError("Аудио-инвентаризация не выполнена; устройства не открывались")
    lines = [line.rstrip().rstrip("\x00") for line in result.stdout.splitlines()]
    markers = [index for index, line in enumerate(lines) if line == _MARKER]
    if len(markers) != 1 or not lines[markers[0] + 1 :]:
        raise ProvisionError("Неизвестный или пустой ответ аудио-инвентаризации; поддержка звука не подтверждена")
    return "\n".join(lines[markers[0] + 1 :])[:12000]


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Собрать read-only аудио-данные Станции Макс")
    parser.add_argument("--host", required=True, help="IP-адрес колонки")
    parser.add_argument("--user", required=True, help="Имя пользователя для существующего SSH")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--ssh-config", help="Путь к существующему SSH-конфигу")
    args = parser.parse_args()
    try:
        print(probe_max_audio(MaxSshTarget(args.host, args.user, args.port, args.ssh_config)))
    except ProvisionError as error:
        print(str(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
