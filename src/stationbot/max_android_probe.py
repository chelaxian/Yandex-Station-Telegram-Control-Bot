"""Read-only Android service inventory for the experimental Station Max."""
from __future__ import annotations

import argparse
import base64
import importlib.resources
import subprocess
import sys

from .max_ssh_probe import MaxSshTarget, probe_max_ssh
from .provision import ProvisionError

_MARKER = "MAX_ANDROID_PROBE_V1"
_INVENTORY = r"""
printf 'MAX_ANDROID_PROBE_V1\n'
h() { printf '%s\n' "--- $*"; }
h build
for k in ro.build.version.release ro.build.version.sdk ro.product.manufacturer ro.product.model ro.product.device ro.build.type ro.build.tags; do
  printf '%s=%s\n' "$k" "$(getprop $k)"
done
getenforce 2>&1
h binder nodes
ls -l /dev/binder /dev/hwbinder /dev/vndbinder 2>&1
h command wrappers
for n in am pm media cmd; do
  f=/system/bin/$n
  if [ "$(head -c 2 "$f" 2>/dev/null)" = "#!" ]; then printf '%s script:\n' "$n"; head -n 8 "$f"; else printf '%s native-or-missing\n' "$n"; fi
done
h services
service list 2>&1 | grep -E 'audio|media|activity|package' | head -n 40
h cmd services
cmd -l 2>&1 | head -n 80
h dumpsys audio
dumpsys audio 2>&1 | head -n 120
h dumpsys media_session
dumpsys media_session 2>&1 | head -n 60
h relevant packages
pm list packages 2>&1 | grep -i -E 'yandex|yio|alice|quasar|media|music|player|audio|tts|sound|speech' | head -n 80
h tools
for n in tinyplay tinymix tinycap aplay stagefright sox am cmd media pm input service dumpsys; do
  if command -v "$n" >/dev/null 2>&1; then printf '%s present\n' "$n"; else printf '%s missing\n' "$n"; fi
done
h adbd environment variable names
p=$(pidof adbd | cut -d' ' -f1)
if [ -r "/proc/$p/environ" ]; then tr '\000' '\n' < "/proc/$p/environ" | cut -d= -f1 | sort; else echo unavailable; fi
"""
_BINDER_TEST = r"""
d=$(mktemp -d /data/local/tmp/max-binder.XXXXXXXX) || exit 1
trap 'rm -rf "$d"' EXIT
printf '%s' '@PAYLOAD@' | base64 -d > "$d/binder.jar" || exit 1
tr '\000' '\n' < "/proc/$p/environ" > "$d/env"
while IFS= read -r l; do
  case "$l" in ANDROID_*=*|BOOTCLASSPATH=*|SYSTEMSERVERCLASSPATH=*|EXTERNAL_STORAGE=*|ASEC_MOUNTPOINT=*|LOOP_MOUNTPOINT=*|DOWNLOAD_CACHE=*|STANDALONE_SYSTEMSERVER_JARS=*|LD_LIBRARY_PATH=*) export "$l";; esac
done < "$d/env"
h binder test using adbd environment
CLASSPATH="$d/binder.jar" app_process /system/bin MaxBinder 2>&1 | head -n 40
"""


def probe_max_android(target: MaxSshTarget, ssh: str = "ssh", binder_test: bool = False) -> str:
    probe_max_ssh(target, ssh)
    script = _INVENTORY
    if binder_test:
        jar = importlib.resources.files("stationbot").joinpath("max-binder.jar").read_bytes()
        script += _BINDER_TEST.replace("@PAYLOAD@", base64.b64encode(jar).decode("ascii"))
    args = [ssh, *(["-F", target.ssh_config] if target.ssh_config else []),
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8",
            "-p", str(target.port), "--", f"{target.user}@{target.host}", "sh -s"]
    try:
        # Bytes avoid Windows text-mode CRLF translation of the remote shell script.
        result = subprocess.run(args, input=script.encode("utf-8"), capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProvisionError("SSH недоступен или время ожидания истекло; проверьте остатки /data/local/tmp/max-binder.*") from exc
    if result.returncode != 0:
        raise ProvisionError("Android-инвентаризация не выполнена; воспроизведение не запускалось")
    output = result.stdout.decode("utf-8", errors="replace") if isinstance(result.stdout, bytes) else result.stdout
    lines = [line.rstrip().rstrip("\x00") for line in output.splitlines()]
    markers = [index for index, line in enumerate(lines) if line == _MARKER]
    if len(markers) != 1 or not lines[markers[0] + 1:]:
        raise ProvisionError("Неизвестный или пустой ответ Android-инвентаризации; поддержка звука не подтверждена")
    return "\n".join(lines[markers[0] + 1:])[:30000]


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Read-only Android-инвентаризация Станции Макс; звук не воспроизводится")
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--ssh-config")
    parser.add_argument("--binder-test", action="store_true",
                        help="дополнительно проверить доступ Java к binder с окружением adbd; без звука")
    args = parser.parse_args()
    try:
        print(probe_max_android(MaxSshTarget(args.host, args.user, args.port, args.ssh_config), binder_test=args.binder_test))
    except ProvisionError as error:
        print(str(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
