from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import logging
import sys
from pathlib import Path

from .config import Config
from .errors import BotError
from .instance import InstanceLock
from .luna import CONTRACT_COMMIT, Luna
from .store import Store


async def doctor(config: Config) -> int:
    result = {"contract_commit": CONTRACT_COMMIT, "stations": {}}
    failed = False
    for station in config.stations:
        client = Luna(station)
        try:
            device = await client.device()
            result["stations"][station.id] = {"model": device.model, "online": True,
                                               "features": sorted(device.features)}
        except BotError as e:
            failed = True
            result["stations"][station.id] = {"online": False, "error": str(e)}
        finally:
            await client.close()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return int(failed)


async def serve(config: Config) -> None:
    from aiogram import Bot
    from aiogram.types import BotCommand

    from .service import Service
    from .telegram import make_dispatcher, timer_worker

    lock = InstanceLock(config.state_dir / "instance.lock")
    store = Store(config.state_dir / "stationbot.db", config.owner_id)
    clients: dict[str, Luna] = {}
    try:
        await store.open()
        for station in config.stations:
            clients[station.id] = Luna(station)
        service = Service(config, store, clients)
        async with Bot(config.token()) as bot:
            await bot.set_my_commands([BotCommand(command=cmd, description=desc) for cmd, desc in [
                ("menu", "Управление станцией"), ("stations", "Выбор станции"),
                ("features", "Возможности и ограничения"), ("help", "Справка")]])
            dispatcher = make_dispatcher(service)
            timer_task = asyncio.create_task(timer_worker(service, bot), name="durable-timers")
            polling_task = asyncio.create_task(dispatcher.start_polling(
                bot, allowed_updates=["message", "callback_query"], tasks_concurrency_limit=16),
                name="telegram-polling")
            try:
                # A failed scheduler must not silently leave a healthy-looking poller running.
                done, _ = await asyncio.wait({polling_task, timer_task}, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
            finally:
                timer_task.cancel()
                polling_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await asyncio.gather(timer_task, polling_task, return_exceptions=True)
    finally:
        await asyncio.gather(*(client.close() for client in clients.values()))
        await store.close()
        lock.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Yandex Station Telegram Control Bot")
    parser.add_argument("--config", type=Path, default=Path("config.toml"))
    parser.add_argument("command", choices=["run", "doctor"], nargs="?", default="run")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    # httpx debug logging can include token-bearing URLs from other integrations.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        config = Config.load(args.config.resolve())
        if args.command == "doctor":
            sys.exit(asyncio.run(doctor(config)))
        asyncio.run(serve(config))
    except BotError as e:
        print(str(e), file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print(f"Запуск не удался ({type(e).__name__}); проверьте окружение и соединение", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
