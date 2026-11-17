"""Opt-in short Android AudioTrack test; does not change system volume."""
from __future__ import annotations

import argparse
import base64
import importlib.resources
import subprocess
import sys

from .max_ssh_probe import MaxSshTarget, probe_max_ssh
from .provision import ProvisionError

# Level -> (amplitude out of 32767, AudioTrack gain, duration ms). The first public probe
# used 500 * 0.25 and was inaudible at 15% volume, so levels start near -24 dBFS.
LEVELS = {1: (4000, "0.5", 1500), 2: (8000, "0.7", 1500), 3: (14000, "1.0", 1500)}


def run_tone(target: MaxSshTarget, ssh: str = "ssh", level: int = 1) -> str:
    if level not in LEVELS:
        raise ProvisionError("Уровень сигнала должен быть 1, 2 или 3")
    amplitude, gain, millis = LEVELS[level]
    probe_max_ssh(target, ssh)
    payload = importlib.resources.files("stationbot").joinpath("max-tone.jar").read_bytes()
    encoded = base64.b64encode(payload).decode("ascii")
    # A fresh private directory avoids overwriting existing files. ART creates an oat/
    # cache inside it, so cleanup is recursive; abrupt power loss may leave the directory.
    # The Android environment is copied from adbd because root SSH sessions lack it.
    command = (
        "umask 077; d=$(mktemp -d /data/local/tmp/max-tone.XXXXXXXX) || exit 1; "
        "trap 'rm -rf \"$d\"' EXIT; "
        f"printf '%s' '{encoded}' | base64 -d > \"$d/tone.jar\" || exit 1; "
        "p=$(pidof adbd | cut -d' ' -f1); [ -r \"/proc/$p/environ\" ] || exit 1; "
        "tr '\\000' '\\n' < \"/proc/$p/environ\" > \"$d/env\" || exit 1; "
        "while IFS= read -r l; do case \"$l\" in "
        "ANDROID_*=*|BOOTCLASSPATH=*|SYSTEMSERVERCLASSPATH=*|EXTERNAL_STORAGE=*|ASEC_MOUNTPOINT=*|"
        "LOOP_MOUNTPOINT=*|DOWNLOAD_CACHE=*|STANDALONE_SYSTEMSERVER_JARS=*|LD_LIBRARY_PATH=*) "
        "export \"$l\";; esac; done < \"$d/env\"; "
        # A read-only dumpsys snapshot taken while the tone plays shows the active output route.
        "(sleep 0.7; dumpsys media.audio_flinger 2>&1 | "
        "grep -i -E 'output thread|standby|output devices|frames written' | head -n 24 | "
        "sed 's/^/MAX_TONE_ROUTE /') & "
        f"CLASSPATH=\"$d/tone.jar\" app_process /system/bin MaxTone {amplitude} {gain} {millis}; "
        "rc=$?; wait; exit $rc"
    )
    args = [ssh, *(["-F", target.ssh_config] if target.ssh_config else []),
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8",
            "-p", str(target.port), "--", f"{target.user}@{target.host}", command]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=25, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProvisionError("SSH недоступен или время ожидания истекло; проверьте остатки /data/local/tmp/max-tone.*") from exc
    lines = (result.stdout + "\n" + result.stderr).splitlines()
    evidence = [line for line in lines if line.startswith(("MAX_TONE_RESULT ", "MAX_TONE_ERROR ", "MAX_TONE_ROUTE "))]
    evidence = [line[:250] for line in evidence[:30]]
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
    parser.add_argument("--level", type=int, choices=sorted(LEVELS), default=1,
                        help="1: заметный тихий сигнал, 2: средний, 3: громкий; начните с 1")
    parser.add_argument("--play", action="store_true", help="согласие на короткий звуковой сигнал")
    args = parser.parse_args()
    if not args.play:
        parser.error("Для воспроизведения явно укажите --play")
    try:
        print(run_tone(MaxSshTarget(args.host, args.user, args.port, args.ssh_config), level=args.level))
    except ProvisionError as error:
        print(str(error))
        return 1
    print("Завершение команды не подтверждает слышимость: сообщите, слышали ли сигнал.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
