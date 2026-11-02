"""User-bound Telegram controls and short-lived, station-bound input prompts."""
from __future__ import annotations

import secrets
import time
from collections import OrderedDict
from dataclasses import dataclass

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from .errors import InvalidInput
from .presentation import card, result_card, safe


@dataclass(frozen=True)
class Intent:
    user: int
    station: str
    mode: str
    action: str
    args: tuple[str, ...]
    once: bool
    expires: float


class Interface:
    def __init__(self, service):
        self.service = service
        self.buttons: OrderedDict[str, Intent] = OrderedDict()
        self.pending: dict[int, Intent] = {}

    def button(self, user, station, text, action, *args, mode="do", once=True):
        now = time.monotonic()
        while self.buttons and (next(iter(self.buttons.values())).expires <= now or len(self.buttons) >= 2048):
            self.buttons.popitem(last=False)
        token = secrets.token_urlsafe(9)
        self.buttons[token] = Intent(user, station, mode, action, tuple(args), once, now + 1800)
        return InlineKeyboardButton(text=text, callback_data="u:" + token)

    def resolve(self, token, user, station):
        intent = self.buttons.get(token)
        if intent is None or intent.expires <= time.monotonic():
            raise InvalidInput("Кнопка устарела. Откройте новое меню: /menu")
        if intent.user != user:
            raise InvalidInput("Эта кнопка предназначена другому пользователю")
        if intent.station != station:
            raise InvalidInput("Вы уже выбрали другую станцию. Откройте /menu")
        if intent.once:
            self.buttons.pop(token, None)
        return intent

    def prompt(self, intent):
        self.pending[intent.user] = Intent(intent.user, intent.station, "input", intent.action, intent.args, True, time.monotonic() + 600)

    def take_input(self, user, station):
        intent = self.pending.pop(user, None)
        if intent and (intent.expires <= time.monotonic() or intent.station != station):
            raise InvalidInput("Ввод отменён: время истекло или станция изменилась. Выберите действие заново.")
        return intent

    async def keyboard(self, user, station, page, value=None):
        role = await self.service.store.role(user)
        rows = []
        def button(label, action, *args, mode="do", owner=False):
            if mode not in {"page", "nav"} and (role == "viewer" or (owner and role != "owner")):
                return None
            return self.button(user, station, label, action, *args, mode=mode, once=mode not in {"page", "nav"})
        def row(*items):
            cells = [item for item in items if item]
            if cells:
                rows.append(cells)
        def page_button(label, target):
            return button(label, target, mode="page")
        def prompt(label, action, *args, owner=False):
            return button(label, action, *args, mode="input", owner=owner)
        if page in {"volume", "volume_get"}:
            row(*[button(f"{n}%", "volume", str(n)) for n in (0, 10, 25, 50)])
            row(*[button(f"{n}%", "volume", str(n)) for n in (60, 75, 90, 100)])
            row(prompt("🎚 Другая громкость", "volume"), page_button("🔄 Обновить", "volume"))
        elif page == "led":
            row(button("🔴 Красный", "led", "ring", "#FF0000"), button("🔵 Синий", "led", "ring", "#0088FF"), button("🟢 Зелёный", "led", "ring", "#00FF44"))
            row(button("🟣 Фиолетовый", "led", "ring", "#AA00FF"), button("⚪ Белый", "led", "ring", "#FFFFFF"))
            row(button("🌈 Радуга", "led_effect", "rainbow"), button("💓 Пульс", "led_effect", "pulse"), button("🚓 Мигалка", "led_effect", "police"))
            row(prompt("🎨 Свой цвет кольца", "led", "ring"), button("🔅 Штатная подсветка", "led_effect", "off"))
            device = await self.service.clients[station].device()
            if device.logo_count:
                row(prompt("✨ Цвет логотипа", "led", "logo"), button("✨ Штатный логотип", "led", "logo", "off"))
        elif page in {"clock", "screen", "clock_get"}:
            row(*[button(label, "screen", name) for label, name in [("1337", "1337"), ("😎 COOL", "cool"), ("🆘 HELP", "help")]])
            row(button("🐱 Кот", "screen", "cat"), button("😊 UwU", "screen", "uwu"), button("🌙 Ночной", "screen", "night"))
            row(prompt("🕒 Установить время", "clock"), prompt("✏️ Свой текст", "screen"))
            row(*[button(f"☀️ {n}%", "screen", "brightness", str(round(n * 255 / 100))) for n in (10, 50, 100)])
            row(button("↩️ Вернуть часы Алисе", "clock", "off"))
        elif page in {"record", "microphones"}:
            row(*[button(f"🎙 {n} сек", "record", str(n)) for n in (5, 10, 30)])
            row(prompt("⏱ Другая длительность", "record"), page_button("🎚 Микрофоны", "microphones"))
        elif page == "call":
            if station in self.service.interactions.calls:
                row(button("✅ Принять", "answer"), button("📴 Завершить", "hangup"))
            else:
                row(button("📞 Позвонить на станцию", "call"))
        elif page in {"theme", "theme_flags"}:
            for pairs in [[("🪟 Windows", "windows"), ("🌃 Cyberpunk", "cyberpunk")], [("🌀 Portal", "portal"), ("🍄 Mario", "mario")], [("🟣 Яндекс", "yandex"), ("🔕 Выключить", "off")]]:
                row(*[button(label, "theme", name) for label, name in pairs])
            settings = await self.service.features.theme_settings(self.service.clients[station])
            row(button("▶️ Прослушать", "theme_test"))
            row(button(f"{'✅' if settings['ask'] else '⚪'} Начало вопроса", "theme_flags", "ask", "off" if settings['ask'] else "on"), button(f"{'✅' if settings['reply'] else '⚪'} Начало ответа", "theme_flags", "reply", "off" if settings['reply'] else "on"))
        elif page == "tts":
            row(prompt("✏️ Написать текст", "tts"), button("⏹ Остановить", "stop"))
        elif page in {"sounds", "soundboard"}:
            for entry in (value or [])[:15]:
                if isinstance(entry, dict) and entry.get("name"):
                    row(button("▶️ " + entry["name"][:40], "play", entry["name"]))
            row(prompt("➕ Добавить звук", "sound_add"), button("⏹ Остановить", "stop"))
            row(prompt("🗑 Удалить звук", "sound_delete", owner=True), page_button("🔄 Обновить", "sounds"))
        elif page == "siren":
            row(*[button(f"🚨 {n} сек", "siren", str(n)) for n in (3, 10, 30)])
            row(button("🚫 Фейковый бан", "ban"), button("⏹ Остановить", "stop"))
        elif page in {"timer", "timers", "alarm"}:
            row(*[button(f"⏳ {label}", "timer", str(n)) for label, n in [("1 мин", 60), ("5 мин", 300), ("10 мин", 600)]])
            row(prompt("⏱ Свой таймер", "timer"), prompt("⏰ Будильник", "alarm"))
            row(page_button("📋 Активные таймеры", "timers"))
            for entry in (value or [])[:10]:
                if isinstance(entry, dict) and entry.get("id"):
                    row(button("❌ Отменить таймер", "cancel_timer", entry["id"]))
        elif page in {"backup", "firmware"}:
            row(button("📤 Скачать бэкап", "backup", owner=True), prompt("📥 Восстановить ZIP", "restore", owner=True))
            row(page_button("📦 Сохранённые образы", "firmware"), prompt("➕ Загрузить образ", "firmware", owner=True))
            row(prompt("📥 Импорт бэкапа 2.7", "restore_legacy", owner=True))
        elif page in {"terminal", "scripts", "custom", "run_script", "shell"}:
            row(prompt("⌨️ Выполнить команду", "shell", owner=True), prompt("📥 Загрузить .sh", "upload_script", owner=True))
            row(page_button("📜 Скрипты / мои функции", "scripts"))
            for entry in (value or [])[:12] if isinstance(value, list) else []:
                if isinstance(entry, dict) and entry.get("name"):
                    row(button("▶️ " + entry["name"][:35], "run_script", entry["name"], mode="confirm", owner=True))
        elif page in {"camera", "guard", "photo", "video"}:
            row(button("📸 Фото", "photo"), button("🎥 Видео 5 сек", "video", "5"))
            row(button("🛡 Включить охрану", "guard", "on"), button("🔓 Выключить охрану", "guard", "off"))
        elif page in {"ask", "dialogs", "legacy_history"}:
            row(prompt("💬 Задать вопрос", "ask"), page_button("📜 Диалоги", "dialogs"))
            row(page_button("🗂 Прежняя история", "legacy_history"))
        elif page in {"system", "health", "network", "cleanup", "discover"}:
            row(page_button("🩺 Датчики", "health"), page_button("🌐 Проверить связь", "network"))
            row(page_button("⚙️ Система", "system"), button("🧹 Очистить временные файлы", "cleanup", owner=True))
            row(prompt("🔎 Поиск в подсети", "discover", owner=True), page_button("📜 История действий", "history"))
            row(prompt("💡 Предложить улучшение", "suggest"), page_button("📬 Предложения", "suggestions"))
        elif page in {"media", "media_get"}:
            if isinstance(value, dict) and value.get("providers"):
                row(button("⏮", "media", "previous"), button("⏸ Пауза", "media", "pause"), button("▶️ Продолжить", "media", "resume"), button("⏭", "media", "next"))
            row(page_button("🎛 Саундборд", "sounds"), page_button("🔄 Обновить", "media_get"))
        elif page == "plugins":
            for entry in (value or [])[:15]:
                if entry.get("id") and entry.get("enabled") and entry.get("compatible"):
                    row(button("▶️ " + entry["id"][:35], "invoke", entry["id"], mode="confirm", owner=True))
        row(self.button(user, station, "🏠 Главное меню", "menu", mode="nav", once=False), self.button(user, station, "🔀 Станции", "stations", mode="nav", once=False))
        return InlineKeyboardMarkup(inline_keyboard=rows)

    async def panel(self, user, station, page, request):
        data_pages = {"volume": "volume_get", "soundboard": "sounds", "clock": "clock_get"}
        action = data_pages.get(page, page)
        if action in {"status", "volume_get", "health", "system", "network", "plugins", "media_get", "sounds", "scripts", "firmware", "clock_get", "microphones", "audio_jobs", "capabilities"}:
            value = await self.service.run(user, station, action, [], request)
            text = result_card(action, value, self.service.clients[station].config.label, self.service.config.timezone)
        else:
            value = None
            client = self.service.clients[station]
            descriptions = {
                "led": ("🌈 Подсветка", "Выберите цвет или эффект. Кнопка штатной подсветки вернёт управление Алисе."),
                "record": ("🎙 Запись комнаты", "Выберите длительность. Запись начнётся после нажатия и придёт файлом в этот чат."),
                "call": ("📞 Интерком", "Позвоните на станцию. После приёма звук комнаты приходит фрагментами, а ваши голосовые звучат на колонке."),
                "theme": ("🔔 Звуковые темы", "Выберите оформление звуков начала вопроса и ответа Алисы."),
                "tts": ("🎙 Голосовое и текст", "Отправьте голосовое сообщение или нажмите «Написать текст» — станция произнесёт его."),
                "siren": ("🚨 Сирена и эффекты", "Выберите длительность сирены или звуковой розыгрыш. Звук можно остановить кнопкой."),
                "timer": ("⏰ Таймер и будильник", "Выберите быстрый таймер или задайте своё время. По завершении придёт уведомление и прозвучит сигнал."),
                "backup": ("📦 Бэкап и образы", "Скачайте резервную копию или восстановите ZIP. Образы сохраняются с контрольной суммой; разделы не прошиваются."),
                "terminal": ("💻 Терминал и скрипты", "Выполняйте команды на выбранной станции и запускайте свои .sh-функции. Раздел доступен владельцу."),
                "camera": ("📸 Камера и охрана", "Снимок, короткое видео и обнаружение изменений изображения." if client.config.camera_input else "Камера пока не подключена. Для фото, видео и охраны владелец должен настроить источник камеры хоста."),
                "ask": ("💬 Помощник и диалоги", "Задайте вопрос локальному помощнику или откройте историю. Это отдельный помощник бота."),
            }
            title, description = descriptions.get(page, ("📋 Раздел", "Выберите действие кнопками ниже."))
            if page == "theme":
                settings = await self.service.features.theme_settings(client)
                description += "\n\nТекущая тема: " + {"off": "выключена", "windows": "Windows", "cyberpunk": "Cyberpunk", "portal": "Portal", "mario": "Mario", "yandex": "Яндекс"}[settings["theme"]]
            if page == "call":
                description += "\n\nСтатус: " + ("идёт вызов" if station in self.service.interactions.calls else "выключен")
            text = card(title, [safe(description, 1500)], client.config.label)
        return text, await self.keyboard(user, station, page, value)


PROMPTS = {
    "volume": "🔉 Отправьте число от 0 до 100.", "led": "🎨 Отправьте цвет в формате #RRGGBB, например #00AAFF.",
    "clock": "🕒 На какое время установить часы? Например: 12:34.", "screen": "✏️ Отправьте текст для экрана. Сегментные экраны поддерживают до четырёх символов ограниченного алфавита.",
    "record": "🎙 Сколько секунд записать? Отправьте число от 1 до 30.", "tts": "🗣 Что произнести? Отправьте текст следующим сообщением.",
    "timer": "⏱ Через сколько секунд напомнить? Например: 300.", "alarm": "⏰ Отправьте время 07:30 или длительность 10m / 30s / 1h.",
    "shell": "⌨️ Отправьте команду для терминала выбранной станции.", "ask": "💬 Напишите свой вопрос следующим сообщением.",
    "sound_add": "🎵 Отправьте MP3/WAV как файл. Он будет сохранён под именем вложения. Можно указать имя подписью: /sound_add name.wav.",
    "sound_delete": "🗑 Отправьте точное имя звука, который нужно удалить.", "upload_script": "📥 Отправьте текстовый файл .sh с простым латинским именем.",
    "restore": "📥 Отправьте ZIP-бэкап этого бота. Текущие файлы будут сохранены для отката.", "restore_legacy": "📥 Отправьте ZIP-бэкап прежнего бота 2.7.",
    "firmware": "📦 Отправьте файл .img или .bin. Образ будет сохранён с SHA-256, без прошивки.",
    "discover": "🔎 Отправьте частную подсеть /24, например 192.168.1.0/24.", "suggest": "💡 Напишите ваше предложение следующим сообщением.",
    "grant": "👥 Отправьте @username и роль: viewer (просмотр) или operator (управление). Например: @friend operator.",
}
