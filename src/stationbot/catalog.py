"""Every original feature has a tracked migration status; unavailable is never success."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Feature:
    name: str
    command: str
    status: str
    reason: str


FEATURES = (
    Feature("Громкость", "/volume", "implemented", "ALSA capability и живой ответ LUNA"),
    Feature("Подсветка", "/led", "implemented", "ring/logo по topology, release через LUNA"),
    Feature("Часы / экран", "/clock · /screen", "implemented", "Пресеты, текст поддерживаемого алфавита, яркость/ночь; сегменты только из живой topology"),
    Feature("Диагностика", "/health · /system", "implemented", "Датчики и opted-in owner/system: RAM, load, uptime, wireless"),
    Feature("Запись комнаты", "/record", "implemented", "1–30 секунд, только operator/owner, WAV только в памяти"),
    Feature("Плеер", "/media", "partial", "Только зарегистрированные медиапровайдеры, не штатный плеер Алисы"),
    Feature("Мои функции", "/custom · /plugins", "implemented", "Сохранённые .sh через owner tools и совместимые пакеты"),
    Feature("Таймер / будильник", "/timer · /alarm", "implemented", "SQLite, звук через audio jobs, уведомление; хост должен работать"),
    Feature("История действий", "/history", "implemented", "Журнал метаданных; содержание разговоров не собирается"),
    Feature("Управление доступом", "/access", "implemented", "Приглашение по username, подтверждение владельцем, привязка к ID"),
    Feature("Проверка сети", "/network", "implemented", "Доступность/RTT LUNA; ограничения интернета колонки сохраняются"),
    Feature("Интерком (назван VoIP в 2.7)", "/call · /answer · /hangup", "implemented", "Фрагменты комнаты, голосовой приём, предел 30 минут; не Telegram calls"),
    Feature("Саундборд / голосовое / TTS", "/sounds · /play · /tts", "implemented", "ffmpeg/espeak-ng на хосте; audio.jobs.v1 с конечным результатом и очисткой"),
    Feature("Темы / сирена / фейковый бан", "/theme · /siren · /ban · /stop", "implemented", "Автоматические темы по owner.speech.phase.v1, импортированные личные звуки или синтез"),
    Feature("Спросить помощника", "/ask", "implemented", "Как в 2.7: локальные намерения и энциклопедия; не облачная Алиса"),
    Feature("История диалогов", "/dialogs · /legacy_history", "implemented", "Диалоги помощника и read-only прежняя история"),
    Feature("Камера / фото / видео / охрана", "/photo · /video · /guard", "implemented", "Явно настроенная камера хоста, как в 2.7; не несуществующая камера колонки"),
    Feature("Образы / backup / restore", "/firmware · /backup · /restore", "implemented", "Сохранение образа с SHA-256 и ZIP прикладных данных; как в исходнике, без flash"),
    Feature("Терминал / загрузка скрипта", "/shell · /upload_script · /run_script", "implemented", "Owner tools включаются отдельно; timeout, ограниченный вывод, аудит"),
    Feature("Очистка / система", "/cleanup · /system", "implemented", "Только собственные временные файлы; неизвестные системные каталоги не удаляются"),
    Feature("Автопоиск IP", "/discover", "implemented", "Ограниченная частная подсеть; найденные ADB-порты — кандидаты, не идентификация модели"),
    Feature("Автономная установка на колонку", "", "partial", "Требует отдельного Python/runtime и квалификации автозапуска; сейчас используется мини-ПК"),
)


def parity_text() -> str:
    symbols = {"implemented": "✅", "partial": "◐", "blocked": "⏳"}
    return "\n".join(f"{symbols[f.status]} {f.name}: {f.command or f.reason}" for f in FEATURES)
