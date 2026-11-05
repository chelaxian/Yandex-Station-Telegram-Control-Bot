"""Host service: recover managed LUNA forwards and run one bot process."""
from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from .instance import InstanceLock
from .provision import Adb, ProvisionError, device_json

logger = logging.getLogger(__name__)


def load_environment(root: Path):
    for line in (root / "secrets.env").read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition("=")
        if separator and key in {"TELEGRAM_BOT_TOKEN", "TELEGRAM_PROXY_URL"}:
            os.environ[key] = value


def recover(station, adb_path):
    adb = Adb(adb_path, station["serial"])
    try:
        device = device_json(station["port"])
        if device.get("model") == station["model"]:
            return
        raise ProvisionError("Модель по локальному порту изменилась")
    except OSError:
        pass
    adb.connect()
    if adb.probe() != station["model"]:
        raise ProvisionError("После переподключения идентификация изменилась")
    adb.start()
    adb.forward(station["port"])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    plan = json.loads((root / "installation.json").read_text(encoding="utf-8"))
    load_environment(root)
    os.environ["PATH"] = plan["path"]
    if args.check:
        from .config import Config
        config = Config.load(root / "config.toml")
        config.token()
        for station in plan["stations"]:
            recover(station, plan["adb"])
            if device_json(station["port"])["model"] != station["model"]:
                raise ProvisionError("Проверка модели не пройдена")
        print("Конфигурация и подключения LUNA проверены. Poller здесь намеренно не запускается; служба будет запущена на следующем шаге.")
        return
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    lock = InstanceLock(root / "supervisor.lock")
    stopping = False
    def stop(signum, frame):
        nonlocal stopping
        stopping = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    child = None
    try:
        failures = 0
        while not stopping:
            for station in plan["stations"]:
                try:
                    recover(station, plan["adb"])
                except (OSError, ValueError, ProvisionError):
                    logger.warning("station_unavailable id=%s", station["id"])
            if child is None:
                child = subprocess.Popen([sys.executable, "-m", "stationbot", "--config", str(root / "config.toml"), "run"])
            elif child.poll() is not None:
                failures += 1
                if failures >= 3:
                    raise ProvisionError("Бот завершился трижды; проверьте настройки и отсутствие второго poller")
                child = None
            for _ in range(10):
                if stopping:
                    break
                time.sleep(.5)
    finally:
        if child and child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=5)
        lock.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never print secrets, request URLs or raw remote shell output.
        print(f"Служба остановлена: {type(error).__name__}", file=sys.stderr)
        raise SystemExit(1) from None
