"""Launch the same runtime on a host or a station with an owner-provisioned Python.

No device detection, boot editing, rootfs writes, downloads, or credential defaults.
Use --check during offline packaging; a model-qualified supervisor calls this launcher.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import os
import shutil
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["host", "station"], default="host")
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if sys.version_info < (3, 10):  # noqa: UP036 - standalone bootstrap checks the target interpreter
        parser.error("Python 3.10+ is required")
    for dependency in ["aiogram", "httpx", "aiosqlite", "aiohttp-socks"]:
        try:
            importlib.metadata.version(dependency)
        except importlib.metadata.PackageNotFoundError:
            parser.error(f"Missing offline dependency: {dependency}")
    for executable in ["ffmpeg", "espeak-ng"]:
        if not shutil.which(executable):
            parser.error(f"Missing media runtime: {executable}")
    from stationbot.config import Config
    config = Config.load(args.config.resolve())
    if args.mode == "station":
        from urllib.parse import urlsplit
        if any(urlsplit(s.url).hostname not in {"localhost", "127.0.0.1", "::1"} for s in config.stations):
            parser.error("Station mode requires a local LUNA endpoint")
    secret_path = args.env_file.resolve()
    if os.name != "nt" and secret_path.stat().st_mode & 0o077:
        parser.error("The environment file must be private (chmod 600)")
    for line in secret_path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key or not key.replace("_", "").isalnum():
            parser.error("Invalid environment file entry")
        os.environ[key] = value
    config.token()
    config.telegram_proxy()
    if args.check:
        print(f"{args.mode} prerequisites verified; network and boot not tested")
        return
    import asyncio

    from stationbot.__main__ import serve
    asyncio.run(serve(config))


if __name__ == "__main__":
    main()
