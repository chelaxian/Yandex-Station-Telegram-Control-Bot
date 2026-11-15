"""Android volume probe for the experimental Station Max: reads volume and optionally tests a round trip."""
from __future__ import annotations

import argparse
import subprocess
import sys

from .max_ssh_probe import MaxSshTarget, probe_max_ssh
from .provision import ProvisionError

_MARKER = "MAX_VOLUME_PROBE_V1"
_ENV = r"""
umask 077
d=$(mktemp -d /data/local/tmp/max-volume.XXXXXXXX) || exit 1
trap 'rm -rf "$d"' EXIT
p=$(pidof adbd | cut -d' ' -f1)
[ -r "/proc/$p/environ" ] || exit 1
tr '\000' '\n' < "/proc/$p/environ" > "$d/env" || exit 1
while IFS= read -r l; do
  case "$l" in ANDROID_*=*|BOOTCLASSPATH=*|SYSTEMSERVERCLASSPATH=*|EXTERNAL_STORAGE=*|ASEC_MOUNTPOINT=*|LOOP_MOUNTPOINT=*|DOWNLOAD_CACHE=*|STANDALONE_SYSTEMSERVER_JARS=*|LD_LIBRARY_PATH=*) export "$l";; esac
done < "$d/env"
h() { printf '%s\n' "--- $*"; }
printf 'MAX_VOLUME_PROBE_V1\n'
h music volume before
media volume --stream 3 --get 2>&1 | head -n 8
"""
_ROUND_TRIP = r"""
restore() { media volume --stream 3 --set @RESTORE@ >/dev/null 2>&1; }
trap 'restore; rm -rf "$d"' EXIT
h set music volume @TEST@
media volume --stream 3 --set @TEST@ 2>&1 | head -n 8
h music volume after set
media volume --stream 3 --get 2>&1 | head -n 8
h restore music volume @RESTORE@
media volume --stream 3 --set @RESTORE@ 2>&1 | head -n 8
h music volume after restore
media volume --stream 3 --get 2>&1 | head -n 8
"""


def probe_max_volume(
    target: MaxSshTarget,
    ssh: str = "ssh",
    test_index: int | None = None,
    restore_index: int | None = None,
) -> str:
    if (test_index is None) != (restore_index is None):
        raise ProvisionError("Для проверки изменения укажите --test-index и --restore-index вместе")
    if test_index is not None:
        for value in (test_index, restore_index):
            if type(value) is not int or not 0 <= value <= 100:
                raise ProvisionError("Индексы громкости должны быть целыми числами 0-100")
    probe_max_ssh(target, ssh)
    script = _ENV
    if test_index is not None:
        script += _ROUND_TRIP.replace("@TEST@", str(test_index)).replace("@RESTORE@", str(restore_index))
    args = [ssh, *(["-F", target.ssh_config] if target.ssh_config else []),
            "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8",
            "-p", str(target.port), "--", f"{target.user}@{target.host}", "sh -s"]
    try:
        # Bytes avoid Windows text-mode CRLF translation of the remote shell script.
        result = subprocess.run(args, input=script.encode("utf-8"), capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ProvisionError("SSH недоступен или время ожидания истекло; проверьте остатки /data/local/tmp/max-volume.*") from exc
    if result.returncode != 0:
        raise ProvisionError("Проверка громкости не выполнена; при тесте изменения проверьте текущую громкость вручную")
    output = result.stdout.decode("utf-8", errors="replace") if isinstance(result.stdout, bytes) else result.stdout
    lines = [line.rstrip().rstrip("\x00") for line in output.splitlines()]
    markers = [index for index, line in enumerate(lines) if line == _MARKER]
    if len(markers) != 1 or not lines[markers[0] + 1:]:
        raise ProvisionError("Неизвестный или пустой ответ проверки громкости; управление громкостью не подтверждено")
    return "\n".join(lines[markers[0] + 1:])[:6000]


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Проверка громкости STREAM_MUSIC на Станции Макс")
    parser.add_argument("--host", required=True)
    parser.add_argument("--user", required=True)
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--ssh-config")
    parser.add_argument("--test-index", type=int, help="временный индекс громкости 0-100 (без звука)")
    parser.add_argument("--restore-index", type=int, help="исходный индекс громкости 0-100 для возврата")
    args = parser.parse_args()
    try:
        print(probe_max_volume(MaxSshTarget(args.host, args.user, args.port, args.ssh_config),
                               test_index=args.test_index, restore_index=args.restore_index))
    except ProvisionError as error:
        print(str(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
