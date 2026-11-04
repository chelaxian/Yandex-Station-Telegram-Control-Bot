"""Interactive host + station configuration, called from the one-click bootstrap."""
from __future__ import annotations

import argparse
import asyncio
import getpass
import json
import os
import shutil
from pathlib import Path

from .config import Config
from .provision import Adb, ProvisionError


def private_write(path: Path, text: str):
    temporary = path.with_suffix(path.suffix + ".next")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    os.chmod(path, 0o600)


def toml_string(value):
    return json.dumps(value, ensure_ascii=False)


async def telegram_preflight(token, proxy):
    from aiogram import Bot
    from aiogram.client.session.aiohttp import AiohttpSession
    async with Bot(token, session=AiohttpSession(proxy=proxy or None)) as bot:
        await bot.get_me()
        if (await bot.get_webhook_info()).url:
            raise ProvisionError("У бота уже настроен webhook; текущая интеграция сохранена. Для этой установки нужен отдельный bot token без webhook.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--answers", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    answers = json.loads(args.answers.read_text(encoding="utf-8")) if args.answers else {}
    if args.answers and os.name != "nt" and args.answers.stat().st_mode & 0o077:
        raise ProvisionError("Файл ответов содержит секреты: выполните chmod 600")
    # Updates reuse exactly the saved configuration; never reset state/roles.
    if (root / "installation.json").exists():
        plan = json.loads((root / "installation.json").read_text(encoding="utf-8"))
        for station in plan["stations"]:
            client = Adb(plan["adb"], station["serial"])
            if client.probe() != station["model"]:
                raise ProvisionError("Модель изменилась; запись на устройство отменена")
            result = client.install(args.bundle / "runtime", station["port"], plan["owner_tools"])
            if result["model"] != station["model"]:
                raise ProvisionError("Модель изменилась; прежняя конфигурация сохранена")
        print("LUNA обновлена; настройки, токен и состояние бота сохранены")
        return
    owner = answers.get("owner_id") or input("Ваш числовой Telegram ID: ").strip()
    if not str(owner).isdigit() or int(owner) <= 0:
        raise ProvisionError("Нужен положительный Telegram ID владельца")
    token = answers.get("bot_token") or getpass.getpass("Токен BotFather (ввод скрыт): ").strip()
    proxy = answers.get("telegram_proxy") if "telegram_proxy" in answers else input("Telegram proxy (Enter — без proxy): ").strip()
    if any(c in token + (proxy or "") for c in "\r\n"):
        raise ProvisionError("Недопустимый перевод строки в реквизитах")
    timezone = answers.get("timezone") or input("Часовой пояс IANA [Europe/Moscow]: ").strip() or "Europe/Moscow"
    addresses = answers.get("stations") or [s.strip() for s in input("IP колонок через запятую (root ADB уже включён): ").split(",") if s.strip()]
    if not 1 <= len(addresses) <= 10 or len(set(addresses)) != len(addresses):
        raise ProvisionError("Укажите от 1 до 10 разных колонок")
    adb = shutil.which("adb")
    if not adb:
        raise ProvisionError("ADB не установлен или отсутствует в PATH")
    os.environ["TELEGRAM_BOT_TOKEN"] = token
    os.environ["TELEGRAM_PROXY_URL"] = proxy or ""
    lines = ["[bot]", f"owner_id = {int(owner)}", 'token_env = "TELEGRAM_BOT_TOKEN"', 'state_dir = "state"', f"timezone = {toml_string(timezone)}"]
    if proxy:
        lines.append('telegram_proxy_env = "TELEGRAM_PROXY_URL"')
    plan = {"schema": 1, "adb": adb, "path": os.environ["PATH"], "owner_tools": True, "stations": []}
    # Validate local config/token before touching any station.
    from .config import StationConfig
    Config(int(owner), (StationConfig("probe", "Проверка", "http://127.0.0.1:18210/api", "probe"),), root / "state", timezone=timezone).token()
    if proxy:
        Config(int(owner), (StationConfig("probe", "Проверка", "http://127.0.0.1:18210/api", "probe"),), root / "state", telegram_proxy_env="TELEGRAM_PROXY_URL").telegram_proxy()
    asyncio.run(telegram_preflight(token, proxy))
    clients = [Adb(adb, address) for address in addresses]
    for address in addresses:
        print(f"Проверяю колонку {address}: root ADB, модель и прошивку…")
    models = [client.probe() for client in clients]
    for index, (client, model) in enumerate(zip(clients, models, strict=True)):
        print(f"Колонка {index + 1}: {model}; установка закреплённой LUNA…")
        station = client.install(args.bundle / "runtime", 18210 + index, True)
        station["id"] = f"station_{index + 1}"
        plan["stations"].append(station)
        label = {"yandexmini_3_pro": "Мини 3 Про", "yandexstation_2": "Станция 2"}[model]
        lines += ["", "[[stations]]", f'id = "{station["id"]}"', f"label = {toml_string(label)}", f'url = "http://127.0.0.1:{station["port"]}/api"', f"expected_model = {toml_string(model)}", "allow_owner_tools = true", "allow_packages = false"]
    private_write(root / "config.toml", "\n".join(lines) + "\n")
    private_write(root / "secrets.env", f"TELEGRAM_BOT_TOKEN={token}\n" + (f"TELEGRAM_PROXY_URL={proxy}\n" if proxy else ""))
    private_write(root / "installation.json", json.dumps(plan, ensure_ascii=False, indent=2))
    Config.load(root / "config.toml")
    print("Готово: конфигурация создана, LUNA установлена на колонки")


if __name__ == "__main__":
    try:
        main()
    except ProvisionError as error:
        print(f"Установка остановлена: {error}")
        raise SystemExit(1) from None
    except Exception as error:
        print(f"Установка остановлена: {type(error).__name__}. Проверьте root ADB, модель, зависимости и права. Секреты не выведены.")
        raise SystemExit(1) from None
