"""Build a small standalone archive for a read-only Station Max probe."""
from __future__ import annotations

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path

PROBES = {
    "ssh": {
        "entry": "stationbot.max_ssh_probe:main",
        "files": ("__init__.py", "network.py", "provision.py", "max_ssh_probe.py"),
    },
    "audio": {
        "entry": "stationbot.max_audio_probe:main",
        "files": ("__init__.py", "network.py", "provision.py", "max_ssh_probe.py", "max_audio_probe.py"),
    },
}


def build(probe: str, output: Path) -> str:
    if probe not in PROBES:
        raise ValueError("Unknown probe")
    source = Path(__file__).resolve().parents[1] / "src" / "stationbot"
    module, function = PROBES[probe]["entry"].split(":")
    main = f"from {module} import {function}\nraise SystemExit({function}())\n"
    with output.open("wb") as stream:
        stream.write(b"#!/usr/bin/env python3\n")
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            files = [(f"stationbot/{name}", (source / name).read_bytes()) for name in PROBES[probe]["files"]]
            files.append(("__main__.py", main.encode("utf-8")))
            for name, contents in sorted(files):
                info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                archive.writestr(info, contents)
    return hashlib.sha256(output.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a standalone read-only Max probe")
    parser.add_argument("probe", choices=PROBES)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    digest = build(args.probe, output)
    print(f"{output}: {digest}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError) as error:
        print(f"Probe build failed: {error}", file=sys.stderr)
        raise SystemExit(1) from None
