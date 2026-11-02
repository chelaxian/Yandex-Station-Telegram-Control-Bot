# Статус переноса функций 2.7 → 3.0.0a1

`implemented` означает реализовано и проверено в контрактных тестах; не обещание аппаратного теста всех моделей. `partial` и `blocked` означают незавершённую работу. Кодовый реестр: `src/stationbot/catalog.py`.

| Функция | Статус | Интерфейс | Граница |
|---|---|---|---|
| Громкость | implemented | /volume | ALSA capability и живой ответ LUNA |
| Подсветка | implemented | /led | ring/logo по topology, release через LUNA |
| Часы | implemented | /clock | Только при clock.available=true; без выдуманной бегущей строки |
| Диагностика | partial | /health | Устройство и датчики; CPU/RAM/Flash/RSSI API отсутствует |
| Запись комнаты | implemented | /record | 1–30 секунд, только operator/owner, WAV только в памяти |
| Плеер | partial | /media | Только зарегистрированные медиапровайдеры, не штатный плеер Алисы |
| Мои функции | partial | /plugins | Запуск установленных совместимых пакетов, выключен по умолчанию |
| Таймер | partial | /timer | Устойчивое уведомление в Telegram; не будильник на выключенном хосте |
| История действий | implemented | /history | Журнал метаданных; содержание разговоров не собирается |
| Управление доступом | implemented | /access | Приглашение по username, подтверждение владельцем, привязка к ID |
| Проверка сети | partial | /status | Доступность LUNA; не проверка интернета колонки |
| Звонки / VoIP | blocked | — | Нет проверенного duplex/VoIP API; voice-сообщения не являются звонком |
| Саундборд / голосовое / TTS | blocked | — | Нужны транспорт файлов и подтверждение результата Lua audio.play |
| Звуковые темы / сирена / фейковый бан | blocked | — | Зависят от корректного playback/stop/release; прямой aplay из бота запрещён |
| Спросить Алису | blocked | — | speech/recognize читает STT; API отправки вопроса и ответа нет |
| История диалогов | blocked | — | Нет исторического API; STT события не равны полной истории ответов |
| Камера / фото / видео / охрана | blocked | — | Универсального camera/motion API LUNA нет; ПК-камера не камера колонки |
| Прошивка / backup / restore | blocked | — | Нет квалифицированного API и модельных карт разделов; запись не выполняется |
| Терминал / загрузка скрипта | blocked | — | Нужен отдельный privileged provider с аудитом и политикой выполнения |
| Очистка кэша / fastfetch | blocked | — | Нет универсального maintenance API; пути не угадываются |
| Автопоиск IP | blocked | — | LUNA не предоставляет discovery-протокол; настройте существующий туннель |
| Автономный бот на колонке | blocked | — | Нужны Python/native runtime, упаковка и квалификация boot для каждой платформы |

Ни одна blocked-функция не перенаправляется в legacy ADB/shell. Все функции исходника сохранены как требования; требования ещё не выполнены целиком.

Следующие этапы: квалифицированный audio-transfer/playback с acknowledgement и stop → soundboard/voice/TTS/themes/siren; отдельный intercom state machine; camera/motion provider; privileged maintenance provider с модельными профилями и отдельным восстановлением; station-local packaging и boot validation. Все этапы требуют тестов на фактических целевых устройствах.
