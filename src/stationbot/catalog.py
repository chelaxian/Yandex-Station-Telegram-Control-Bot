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
    Feature("Часы", "/clock", "implemented", "Только при clock.available=true; без выдуманной бегущей строки"),
    Feature("Диагностика", "/health", "partial", "Устройство и датчики; CPU/RAM/Flash/RSSI API отсутствует"),
    Feature("Запись комнаты", "/record", "implemented", "1–30 секунд, только operator/owner, WAV только в памяти"),
    Feature("Плеер", "/media", "partial", "Только зарегистрированные медиапровайдеры, не штатный плеер Алисы"),
    Feature("Мои функции", "/plugins", "partial", "Запуск установленных совместимых пакетов, выключен по умолчанию"),
    Feature("Таймер", "/timer", "partial", "Устойчивое уведомление в Telegram; не будильник на выключенном хосте"),
    Feature("История действий", "/history", "implemented", "Журнал метаданных; содержание разговоров не собирается"),
    Feature("Управление доступом", "/access", "implemented", "Приглашение по username, подтверждение владельцем, привязка к ID"),
    Feature("Проверка сети", "/status", "partial", "Доступность LUNA; не проверка интернета колонки"),
    Feature("Звонки / VoIP", "", "blocked", "Нет проверенного duplex/VoIP API; voice-сообщения не являются звонком"),
    Feature("Саундборд / голосовое / TTS", "", "blocked", "Нужны транспорт файлов и подтверждение результата Lua audio.play"),
    Feature("Звуковые темы / сирена / фейковый бан", "", "blocked", "Зависят от корректного playback/stop/release; прямой aplay из бота запрещён"),
    Feature("Спросить Алису", "", "blocked", "speech/recognize читает STT; API отправки вопроса и ответа нет"),
    Feature("История диалогов", "", "blocked", "Нет исторического API; STT события не равны полной истории ответов"),
    Feature("Камера / фото / видео / охрана", "", "blocked", "Универсального camera/motion API LUNA нет; ПК-камера не камера колонки"),
    Feature("Прошивка / backup / restore", "", "blocked", "Нет квалифицированного API и модельных карт разделов; запись не выполняется"),
    Feature("Терминал / загрузка скрипта", "", "blocked", "Нужен отдельный privileged provider с аудитом и политикой выполнения"),
    Feature("Очистка кэша / fastfetch", "", "blocked", "Нет универсального maintenance API; пути не угадываются"),
    Feature("Автопоиск IP", "", "blocked", "LUNA не предоставляет discovery-протокол; настройте существующий туннель"),
    Feature("Автономный бот на колонке", "", "blocked", "Нужны Python/native runtime, упаковка и квалификация boot для каждой платформы"),
)


def parity_text() -> str:
    symbols = {"implemented": "✅", "partial": "◐", "blocked": "⏳"}
    return "\n".join(f"{symbols[f.status]} {f.name}: {f.command or f.reason}" for f in FEATURES)
