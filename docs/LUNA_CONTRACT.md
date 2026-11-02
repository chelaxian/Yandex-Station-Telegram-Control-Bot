# Проверенный контракт LUNA

## Расширение beta 3.0.0b1

Источник: [`0f2393e`](https://github.com/chelaxian/luna/commit/0f2393e4d613472c79755b358abc3047a9466963), ветка `feat/telegram-complete-runtime`. Это реализованные HTTP handlers, а не предполагаемые upstream endpoints. Новые маршруты проходят общий browser guard и ограничение тела запроса. Аутентификация admin API не добавлена: требуется loopback или аутентифицирующий proxy.

| Контракт | Endpoint | Семантика |
|---|---|---|
| audio.jobs.v1 | POST `/api/audio/jobs` | WAV ≤64 МиБ/600 секунд; обязательный Idempotency-Key; один активный job; 202 не означает завершение |
| Журнал/результат | GET `/api/audio/jobs`, GET `/api/audio/jobs/{uuid}` | queued/playing/succeeded/failed/cancelled/interrupted и отдельный cleanup |
| Отмена | POST `/api/audio/jobs/{uuid}/cancel` | Завершает только собственный aplay; конечный статус читать отдельно |
| Удаление метаданных | DELETE `/api/audio/jobs/{uuid}` | Только terminal job; payload очищается автоматически после выхода |
| Owner files | GET `/api/owner/files`; GET/POST/DELETE `/api/owner/files/{scripts,firmware}/{name}` | Явное `LUNA_ENABLE_OWNER_TOOLS=1`; плоские проверенные имена; create-only, SHA-256, квота; firmware всегда flashed=false |
| Терминал | POST `/api/owner/execute` `{command,timeout}` | Только явно включённый provider; 1–30 секунд, вывод ≤64 КиБ на поток; собственная process group |
| Скрипт | POST `/api/owner/scripts/run` `{name,source?}` | Только .sh, UTF-8, ≤1 МиБ; временная копия source удаляется после выполнения |
| Диагностика | GET `/api/owner/system` | Стандартные Linux procfs: RAM, uptime, load, wireless, kernel; без системных изменений |
| Фазы речи | GET `/api/owner/phase` | owner.speech.phase.v1; только phase/initial_snapshot, без transcript/request ID/account; используется для звуковых тем |

Audio payload не сохраняется после завершения job. Метаданные ограничены 64 записями; при старте незавершённые задания становятся interrupted, аудио удаляется, автоматического replay нет. TTL метаданных 24 часа применяется при старте; в работающем процессе действует ограничение количества. Успешный код выхода ALSA не заменяет слуховую проверку.

`allow_owner_tools=true` в bot config также обязателен; терминал/скрипты/образы доступны только owner. Это полномочный root-shell на выбранной колонке, не песочница для чужих скриптов. Не открывать owner API в LAN/WAN без внешней аутентификации.

Срез 02.11.2026: `3858d133a856adf35bb3af7eba0f91f1284bf987`, [источники](https://github.com/chelaxian/luna/tree/3858d133a856adf35bb3af7eba0f91f1284bf987), upstream base `e6a4b3abfe9631d6cea619ecc1c38d6b8a1315c6`. Консультация с сессией LUNA сверена с `src/gateway.rs`, `src/audio.rs`, station crates и предыдущими аппаратными отчётами. Это HTTP JSON, не WebSocket или Python SDK.

| Функция | Endpoint | Проверка перед действием |
|---|---|---|
| Идентификация | GET `/api/device` | canonical model == expected_model; форма ответа |
| Громкость | GET/POST `/api/volume`, `{percent}` | `audio.volume.alsa`, диапазон 0–100 |
| Ring/logo | POST `/api/led/{zone}`, `{colors:["#RRGGBB"]}` | capability и ненулевая topology |
| Release LED | POST `/api/led/off/{zone}` | та же zone/capability |
| Часы | GET/POST `/api/clock`, `{time,brightness}` | `available=true`; не вывод по названию модели |
| Release часов | POST `/api/clock/off` | доступные часы |
| Сегментный экран | POST `/api/clock`, `{segments:{name:brightness}}` | имена только из GET clock; 0–255; без угадывания нумерации по модели |
| Текстовый экран | POST `/api/clock/text`, `{text,brightness}` | только text_available=true; на Mini3Pro false, используется ограниченный четырёхзначный алфавит |
| Датчики | GET `/api/sensors` | массив, `value` может быть null |
| Микрофоны | GET `/api/microphone/devices` | `microphone.capture` и актуальные channel IDs |
| WAV | POST `/api/microphone/record`, `{seconds,device?}` | 1–30 с, bounded response, валидный непустой PCM WAV |
| Тест звука | POST `/api/audio/test` | объявленный audio.play backend; не произвольный playback |
| Пакеты | GET `/api/plugins`; POST `/api/plugins/{id}/invoke` | owner, allow_packages, enabled + compatible |
| Плеер | GET `/api/media`; POST `/api/media/command` | только зарегистрированные провайдеры; 202 значит accepted |

LUNA обычно возвращает HTTP 400 даже для недоступности/ошибок разрешений. Нельзя ожидать только 401/403. HTTP redirect запрещён. Изменяющие операции, запись и playback не повторяются автоматически при timeout. Только ограниченный набор read-only запросов имеет один повтор. Живой ответ сильнее capability hint; например, Station2 может рекламировать `led.sysfs`, хотя ring реализован через framebuffer.

## Аппаратная квалификация upstream-адаптации

Предыдущая проверка другой сессии от 02.11, не повторный тест нового Telegram-кода:

| Устройство | Canonical model | Проверенные особенности | Ограничения |
|---|---|---|---|
| Станция 2 YNDX00051 .50 | `yandexstation_2` | framebuffer ring 89/BGRX, 4 raw microphone channels, PCM `dmix_spk_plug`, volume-up событие | нет logo/clock; platform `yandexmidi` не означает коммерческую Midi |
| Мини 3 Про YNDX00059 .50 | `yandexmini_3_pro` / asset pickle | ring16/logo6, 36 clock segments, 3 raw microphone channels, PCM `speakers`, volume-up событие | не bergamot; clock text_available=false |

LED readback, release, clock readback и nonzero PCM ранее проверены. Владелец подтвердил слышимый прямой ALSA-тест обеих; для последующего HTTP audio/test отдельного слухового подтверждения нет. Новая версия бота не переиспользует прямой ALSA из этих испытаний.

LUNA на устройствах была запущена временно из `/tmp`, persistence/reboot не проверены. `doctor` не устанавливает LUNA и не создаёт tunnel. Локальный port-forward одного компьютера не является доступом из Docker/CT126.

## Отсутствующие контракты

Нет общего admin API для TTS, отправки текстового вопроса Алисе, полного dialog history, camera/motion, terminal, backup, restore и firmware flash. `alice/speech` и `recognize` относятся к распознаванию, а не к синтезу/ответу Алисы. `/input/*` ожидает реальные события, а не эмулирует нажатия. `/audio/test` проигрывает встроенный тестовый файл, а не пользовательский MP3.

Lua `alice.audio.play(relative_file)` существует, но HTTP-клиенту нужны безопасный перенос файла, подтверждённый результат выполнения и stop/cleanup. Простая установка Lua-пакета и ответ 202 не доказывают звук или успешное удаление. Нужен отдельный квалифицированный provider, а не выдуманный `/api/tts`.
