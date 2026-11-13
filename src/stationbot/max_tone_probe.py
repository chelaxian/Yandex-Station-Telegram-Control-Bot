"""Opt-in short Android AudioTrack test; does not change system volume."""
from __future__ import annotations

import argparse
import base64
import importlib.resources
import subprocess
import sys

from .max_ssh_probe import MaxSshTarget, probe_max_ssh
from .provision import ProvisionError


def run_tone(target: MaxSshTarget, ssh: str = "ssh") -> str:
    probe_max_ssh(target, ssh)
    payload = importlib.resources.files("stationbot").joinpath("max-tone.jar").read_bytes()
    encoded = base64.b64encode(payload).decode("ascii")
    # A fresh private directory avoids overwriting existing files. EXIT cleanup also
    # runs on normal app_process failure; abrupt power loss may leave the directory.
    command = (
        "umask 077; d=$(mktemp -d /data/local/tmp/max-tone.XXXXXXXX) || exit 1; "
        "trap 'rm -f \"$d/tone.jar\"; rmdir \"$d\"' EXIT; "
        f"printf '%s' '{encoded}' | base64 -d > \"$d/tone.jar\" || exit 1; "
        "CLASSPATH=\"$d/tone.jar\" app_process /system/bin MaxTone"
    )
    args = [ssh, *(["-F", target.ssh_config] if target.ssh_config else []),
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8",
            "-p", str(target.port), "--", f"{target.user}@{target.host}", command]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=25, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProvisionError("SSH недоступен или время ожидания истекло; проверьте остатки /data/local/tmp/max-tone.*") from exc
    lines = (result.stdout + "\n" + result.stderr).splitlines()
    evidence = [line for line in lines if line.startswith(("MAX_TONE_RESULT ", "MAX_TONE_ERROR "))]
    evidence = [line[:250] for line in evidence[:3]]
    if result.returncode != 0 or not any(line.startswith("MAX_TONE_RESULT ") for line in evidence):
        raise ProvisionError("Проверка не завершилась успешно. " + " ".join(evidence))
    return "\n".join(evidence)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Короткий тест звука Станции Макс через Android AudioTrack")
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--ssh-config")
    parser.add_argument("--play", action="store_true", help="согласие на короткий звуковой сигнал")
    args = parser.parse_args()
    if not args.play:
        parser.error("Для воспроизведения явно укажите --play")
    try:
        print(run_tone(MaxSshTarget(args.host, args.user, args.port, args.ssh_config)))
    except ProvisionError as error:
        print(str(error))
        return 1
    print("Завершение команды не подтверждает слышимость: сообщите, слышали ли сигнал.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
