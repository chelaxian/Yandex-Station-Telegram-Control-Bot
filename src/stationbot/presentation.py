"""Telegram HTML cards. Device responses stay data, never become chat JSON."""
from __future__ import annotations

from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

TITLES = {
    "status": "📡 Статус станции", "volume": "🔉 Громкость", "volume_get": "🔉 Громкость",
    "health": "🩺 Диагностика", "system": "⚙️ Система", "fastfetch": "⚙️ Система",
    "network": "🌐 Проверка связи", "plugins": "📦 Пакеты", "media": "🎵 Плеер", "media_get": "🎵 Плеер",
    "sounds": "🎛 Саундборд", "scripts": "💻 Скрипты", "custom": "✨ Мои функции", "firmware": "📦 Образы",
    "history": "📜 История действий", "dialogs": "💬 Диалоги", "suggestions": "💡 Предложения",
    "timers": "⏰ Ваши таймеры", "microphones": "🎙 Микрофоны", "audio_jobs": "🎧 Воспроизведение",
    "capabilities": "🔎 Возможности станции", "clock": "🕒 Часы", "clock_get": "🕒 Часы",
    "screen": "🖥 Экран", "led": "🌈 Подсветка", "theme": "🔔 Звуковая тема", "theme_flags": "🔔 Настройки темы",
    "stop": "⏹ Остановка звука", "cleanup": "🧹 Очистка", "discover": "🔎 Поиск станций",
    "shell": "💻 Терминал", "run_script": "💻 Выполнение скрипта", "restore": "📥 Восстановление",
    "restore_legacy": "📥 Импорт бэкапа 2.7", "sound_add": "🎵 Звук сохранён", "upload_script": "📥 Скрипт загружен",
    "sound_delete": "🗑 Удаление звука", "script_delete": "🗑 Удаление скрипта", "custom_add": "✨ Функция сохранена",
    "timer": "⏱ Таймер установлен", "alarm": "⏰ Будильник установлен", "cancel_timer": "⏹ Отмена таймера",
    "ask": "💬 Ответ помощника", "suggest": "💡 Предложение", "legacy_history": "🗂 Прежняя история",
}
STATES = {"ok": "✅ Готово", "accepted": "⏳ Принято, ожидаем результат", "queued": "⏳ В очереди",
          "playing": "▶️ Воспроизводится", "succeeded": "✅ Завершено", "failed": "❌ Ошибка",
          "cancelled": "⏹ Отменено", "interrupted": "⚠️ Прервано", "unknown": "❔ Результат неизвестен",
          "pending": "⏳ Ожидает", "sent": "✅ Доставлено", "complete": "✅ Удалён"}


def safe(value, limit=300):
    text = str(value)
    return escape(text[:limit] + ("…" if len(text) > limit else ""))


def card(title: str, lines: list[str], station: str | None = None) -> str:
    result = [f"<b>{safe(title)}</b>"]
    if station:
        result.append(f"📍 {safe(station)}")
    result.append("")
    for line in lines:
        if sum(len(s) + 1 for s in result) + len(line) > 3800:
            result.append("… Показаны первые записи.")
            break
        result.append(line)
    return "\n".join(result)


def date(value, timezone="UTC"):
    try:
        return datetime.fromtimestamp(float(value), ZoneInfo(timezone)).strftime("%d.%m · %H:%M")
    except (ValueError, TypeError, OverflowError, OSError):
        return "—"


def size(value):
    try:
        number = float(value)
        return f"{number / 1048576:.1f} МиБ" if number >= 1048576 else f"{number / 1024:.1f} КиБ"
    except (ValueError, TypeError):
        return "—"


def result_card(action: str, value, station: str | None = None, timezone="UTC") -> str:
    title = TITLES.get(action, "✅ Результат действия")
    lines = []
    if action in {"theme", "theme_flags"} and isinstance(value, str):
        lines = ["✅ Настройки звуковой темы сохранены.", "Выберите тему, прослушайте её или измените переключатели ниже."]
    elif isinstance(value, str):
        lines = [safe(value, 2000)]
    elif action in {"volume", "volume_get"} and isinstance(value, dict):
        percent = value.get("percent")
        if type(percent) in {int, float} and 0 <= percent <= 100:
            filled = round(percent / 10)
            lines = [f"<b>{percent:g}%</b>", "🟦" * filled + "▫️" * (10 - filled), "Выберите комфортную громкость кнопками ниже."]
        else:
            lines = ["⚠️ Станция не сообщила текущую громкость."]
    elif action == "status" and isinstance(value, dict):
        lines = ["🟢 На связи" if value.get("online") else "🔴 Не отвечает",
                 f"Управление доступно через LUNA · runtime <b>{safe(value.get('runtime_version', 'неизвестен'))}</b>"]
    elif action in {"health", "system", "fastfetch"} and isinstance(value, dict):
        for sensor in value.get("sensors", []):
            kind, number = sensor.get("kind"), sensor.get("value")
            label = {"temperature": "🌡 Температура", "ambient_light": "💡 Освещённость"}.get(kind, "📊 Датчик")
            unit = {"celsius": "°C", "lux": "лк"}.get(sensor.get("unit"), sensor.get("unit", ""))
            lines.append(f"{label}: <b>{safe(number if number is not None else 'нет данных')} {safe(unit)}</b>")
        if isinstance(value.get("uptime"), str):
            try:
                seconds = int(float(value["uptime"].split()[0]))
                lines.append(f"⏱ Работает: <b>{seconds // 86400} дн. {seconds // 3600 % 24} ч. {seconds // 60 % 60} мин.</b>")
            except (ValueError, IndexError):
                pass
        if isinstance(value.get("memory"), str):
            import re
            memory = dict(re.findall(r"^(MemTotal|MemAvailable|MemFree):\s+(\d+)", value["memory"], re.MULTILINE))
            total = int(memory.get("MemTotal", 0))
            if total:
                free = int(memory.get("MemAvailable", memory.get("MemFree", 0)))
                lines.append(f"🧠 RAM: <b>{(total - free) / 1024:.0f} / {total / 1024:.0f} МиБ</b>")
        labels = {"uptime_seconds": "⏱ Время работы, с", "load": "⚡ Нагрузка CPU (1/5/15 мин)", "loadavg": "⚡ Нагрузка CPU", "wireless": "📶 Wi-Fi"}
        for key, label in labels.items():
            if key in value:
                item = value[key]
                if isinstance(item, dict):
                    item = " · ".join(f"{k}: {v}" for k, v in list(item.items())[:6])
                if key == "load" and isinstance(item, str):
                    item = " / ".join(item.split()[:3])
                lines.append(f"{label}: {safe(item, 450)}")
        if isinstance(value.get("network"), str):
            connections = [line.split() for line in value["network"].splitlines() if ":" in line]
            if connections and len(connections[0]) >= 4:
                lines.append(f"📶 Wi-Fi: <b>{safe(connections[0][3].rstrip('.'))} dBm</b>")
    elif action == "network" and isinstance(value, dict):
        lines = ["🟢 Связь со станцией установлена", f"⚡ Задержка: <b>{safe(value.get('luna_rtt_ms', '—'))} мс</b>"]
    elif action in {"media", "media_get"} and isinstance(value, dict):
        lines = (["🎵 Музыкальный провайдер подключён", f"Выбран: {safe(value.get('selected') or 'не выбран')}"] if value.get("providers") else ["Плеер пока не подключён.", "Для управления музыкой нужен настроенный медиапровайдер LUNA.", "Звуки и голосовые доступны в разделе «Саундборд»."])
        if value.get("status") == "accepted":
            lines = ["⏳ Команда передана плееру. Выполнение ещё не подтверждено."]
    elif action in {"shell", "run_script", "custom"} and isinstance(value, dict) and "exit_code" in value:
        lines = [f"{'✅' if value['exit_code'] == 0 else '⚠️'} Код завершения: <b>{safe(value['exit_code'])}</b>"]
        if value.get("timed_out"):
            lines.append("⌛ Превышено время выполнения")
        for key, label in [("stdout", "Вывод"), ("stderr", "Ошибки")]:
            if value.get(key):
                lines.append(f"<b>{label}</b>\n<pre>{safe(value[key], 650)}</pre>")
    elif isinstance(value, list):
        empty = {"plugins": "Пакеты пока не установлены.", "sounds": "Звуков пока нет. Добавьте первый аудиофайл кнопкой ниже.", "scripts": "Скриптов пока нет. Загрузите файл .sh.", "custom": "Пользовательских функций пока нет.", "firmware": "Сохранённых образов пока нет.", "history": "Вы ещё не выполняли действий.", "dialogs": "Диалогов пока нет. Задайте первый вопрос.", "timers": "Активных таймеров нет.", "suggestions": "Предложений пока нет.", "audio_jobs": "Аудиозаданий пока нет."}
        if not value:
            lines = [empty.get(action, "Записей пока нет.")]
        for entry in value[:15]:
            if not isinstance(entry, dict):
                lines.append(f"• {safe(entry)}")
                continue
            if action in {"sounds", "scripts", "firmware", "custom"}:
                lines.append(f"{'🎵' if action == 'sounds' else '📄'} <b>{safe(entry.get('name', 'Файл'))}</b> · {size(entry.get('bytes', 0))}")
            elif action == "plugins":
                lines.append(f"{'🟢' if entry.get('running') else '⚪'} <b>{safe(entry.get('id', 'Пакет'))}</b> · {'включён' if entry.get('enabled') else 'выключен'}")
            elif action == "history":
                name = TITLES.get(entry.get("action"), entry.get("action", "Действие"))
                lines.append(f"{safe(name)} · {STATES.get(entry.get('status'), '❔')}\n<i>{date(entry.get('created'), timezone)}</i>")
            elif action == "dialogs":
                lines.append(f"💬 <b>{safe(entry.get('question'), 180)}</b>\n{safe(entry.get('answer'), 500)}\n<i>{date(entry.get('created'), timezone)}</i>")
            elif action == "suggestions":
                lines.append(f"💡 {safe(entry.get('text'), 400)}\n<i>{date(entry.get('created'), timezone)}</i>")
            elif action == "timers":
                lines.append(f"⏰ <b>{date(entry.get('due'), timezone)}</b> · {STATES.get(entry.get('status'), '❔')}")
            elif action == "audio_jobs":
                lines.append(f"{STATES.get(entry.get('state'), '❔')} · временный файл: {STATES.get(entry.get('cleanup'), 'ожидает очистки')}")
            else:
                lines.append(f"• {safe(entry.get('name') or entry.get('id') or 'Запись')}")
    elif isinstance(value, dict):
        if "sha256" in value:
            lines = [f"📄 <b>{safe(value.get('name', 'Файл'))}</b>", f"Размер: {size(value.get('bytes', value.get('size', 0)))}", f"🔐 SHA-256\n<code>{safe(value['sha256'])}</code>"]
        elif "state" in value:
            lines = [STATES.get(value["state"], "⏳ Результат уточняется")]
            if type(value.get("station_volume_percent")) is int:
                lines.append(f"🔉 Громкость станции: <b>{value['station_volume_percent']}%</b>")
                lines.append(f"🎚 Уровень файла: <b>{value.get('playback_volume_percent', 0)}%</b>")
        elif action in {"clock", "clock_get"}:
            lines = ["🕒 Экран доступен" if value.get("available") else "У станции нет доступного экрана.", "Выберите пресет, яркость или введите своё время."]
        elif action == "capabilities":
            lines = ["Возможности определяются подключённой станцией.", f"📍 Модель: <code>{safe(value.get('model'))}</code>", f"🌈 Светодиоды: кольцо {safe(value.get('ring_count', 0))}, логотип {safe(value.get('logo_count', 0))}"]
        elif action == "discover":
            lines = [f"🔎 Найдено кандидатов: <b>{len(value.get('adb_candidates', []))}</b>", *[f"• {safe(x)}" for x in value.get("adb_candidates", [])[:10]], "Подключение и модель нужно проверить перед добавлением."]
        elif action == "stop":
            lines = ["⏹ Запрос остановки отправлен. Текущий результат доступен в списке воспроизведения."]
        elif action == "cleanup":
            lines = [f"🧹 Удалено временных файлов: <b>{safe(value.get('temporary_files_removed', 0))}</b>", "Ваши звуки, скрипты и настройки сохранены."]
        else:
            lines = ["✅ Запрос обработан."]
    else:
        lines = ["✅ Готово."]
    return card(title, lines or ["Данные пока недоступны."], station)
