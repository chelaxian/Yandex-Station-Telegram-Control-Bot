from __future__ import annotations

import asyncio
import io
import logging
import time
import wave
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
from .legacy_history import read_legacy_history
from .presentation import card, result_card, safe
from .service import OWNER_ONLY, Service
from .ui import PROMPTS, Interface

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
            await message.answer(card("⚠️ Не удалось выполнить действие", [safe(e)]), parse_mode="HTML",
                                 reply_markup=markup([[("🏠 Главное меню", "home")]]))
        except asyncio.CancelledError:
            raise
        except Exception as e:
            # Telegram/network exceptions can embed a token-bearing URL. Log only the type.
            logger.error("handler_failed type=%s", type(e).__name__)
            await message.answer(card("⚠️ Действие не завершено", ["Проверьте связь и откройте меню. Результат действия пока неизвестен."]), parse_mode="HTML", reply_markup=markup([[("🏠 Главное меню", "home")]]))
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
        text = card("🏠 Управление станцией", ["🟢 На связи", f"📞 Интерком: {'включён' if station in service.interactions.calls else 'выкл'}", f"🛡 Охрана: {'включена' if station in service.interactions.guards else 'выкл'}", "", "Выберите раздел ниже 👇"], label)
        if "audio.volume.alsa" in device.features:
            rows.append([("🔉 Громкость", f"act:{station}:volume_get")])
        if (("led.ring.rgb" in device.features and device.ring_count)
                or ("led.logo" in device.features and device.logo_count)):
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
        text = card("🏠 Управление станцией", ["🔴 Станция не отвечает", "Проверьте подключение. Когда связь восстановится, нажмите «Статус»."], label)
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
    ui = Interface(service)
    dispatcher["interface"] = ui
    router = Router(name="station-control")
    guard = AccessMiddleware(service)
    router.message.outer_middleware(guard)
    router.callback_query.outer_middleware(guard)

    async def stations(message: Message) -> None:
        await message.answer(card("🔀 Выбор станции", ["Какой станцией хотите управлять?"]), parse_mode="HTML", reply_markup=markup([
            [(c.config.label, f"st:{key}")] for key, c in service.clients.items()
        ]))

    async def access(message: Message, user: int) -> None:
        await service.store.require(user, "owner")
        members = await service.store.rows("SELECT user_id,role FROM members ORDER BY user_id")
        claims = await service.store.rows("SELECT user_id,username,role FROM claims ORDER BY created")
        station = await service.station_for(user)
        rows = [[ui.button(user, station, "➕ Пригласить друга", "grant", mode="input")]]
        lines = ["Пригласите друга по имени пользователя. После его запуска бота здесь появится заявка.", "", "<b>Участники</b>"]
        lines += [f"👤 <code>{m['user_id']}</code> · {'просмотр' if m['role'] == 'viewer' else 'управление'}" for m in members] or ["Пока доступ есть только у вас."]
        for member in members[:15]:
            rows.append([ui.button(user, station, f"🚫 Отозвать доступ {member['user_id']}", "revoke", str(member["user_id"]), mode="confirm")])
        lines += ["", "<b>Заявки</b>"]
        lines += [f"🙋 @{safe(c['username'])} · <code>{c['user_id']}</code>" for c in claims[:15]] or ["Новых заявок нет."]
        for claim in claims[:15]:
            rows.append([ui.button(user, station, f"✅ Подтвердить @{claim['username']}", "approve", str(claim["user_id"]), mode="confirm")])
        lines += ["", "Подтверждайте заявку после проверки личности друга."]
        rows += (await ui.keyboard(user, station, "access")).inline_keyboard
        await message.answer(card("👥 Управление доступом", lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    async def show_help(message, user, station, features=False):
        sections = [[("📡 Статус", "status"), ("🔉 Громкость", "volume")], [("🌈 Подсветка", "led"), ("🩺 Диагностика", "health")],
                    [("🎙 Запись", "record"), ("📞 Интерком", "call")], [("🎛 Саундборд", "sounds"), ("🗣 Голос / текст", "tts")],
                    [("🔔 Темы", "theme"), ("🚨 Эффекты", "siren")], [("⏰ Таймеры", "timer"), ("📦 Бэкап", "backup")],
                    [("💻 Скрипты", "terminal"), ("📸 Камера", "camera")], [("💬 Помощник", "ask"), ("⚙️ Система", "system")]]
        rows = [[ui.button(user, station, label, page, mode="page", once=False) for label, page in row] for row in sections]
        rows += (await ui.keyboard(user, station, "help")).inline_keyboard
        lines = ["Управляйте станцией кнопками. Для текста или файла бот подскажет, что отправить следующим сообщением.", "", "Для отмены ввода нажмите «Главное меню» или отправьте /cancel."]
        if features:
            lines += ["", "ℹ️ Штатный музыкальный провайдер и автономная установка ещё в разработке. Камера требует настроенного источника."]
        await message.answer(card("📋 Все разделы" if features else "❔ Как пользоваться", lines), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))

    async def show_page(message, user, station, page, request, edit=False):
        if page in {"timers", "history", "dialogs", "legacy_history", "suggestions", "access"}:
            await dispatch_command(message, user, station, page, [], request)
            return
        if page in {"terminal", "backup", "firmware", "scripts"}:
            await service.store.require(user, "owner")
        text, buttons = await ui.panel(user, station, page, request)
        if edit:
            await message.edit_text(text, parse_mode="HTML", reply_markup=buttons)
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=buttons)

    async def send_result(message: Message, value: Any, action: str, station: str, user: int) -> None:
        label = service.clients[station].config.label
        page = {"play": "sounds", "sound_add": "sounds", "sound_delete": "sounds", "tts": "tts", "siren": "siren", "ban": "siren", "theme_test": "theme", "upload_script": "scripts", "restore": "backup", "stop": "tts", "cancel_timer": "timers"}.get(action, action)
        buttons = await ui.keyboard(user, station, page, value)
        if isinstance(value, bytes):
            lines = ["Файл отправлен в этот чат."]
            if action == "record":
                with wave.open(io.BytesIO(value), "rb") as recording:
                    duration = recording.getnframes() / recording.getframerate()
                lines.insert(0, f"⏱ Длительность записи: {duration:.2f} сек.")
            caption = card({"photo": "📸 Снимок готов", "video": "🎥 Видео готово", "backup": "📦 Резервная копия готова"}.get(action, "🎙 Запись готова"), lines, label)
            if action == "photo":
                await message.answer_photo(BufferedInputFile(value, filename="photo.jpg"), caption=caption, parse_mode="HTML", reply_markup=buttons)
            elif action == "video":
                await message.answer_video(BufferedInputFile(value, filename="video.mp4"), caption=caption, parse_mode="HTML", reply_markup=buttons)
            else:
                await message.answer_document(BufferedInputFile(value, filename="backup.zip" if action == "backup" else "recording.wav"), caption=caption, parse_mode="HTML", reply_markup=buttons)
        elif isinstance(value, dict) and value.get("state") in {"queued", "playing"} and "id" in value and station:
            await message.answer(card("🎧 Воспроизведение", ["⏳ Звук передан станции. Сообщу, когда воспроизведение завершится."], label), parse_mode="HTML", reply_markup=await ui.keyboard(user, station, "tts"))
            service.interactions.watch_audio(message, station, value["id"])
        else:
            await message.answer(result_card(action, value, label, service.config.timezone), parse_mode="HTML", reply_markup=buttons)

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
            pending = ui.take_input(user, station) if not tokens or not tokens[0].startswith("/") else None
            command = tokens[0].split("@", 1)[0].lstrip("/") if tokens and tokens[0].startswith("/") else pending.action if pending else "play_upload"
            upload_args = tokens[1:] if tokens and tokens[0].startswith("/") else list(pending.args) if pending else []
            if command in {"sound_add", "upload_script", "firmware"} and not upload_args:
                from pathlib import PurePosixPath
                name = PurePosixPath(getattr(attachment, "file_name", "") or "sound.wav").name
                upload_args = [str(PurePosixPath(name).with_suffix(".wav")) if command == "sound_add" else name]
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
            result = await service.run(user, station, command, upload_args,
                                       f"m:{message.chat.id}:{message.message_id}", stream.getvalue())
            await send_result(message, result, command, station, user)
            return
        if not tokens:
            await message.answer("Откройте /menu")
            return
        if tokens[0].startswith("/"):
            ui.pending.pop(user, None)
            command, args = tokens[0].split("@", 1)[0].lstrip("/"), tokens[1:]
        else:
            pending = ui.take_input(user, station)
            if pending is None:
                await show_help(message, user, station)
                return
            command, args = pending.action, [*pending.args, *tokens]
        await dispatch_command(message, user, station, command, args, f"m:{message.chat.id}:{message.message_id}")

    async def dispatch_command(message: Message, user: int, station: str, command: str, args: list[str], request: str, edit=False) -> None:
        sections = {"led": "led", "record": "record", "theme": "theme", "siren": "siren", "timer": "timer", "alarm": "timer", "screen": "clock", "tts": "tts", "shell": "terminal", "ask": "ask"}
        if not args and command in sections:
            await show_page(message, user, station, sections[command], request, edit=edit)
        elif command in {"start", "menu", "cancel"}:
            ui.pending.pop(user, None)
            title, buttons = await main_menu(service, user)
            if edit:
                await message.edit_text(title, parse_mode="HTML", reply_markup=buttons)
            else:
                await message.answer(title, parse_mode="HTML", reply_markup=buttons)
        elif command == "help":
            await show_help(message, user, station)
        elif command == "features":
            await show_help(message, user, station, features=True)
        elif command in {"stations", "station"}:
            if args:
                if len(args) != 1 or args[0] not in service.clients:
                    raise InvalidInput("Неизвестная станция; используйте /stations")
                await service.store.select(user, args[0])
                title, buttons = await main_menu(service, user)
                await message.answer(title, parse_mode="HTML", reply_markup=buttons)
            else:
                await stations(message)
        elif command == "access":
            await access(message, user)
        elif command == "grant":
            if len(args) != 2:
                raise InvalidInput("/grant @username viewer|operator")
            await service.store.invite(user, args[0], args[1])
            await message.answer(card("👥 Приглашение создано", ["✅ Попросите друга открыть бота и нажать «Старт». После этого подтвердите его заявку в разделе доступа."]), parse_mode="HTML", reply_markup=markup([[("👥 Управление доступом", "access"), ("🏠 Меню", "home")]]))
        elif command in {"approve", "revoke"}:
            if len(args) != 1 or not args[0].isascii() or not args[0].isdigit():
                raise InvalidInput(f"/{command} ID")
            if command == "approve":
                await service.store.approve(user, int(args[0]))
            else:
                await service.store.revoke(user, int(args[0]))
            await access(message, user)
        elif command == "history":
            history = await service.store.rows(
                "SELECT station,action,status,created FROM actions WHERE user_id=? ORDER BY created DESC LIMIT 20", (user,))
            await send_result(message, history, "history", station, user)
        elif command == "legacy_history":
            await service.store.require(user, "owner")
            await send_result(message, await asyncio.to_thread(read_legacy_history, service.config.legacy_history_dir, station), "legacy_history", station, user)
        elif command == "timer":
            await service.store.require(user, "operator")
            if len(args) != 1 or not args[0].isascii() or not args[0].isdigit():
                raise InvalidInput("/timer 1–86400 — уведомление в Telegram")
            await service.store.timer(user, message.chat.id, station, int(args[0]))
            await send_result(message, f"✅ Напомню через {int(args[0])} секунд. Уведомление придёт в этот чат.", "timer", station, user)
        elif command == "alarm":
            import datetime
            from zoneinfo import ZoneInfo
            await service.store.require(user, "operator")
            if len(args) != 1:
                raise InvalidInput("/alarm ЧЧ:ММ|10m|30s|1h")
            import re
            duration = re.fullmatch(r"([0-9]{1,5})([smh])", args[0])
            if duration:
                seconds = int(duration[1]) * {"s": 1, "m": 60, "h": 3600}[duration[2]]
                await service.store.timer(user, message.chat.id, station, seconds)
                await send_result(message, f"✅ Будильник установлен: через {seconds} секунд.", "alarm", station, user)
                return
            try:
                clock = datetime.datetime.strptime(args[0], "%H:%M").time()
                now = datetime.datetime.now(ZoneInfo(service.config.timezone))
                target = datetime.datetime.combine(now.date(), clock, tzinfo=now.tzinfo)
                if target <= now:
                    target += datetime.timedelta(days=1)
            except (IndexError, ValueError) as e:
                raise InvalidInput("/alarm ЧЧ:ММ — часовой пояс из настроек бота") from e
            await service.store.timer(user, message.chat.id, station, max(1, int((target-now).total_seconds())))
            await send_result(message, f"✅ Будильник установлен на {target:%d.%m · %H:%M}.\nЧасовой пояс: {service.config.timezone}", "alarm", station, user)
        elif command in {"call", "answer", "hangup", "guard", "led_effect"}:
            await service.store.require(user, "operator")
            if not await service.store.begin_action(request, user, station, command):
                raise InvalidInput("Эта команда уже обработана")
            try:
                await service.interactions.command(message, user, station, command, args)
                await service.store.finish_action(request, "accepted")
                page = {"call": "call", "answer": "call", "hangup": "call", "guard": "camera", "led_effect": "led"}[command]
                await show_page(message, user, station, page, request + ":panel")
            except BaseException:
                await service.store.finish_action(request, "unknown")
                raise
        elif command == "suggestions":
            await service.store.require(user, "owner")
            await send_result(message, await service.store.rows("SELECT user_id,text,created FROM suggestions ORDER BY created DESC LIMIT 20"), "suggestions", station, user)
        elif command == "suggest":
            await service.store.require(user, "operator")
            if not args:
                raise InvalidInput("/suggest текст предложения")
            await service.store.write("INSERT INTO suggestions VALUES (?,?,?)", (user, " ".join(args), time.time()))
            await send_result(message, "💡 Спасибо! Предложение сохранено для владельца.", "suggest", station, user)
        elif command == "dialogs":
            await service.store.require(user, "owner")
            result = await service.store.rows("SELECT question,answer,created FROM dialogs WHERE station=? ORDER BY created DESC LIMIT 10", (station,))
            await send_result(message, result, command, station, user)
        elif command == "ask":
            await service.store.require(user, "operator")
            from .assistant import answer
            client = service.clients[station]
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
            await send_result(message, result, "ask", station, user)
        elif command == "timers":
            result = await service.store.rows("SELECT id,station,due,status FROM timers WHERE user_id=? AND status IN ('pending','unknown')", (user,))
            await send_result(message, result, command, station, user)
        elif command == "cancel_timer":
            if len(args) != 1:
                raise InvalidInput("/cancel_timer ID")
            assert service.store.db is not None
            await service.store.write("UPDATE timers SET status='cancelled' WHERE id=? AND user_id=? AND status='pending'", (args[0], user))
            await send_result(message, "⏹ Запрос отмены таймера обработан.", "cancel_timer", station, user)
        else:
            if command == "listen" and not args:
                command, args = "record", ["10"]
            mapped = {"volume": "volume_get", "clock": "clock_get", "media": "media_get"}
            action = mapped.get(command, command) if not args else command
            value = await service.run(user, station, action, args, request)
            if command == "theme":
                await service.interactions.configure_theme(user, station)
            await send_result(message, value, command, station, user)

    @router.callback_query()
    async def on_callback(query: CallbackQuery) -> None:
        assert isinstance(query.message, Message)
        user, message = query.from_user.id, query.message
        await query.answer()
        value = query.data or ""
        station = await service.station_for(user)
        if value.startswith("u:"):
            intent = ui.resolve(value[2:], user, station)
            ui.pending.pop(user, None)
            if intent.mode == "nav":
                ui.pending.pop(user, None)
                await dispatch_command(message, user, station, intent.action, [], f"c:{query.id}", edit=True)
            elif intent.mode == "page":
                await show_page(message, user, station, intent.action, f"c:{query.id}", edit=True)
            elif intent.mode == "input":
                await service.store.require(user, "owner" if intent.action in OWNER_ONLY or intent.action == "grant" else "operator")
                ui.prompt(intent)
                await message.answer(card("✍️ Жду ваше сообщение", [safe(PROMPTS.get(intent.action, "Отправьте значение следующим сообщением.")), "", "Отмена: /cancel или кнопка ниже."], service.clients[station].config.label), parse_mode="HTML", reply_markup=await ui.keyboard(user, station, "input"))
            elif intent.mode == "confirm":
                await service.store.require(user, "owner")
                confirm = ui.button(user, station, "✅ Подтвердить", intent.action, *intent.args)
                rows = [[confirm], *(await ui.keyboard(user, station, "confirm")).inline_keyboard]
                title = {"run_script": "💻 Запустить скрипт?", "invoke": "📦 Запустить пакет?", "approve": "👥 Подтвердить доступ?", "revoke": "🚫 Отозвать доступ?"}.get(intent.action, "Подтверждение действия")
                await message.answer(card(title, [f"<b>{safe(' '.join(intent.args))}</b>", "Проверьте выбранную станцию и данные перед выполнением."], service.clients[station].config.label), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=rows))
            else:
                await dispatch_command(message, user, station, intent.action, list(intent.args), f"c:{query.id}")
        elif value in {"home", "stations", "help", "features", "access"}:
            ui.pending.pop(user, None)
            await dispatch_command(message, user, station, "menu" if value == "home" else value, [], f"c:{query.id}", edit=True)
        elif value.startswith("st:"):
            await dispatch_command(message, user, station, "station", [value[3:]], f"c:{query.id}")
        elif value.startswith("guide:") or value.startswith("act:"):
            kind, target, action = value.split(":", 2)
            if target != station:
                raise InvalidInput("Это меню другой станции. Откройте /menu заново")
            if kind == "act" and action not in {"status", "volume_get", "health", "plugins", "media_get"}:
                raise Forbidden("Недопустимая кнопка")
            await show_page(message, user, station, action, f"c:{query.id}", edit=True)
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
                lines = ["Время вышло!" + audio_status]
                if late > 10:
                    lines.append(f"Уведомление доставлено с задержкой {int(late)} сек.")
                await bot.send_message(timer["chat_id"], card("⏰ Таймер завершён", [safe(line) for line in lines], client.config.label), parse_mode="HTML", reply_markup=markup([[("⏰ Таймеры", f"guide:{timer['station']}:timer"), ("🏠 Главное меню", "home")]]))
                await service.store.finish_timer(timer["id"], "sent")
            except Forbidden:
                await service.store.finish_timer(timer["id"], "cancelled")
            except asyncio.CancelledError:
                raise
            except Exception as e:
                logger.warning("timer_delivery_unknown type=%s", type(e).__name__)
                await service.store.finish_timer(timer["id"], "unknown")
        await asyncio.sleep(1)
