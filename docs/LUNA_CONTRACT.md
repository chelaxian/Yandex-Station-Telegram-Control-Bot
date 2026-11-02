# Проверенный контракт LUNA

Срез 02.11.2026: `3858d133a856adf35bb3af7eba0f91f1284bf987`, [источники](https://github.com/chelaxian/luna/tree/3858d133a856adf35bb3af7eba0f91f1284bf987), upstream base `e6a4b3abfe9631d6cea619ecc1c38d6b8a1315c6`. Консультация с сессией LUNA сверена с `src/gateway.rs`, `src/audio.rs`, station crates и предыдущими аппаратными отчётами. Это HTTP JSON, не WebSocket или Python SDK.

| Функция | Endpoint | Проверка перед действием |
|---|---|---|
| Идентификация | GET `/api/device` | canonical model == expected_model; форма ответа |
| Громкость | GET/POST `/api/volume`, `{percent}` | `audio.volume.alsa`, диапазон 0–100 |
| Ring/logo | POST `/api/led/{zone}`, `{colors:["#RRGGBB"]}` | capability и ненулевая topology |
| Release LED | POST `/api/led/off/{zone}` | та же zone/capability |
| Часы | GET/POST `/api/clock`, `{time,brightness}` | `available=true`; не вывод по названию модели |
| Release часов | POST `/api/clock/off` | доступные часы |
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
