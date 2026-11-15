"""Opt-in microphone level probe for the experimental Station Max; nothing is saved or transmitted."""
from __future__ import annotations

import argparse
import base64
import importlib.resources
import subprocess
import sys

from .max_ssh_probe import MaxSshTarget, probe_max_ssh
from .provision import ProvisionError

SOURCES = {"mic": 1, "voice-recognition": 6}
RATES = (16000, 48000)


def run_mic(target: MaxSshTarget, ssh: str = "ssh", source: str = "mic", rate: int = 16000) -> str:
    if source not in SOURCES or rate not in RATES:
        raise ProvisionError("Недопустимые параметры микрофона")
    probe_max_ssh(target, ssh)
    payload = importlib.resources.files("stationbot").joinpath("max-mic.jar").read_bytes()
    encoded = base64.b64encode(payload).decode("ascii")
    command = (
        "umask 077; d=$(mktemp -d /data/local/tmp/max-mic.XXXXXXXX) || exit 1; "
        "trap 'rm -rf \"$d\"' EXIT; "
        f"printf '%s' '{encoded}' | base64 -d > \"$d/mic.jar\" || exit 1; "
        "p=$(pidof adbd | cut -d' ' -f1); [ -r \"/proc/$p/environ\" ] || exit 1; "
        "tr '\\000' '\\n' < \"/proc/$p/environ\" > \"$d/env\" || exit 1; "
        "while IFS= read -r l; do case \"$l\" in "
        "ANDROID_*=*|BOOTCLASSPATH=*|SYSTEMSERVERCLASSPATH=*|EXTERNAL_STORAGE=*|ASEC_MOUNTPOINT=*|"
        "LOOP_MOUNTPOINT=*|DOWNLOAD_CACHE=*|STANDALONE_SYSTEMSERVER_JARS=*|LD_LIBRARY_PATH=*) "
        "export \"$l\";; esac; done < \"$d/env\"; "
        f"CLASSPATH=\"$d/mic.jar\" app_process /system/bin MaxMic {SOURCES[source]} {rate} 2"
    )
    args = [ssh, *(["-F", target.ssh_config] if target.ssh_config else []),
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8",
            "-p", str(target.port), "--", f"{target.user}@{target.host}", command]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProvisionError("SSH недоступен или время ожидания истекло; проверьте остатки /data/local/tmp/max-mic.*") from exc
    lines = (result.stdout + "\n" + result.stderr).splitlines()
    evidence = [line[:250] for line in lines if line.startswith(("MAX_MIC_RESULT ", "MAX_MIC_ERROR "))][:3]
    if result.returncode != 0 or not any(line.startswith("MAX_MIC_RESULT ") for line in evidence):
        raise ProvisionError("Проверка микрофона не завершилась успешно. " + " ".join(evidence))
    return "\n".join(evidence)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Проверка уровня микрофона Станции Макс; звук не сохраняется")
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--ssh-config")
    parser.add_argument("--source", choices=sorted(SOURCES), default="mic")
    parser.add_argument("--rate", type=int, choices=RATES, default=16000)
    parser.add_argument("--record", action="store_true",
                        help="согласие на 2 секунды записи в память колонки; звук не сохраняется и не передаётся")
    args = parser.parse_args()
    if not args.record:
        parser.error("Для проверки микрофона явно укажите --record")
    try:
        print(run_mic(MaxSshTarget(args.host, args.user, args.port, args.ssh_config), source=args.source, rate=args.rate))
    except ProvisionError as error:
        print(str(error))
        return 1
    print("Звук не сохранялся и не передавался; значения показывают только уровень сигнала.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
