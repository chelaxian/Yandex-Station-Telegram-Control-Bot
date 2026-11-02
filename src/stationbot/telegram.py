from __future__ import annotations

import asyncio
import io
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher, Router
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    TelegramObject,
)

from .errors import BotError, Forbidden, InvalidInput
from .features import GUIDES
from .legacy_history import read_legacy_history
from .service import HELP, Service, feature_help, format_result

logger = logging.getLogger(__name__)


class AccessMiddleware(BaseMiddleware):
    def __init__(self, service: Service):
        self.service = service

    async def __call__(self, handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
                       event: TelegramObject, data: dict[str, Any]) -> Any:
        message = event.message if isinstance(event, CallbackQuery) else event
        user = getattr(event, "from_user", None)
        if not isinstance(message, Message) or message.chat.type != "private" or user is None:
            if isinstance(event, CallbackQuery):
                await event.answer("Только личный чат", show_alert=True)
            return None
        try:
            # Switching from MTProto/another poller can expose a Bot API backlog.
            # Never replay old physical commands after deployment or restart.
            if isinstance(event, Message) and event.date.timestamp() < self.service.started_at:
                return None
            role = await self.service.store.role(user.id)
            if role is None:
                # Only invited identities may create a claim. No automatic username authorization.
                if isinstance(event, Message) and (event.text or "").split()[0:1] == ["/start"]:
                    claimed = await self.service.store.claim(user.id, user.username)
                    await message.answer("Заявка ожидает подтверждения владельцем" if claimed else "Доступ не предоставлен")
                elif isinstance(event, CallbackQuery):
                    await event.answer("Доступ не предоставлен", show_alert=True)
                return None
            return await handler(event, data)
        except BotError as e:
            if isinstance(event, CallbackQuery):
                await message.answer(str(e))
            else:
                await event.answer(str(e))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # Telegram/network exceptions can embed a token-bearing URL. Log only the type.
            logger.error("handler_failed type=%s", type(e).__name__)
            await message.answer("Операция завершилась ошибкой. Неопределённые действия не повторяются автоматически.")
        return None


def markup(rows: list[list[tuple[str, str]]]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=text, callback_data=callback) for text, callback in row]
        for row in rows
    ])


async def main_menu(service: Service, user: int) -> tuple[str, InlineKeyboardMarkup]:
    station = await service.station_for(user)
    client = service.clients[station]
    label = client.config.label
    rows = [[("🔄 Статус", f"act:{station}:status"), ("🔀 Станции", "stations")]]
    try:
        device = await client.device()
        text = f"Yandex Station Telegram Control Bot\n{label} · {device.model}\nLUNA отвечает"
        text += f"\nИнтерком: {'включён' if station in service.interactions.calls else 'выкл'} · Охрана: {'включена' if station in service.interactions.guards else 'выкл'}"
        if "audio.volume.alsa" in device.features:
            rows.append([("🔉 Громкость", f"act:{station}:volume_get")])
        if "led.ring.rgb" in device.features and device.ring_count:
            rows.append([("🌈 Подсветка", f"guide:{station}:led")])
        # clock.available, not the model name or a substring in features, is authoritative.
        try:
            clock = await client.clock()
            if clock.get("available") is True:
                rows.append([("🕒 Часы", f"guide:{station}:clock")])
        except BotError:
            pass
        rows.append([("🩺 Диагностика", f"act:{station}:health")])
        if "microphone.capture" in device.features and await service.store.role(user) != "viewer":
            rows.append([("🎙 Запись комнаты", f"guide:{station}:record")])
        rows.append([("📦 Пакеты", f"act:{station}:plugins"), ("🎵 Плеер", f"act:{station}:media_get")])
    except BotError:
        text = f"Yandex Station Telegram Control Bot\n{label} · LUNA недоступна\nПроверьте runtime, модель и туннель."
    for row in [
        [("📞 Интерком", "call"), ("🔔 Звуковые темы", "theme")],
        [("🎙 Голосовое / TTS", "tts"), ("🎛 Саундборд", "soundboard")],
        [("🚨 Сирена / эффект", "siren"), ("⏰ Таймер / будильник", "timer")],
        [("📦 Бэкап / образы", "backup"), ("💻 Терминал / скрипты", "terminal")],
        [("📸 Камера / охрана", "camera"), ("💬 Диалоги", "ask")],
        [("⚙️ Система / сеть", "system")],
    ]:
        rows.append([(label, f"guide:{station}:{guide}") for label, guide in row])
    rows.append([("📋 Все функции", "features"), ("❔ Помощь", "help")])
    if user == service.config.owner_id:
        rows.append([("👥 Управление доступом", "access")])
    return text, markup(rows)


def make_dispatcher(service: Service) -> Dispatcher:
    dispatcher = Dispatcher()
    router = Router(name="station-control")
    guard = AccessMiddleware(service)
    router.message.outer_middleware(guard)
    router.callback_query.outer_middleware(guard)

    async def stations(message: Message) -> None:
        await message.answer("Выберите станцию:", reply_markup=markup([
            [(c.config.label, f"st:{key}")] for key, c in service.clients.items()
        ]))

    async def access(message: Message, user: int) -> None:
        await service.store.require(user, "owner")
        members = await service.store.rows("SELECT user_id,role FROM members ORDER BY user_id")
        claims = await service.store.rows("SELECT user_id,username,role FROM claims ORDER BY created")
        await message.answer("/grant @username viewer|operator — приглашение на 24 часа\n"
                             "Друг открывает /start, затем /approve ID\n"
                             "/revoke ID — отозвать доступ\n"
                             "Сверьте личность перед /approve; username можно передать другому.\n\n"
                             + format_result({"members": members, "claims": claims}))

    async def send_result(message: Message, value: Any, action: str = "record", station: str | None = None) -> None:
        if isinstance(value, bytes):
            if action == "photo":
                await message.answer_photo(BufferedInputFile(value, filename="photo.jpg"))
            elif action == "video":
                await message.answer_video(BufferedInputFile(value, filename="video.mp4"))
            else:
                await message.answer_document(BufferedInputFile(value, filename="backup.zip" if action == "backup" else "recording.wav"))
        elif isinstance(value, dict) and value.get("state") in {"queued", "playing"} and "id" in value and station:
            await message.answer("Аудиозадание принято. Результат придёт после завершения; /stop — остановить.")
            service.interactions.watch_audio(message, station, value["id"])
        else:
            await message.answer(format_result(value))

    @router.message()
    async def on_message(message: Message) -> None:
        assert message.from_user is not None
        user = message.from_user.id
        text = message.text or message.caption or ""
        if len(text) > 2048:
            raise InvalidInput("Слишком длинная команда")
        tokens = text.split()
        station = await service.station_for(user)
        attachment = message.voice or message.audio or message.document
        if attachment:
            await service.store.require(user, "operator")
            command = tokens[0].split("@", 1)[0].lstrip("/") if tokens else "play_upload"
            if command not in {"play_upload", "sound_add", "restore", "restore_legacy", "firmware", "upload_script"}:
                raise InvalidInput("Подпись: /sound_add name.wav, /upload_script name.sh, /firmware name.bin или /restore")
            if command in {"restore", "restore_legacy", "firmware", "upload_script"}:
                await service.store.require(user, "owner")
            if not attachment.file_size or attachment.file_size > 20 * 1024 * 1024:
                raise InvalidInput("Вложение не должно превышать 20 МиБ")
            stream = io.BytesIO()
            assert message.bot
            await message.bot.download(attachment.file_id, destination=stream, timeout=60)
            if stream.tell() > 20 * 1024 * 1024:
                raise InvalidInput("Вложение превышает лимит")
            result = await service.run(user, station, command, tokens[1:],
                                       f"m:{message.chat.id}:{message.message_id}", stream.getvalue())
            await send_result(message, result, command, station)
            return
        if not tokens:
            await message.answer("Откройте /menu")
            return
        command, args = tokens[0].split("@", 1)[0].lstrip("/"), tokens[1:]
        station = await service.station_for(user)
        if command in {"start", "menu"}:
            title, buttons = await main_menu(service, user)
            await message.answer(title, reply_markup=buttons)
        elif command == "help":
            await message.answer(HELP)
        elif command == "features":
            await message.answer(feature_help())
        elif command in {"stations", "station"}:
            if args:
                if len(args) != 1 or args[0] not in service.clients:
                    raise InvalidInput("Неизвестная станция; используйте /stations")
                await service.store.select(user, args[0])
                title, buttons = await main_menu(service, user)
                await message.answer(title, reply_markup=buttons)
            else:
                await stations(message)
        elif command == "access":
            await access(message, user)
        elif command == "grant":
            if len(args) != 2:
                raise InvalidInput("/grant @username viewer|operator")
            await service.store.invite(user, args[0], args[1])
            await message.answer("Приглашение создано. После /start друга проверьте /access и подтвердите /approve ID.")
        elif command in {"approve", "revoke"}:
            if len(args) != 1 or not args[0].isascii() or not args[0].isdigit():
                raise InvalidInput(f"/{command} ID")
            if command == "approve":
                await service.store.approve(user, int(args[0]))
            else:
                await service.store.revoke(user, int(args[0]))
            await message.answer("Права обновлены")
        elif command == "history":
            history = await service.store.rows(
                "SELECT station,action,status,created FROM actions WHERE user_id=? ORDER BY created DESC LIMIT 20", (user,))
            await message.answer(format_result(history))
        elif command == "legacy_history":
            await service.store.require(user, "owner")
            await message.answer(await asyncio.to_thread(read_legacy_history, service.config.legacy_history_dir, station))
        elif command == "timer":
            await service.store.require(user, "operator")
            if len(args) != 1 or not args[0].isascii() or not args[0].isdigit():
                raise InvalidInput("/timer 1–86400 — уведомление в Telegram")
            key = await service.store.timer(user, message.chat.id, station, int(args[0]))
            await message.answer(f"Таймер {key} сохранён; уведомление придёт в Telegram")
        elif command == "alarm":
            import datetime
            from zoneinfo import ZoneInfo
            await service.store.require(user, "operator")
            if len(args) != 1:
                raise InvalidInput("/alarm ЧЧ:ММ")
            try:
                clock = datetime.datetime.strptime(args[0], "%H:%M").time()
                now = datetime.datetime.now(ZoneInfo(service.config.timezone))
                target = datetime.datetime.combine(now.date(), clock, tzinfo=now.tzinfo)
                if target <= now:
                    target += datetime.timedelta(days=1)
            except (IndexError, ValueError) as e:
                raise InvalidInput("/alarm ЧЧ:ММ — часовой пояс из настроек бота") from e
            key = await service.store.timer(user, message.chat.id, station, max(1, int((target-now).total_seconds())))
            await message.answer(f"Будильник {key}: {target.isoformat(timespec='minutes')}")
        elif command in {"call", "answer", "hangup", "guard", "led_effect"}:
            await service.store.require(user, "operator")
            request = f"m:{message.chat.id}:{message.message_id}"
            if not await service.store.begin_action(request, user, station, command):
                raise InvalidInput("Эта команда уже обработана")
            try:
                await service.interactions.command(message, user, station, command, args)
                await service.store.finish_action(request, "accepted")
            except BaseException:
                await service.store.finish_action(request, "unknown")
                raise
        elif command == "suggest":
            await service.store.require(user, "operator")
            if not args:
                raise InvalidInput("/suggest текст предложения")
            await service.store.write("INSERT INTO suggestions VALUES (?,?,?)", (user, " ".join(args), time.time()))
            await message.answer("Предложение сохранено")
        elif command == "dialogs":
            await service.store.require(user, "owner")
            result = await service.store.rows("SELECT question,answer,created FROM dialogs WHERE station=? ORDER BY created DESC LIMIT 10", (station,))
            await message.answer(format_result(result))
        elif command == "ask":
            await service.store.require(user, "operator")
            from .assistant import answer
            client = service.clients[station]
            request = f"m:{message.chat.id}:{message.message_id}"
            if not await service.store.begin_action(request, user, station, "ask"):
                raise InvalidInput("Вопрос уже обработан")
            try:
                async with client.operation_lock:
                    await service.store.require(user, "operator")
                    result = await answer(client, " ".join(args))
                await service.store.write("INSERT INTO dialogs VALUES (?,?,?,?)", (station, " ".join(args), result, time.time()))
                await service.store.finish_action(request, "ok")
            except BaseException:
                await service.store.finish_action(request, "unknown")
                raise
            await message.answer("Локальный помощник (как в 2.7):\n" + result)
        elif command == "timers":
            result = await service.store.rows("SELECT id,station,due,status FROM timers WHERE user_id=? AND status IN ('pending','unknown')", (user,))
            await message.answer(format_result(result))
        elif command == "cancel_timer":
            if len(args) != 1:
                raise InvalidInput("/cancel_timer ID")
            assert service.store.db is not None
            await service.store.write("UPDATE timers SET status='cancelled' WHERE id=? AND user_id=? AND status='pending'", (args[0], user))
            await message.answer("Запрос отмены своего таймера обработан")
        else:
            if command == "listen" and not args:
                command, args = "record", ["10"]
            mapped = {"volume": "volume_get", "clock": "clock_get", "media": "media_get"}
            action = mapped.get(command, command) if not args else command
            request = f"m:{message.chat.id}:{message.message_id}"
            value = await service.run(user, station, action, args, request)
            await send_result(message, value, command, station)

    @router.callback_query()
    async def on_callback(query: CallbackQuery) -> None:
        assert isinstance(query.message, Message)
        user = query.from_user.id
        await query.answer()
        value = query.data or ""
        if value == "stations":
            await stations(query.message)
        elif value == "help":
            await query.message.answer(HELP)
        elif value == "features":
            await query.message.answer(feature_help())
        elif value == "access":
            await access(query.message, user)
        elif value.startswith("st:"):
            station = value[3:]
            if station not in service.clients:
                raise InvalidInput("Станция отсутствует в конфигурации")
            await service.store.select(user, station)
            title, buttons = await main_menu(service, user)
            await query.message.answer(title, reply_markup=buttons)
        elif value.startswith("guide:"):
            _, station, action = value.split(":", 2)
            if station not in service.clients:
                raise InvalidInput("Неизвестная станция")
            # A guide does not silently change the selected station.
            selected = await service.station_for(user)
            if selected != station:
                raise InvalidInput("Это меню другой станции. Откройте /menu заново")
            guides = {**GUIDES, "led": "/led ring #00AAFF\n/led ring off — вернуть штатное управление\n/led_effect rainbow|pulse|police|off",
                      "clock": "/clock 12:34\n/clock off — вернуть управление",
                      "record": "/record 10 — запись в личный чат\n/microphones — каналы"}
            await query.message.answer(guides.get(action, HELP))
        elif value.startswith("act:"):
            _, station, action = value.split(":", 2)
            # Callback actions are read-only. Mutations require an explicit command.
            if action not in {"status", "volume_get", "health", "plugins", "media_get"}:
                raise Forbidden("Недопустимая кнопка")
            result = await service.run(user, station, action, [], f"c:{query.id}")
            await send_result(query.message, result)
        else:
            raise InvalidInput("Кнопка устарела; откройте /menu")

    dispatcher.include_router(router)
    return dispatcher


async def timer_worker(service: Service, bot: Bot) -> None:
    next_prune = 0.0
    while True:
        if time.monotonic() >= next_prune:
            await service.store.prune(service.config.audit_days)
            next_prune = time.monotonic() + 3600
        for timer in await service.store.due_timers():
            try:
                await service.store.require(timer["user_id"], "operator")
                client = service.clients.get(timer["station"])
                if client is None:
                    raise InvalidInput("Станция удалена")
                late = time.time() - timer["due"]
                audio_status = ""
                if late <= 60:
                    try:
                        from .audio import effect
                        await client.play(await asyncio.to_thread(effect, "alarm", 3), f"timer-{timer['id']}")
                    except BotError:
                        audio_status = " · звук недоступен"
                await bot.send_message(timer["chat_id"], f"⏰ Таймер {timer['id']} · {client.config.label}"
                                       + audio_status
                                       + (f" (доставка после перезапуска, задержка {int(late)} с)" if late > 10 else ""))
                await service.store.finish_timer(timer["id"], "sent")
            except Forbidden:
                await service.store.finish_timer(timer["id"], "cancelled")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("timer_delivery_unknown type=%s", type(e).__name__)
                await service.store.finish_timer(timer["id"], "unknown")
        await asyncio.sleep(1)
