from __future__ import annotations

import json
import time
from collections import OrderedDict
from typing import Any

from .catalog import parity_text
from .config import Config
from .errors import BotError, InvalidInput, TransportError, Unavailable
from .luna import Luna
from .store import Store

READ_ONLY = {"status", "health", "capabilities", "volume_get", "clock_get", "plugins", "media_get"}
OWNER_ONLY = {"invoke"}


class Service:
    def __init__(self, config: Config, store: Store, clients: dict[str, Luna]):
        self.config, self.store, self.clients = config, store, clients
        self.last_request: OrderedDict[int, float] = OrderedDict()
        self.active: set[int] = set()

    async def station_for(self, user: int) -> str:
        station = await self.store.selected(user, self.config.stations[0].id)
        return station if station in self.clients else self.config.stations[0].id

    async def run(self, user: int, station: str, action: str, args: list[str], request: str) -> Any:
        if station not in self.clients:
            raise InvalidInput("Неизвестная станция")
        minimum = "viewer" if action in READ_ONLY else "owner" if action in OWNER_ONLY else "operator"
        await self.store.require(user, minimum)
        now = time.monotonic()
        if user in self.active or now - self.last_request.get(user, -1e6) < self.config.rate_seconds:
            raise InvalidInput("Дождитесь завершения предыдущей команды")
        self.last_request[user] = now
        self.last_request.move_to_end(user)
        if len(self.last_request) > 1024:
            self.last_request.popitem(last=False)
        self.active.add(user)
        try:
            if not await self.store.begin_action(request, user, station, action):
                raise InvalidInput("Эта команда уже обработана; повторное выполнение заблокировано")
            client = self.clients[station]
            try:
                # Serialize physical operations per station, not globally across devices.
                async with client.operation_lock:
                    # Revocation while queued must take effect before touching the station.
                    await self.store.require(user, minimum)
                    result = await self._execute(client, action, args)
                status = "accepted" if isinstance(result, dict) and result.get("status") == "accepted" else "ok"
                await self.store.finish_action(request, status)
                return result
            except TransportError:
                await self.store.finish_action(request, "failed" if action in READ_ONLY else "unknown")
                raise
            except BotError:
                await self.store.finish_action(request, "failed")
                raise
            except BaseException:
                await self.store.finish_action(request, "unknown")
                raise
        finally:
            self.active.discard(user)

    async def _execute(self, client: Luna, action: str, args: list[str]) -> Any:
        if action == "capabilities":
            d = await client.device()
            return {"model": d.model, "architecture": d.architecture, "features": sorted(d.features),
                    "ring_count": d.ring_count, "logo_count": d.logo_count}
        if action == "status":
            d = await client.device()
            return {"station": client.config.label, "model": d.model, "online": True}
        if action == "health":
            d = await client.device()
            return {"model": d.model, "sensors": await client.sensors()}
        if action == "volume_get":
            return await client.volume()
        if action == "volume":
            if len(args) != 1 or not args[0].isascii() or not args[0].isdigit():
                raise InvalidInput("/volume 0–100")
            return await client.volume(int(args[0]))
        if action == "led":
            if len(args) != 2:
                raise InvalidInput("/led ring|logo #RRGGBB|off")
            await client.led(args[0], None if args[1] == "off" else args[1])
            return "Подсветка: команда LUNA выполнена"
        if action in {"clock", "clock_get"}:
            if action == "clock" and len(args) != 1:
                raise InvalidInput("/clock ЧЧ:ММ|off")
            return await client.clock(args[0] if args else None)
        if action == "microphones":
            return await client.microphone_devices()
        if action == "record":
            if not 1 <= len(args) <= 2 or not args[0].isascii() or not args[0].isdigit():
                raise InvalidInput("/record 1–30 [microphone_id]")
            return await client.record(int(args[0]), args[1] if len(args) == 2 else None)
        if action == "audio_test":
            return await client.audio_test()
        if action == "plugins":
            return [{"id": p.get("manifest", {}).get("id"), "enabled": p.get("enabled"),
                     "compatible": p.get("compatible"), "running": p.get("running")}
                    for p in await client.plugins()]
        if action == "invoke":
            if len(args) != 1:
                raise InvalidInput("/invoke plugin_id")
            return await client.invoke(args[0])
        if action in {"media", "media_get"}:
            if action == "media" and len(args) != 1:
                raise InvalidInput("/media pause|resume|next|previous")
            return await client.media(args[0] if args else None)
        raise Unavailable("Функция не реализована подтверждённым контрактом LUNA; см. /features")


HELP = """Yandex Station Telegram Control Bot

/stations — выбор станции
/status — связь с LUNA
/volume [0–100] — громкость
/led ring|logo #RRGGBB|off
/clock [ЧЧ:ММ|off] — часы, если доступны
/health — модель и датчики
/capabilities — возможности runtime
/microphones — список каналов
/record 1–30 [id] — запись WAV в чат
/audio_test — тестовый звук (4 секунды)
/media [pause|resume|next|previous] — медиапровайдер
/plugins — установленные пакеты
/invoke id — запуск пакета (владелец)
/timer секунды — уведомление в Telegram
/timers — ваши таймеры
/cancel_timer id — отмена своего таймера
/history — журнал действий
/features — статус переноса всех функций
/access — управление доступом (владелец)
/help — эта справка

Управление только в личном чате. Перед записью убедитесь, что люди в комнате согласны."""


def format_result(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, indent=2)[:3800]


def feature_help() -> str:
    return parity_text()
