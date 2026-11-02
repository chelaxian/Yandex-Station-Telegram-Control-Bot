# Функции 2.7 → 3.0.0b1

`implemented` означает наличие реализации и программных проверок, а не аппаратную квалификацию всех моделей. Доступность зависит от backend и настроенных устройств.

| Функция | Статус | Команды | Условия и границы |
|---|---|---|---|
| Громкость | implemented | /volume | ALSA capability и живой ответ LUNA |
| Подсветка | implemented | /led | ring/logo по topology, release через LUNA |
| Часы | implemented | /clock | Только при clock.available=true; без выдуманной бегущей строки |
| Диагностика | implemented | /health · /system | Датчики и opted-in owner/system: RAM, load, uptime, wireless |
| Запись комнаты | implemented | /record | 1–30 секунд, только operator/owner, WAV только в памяти |
| Плеер | partial | /media | Только зарегистрированные медиапровайдеры, не штатный плеер Алисы |
| Мои функции | implemented | /custom · /plugins | Сохранённые .sh через owner tools и совместимые пакеты |
| Таймер / будильник | implemented | /timer · /alarm | SQLite, звук через audio jobs, уведомление; хост должен работать |
| История действий | implemented | /history | Журнал метаданных; содержание разговоров не собирается |
| Управление доступом | implemented | /access | Приглашение по username, подтверждение владельцем, привязка к ID |
| Проверка сети | implemented | /network | Доступность/RTT LUNA; ограничения интернета колонки сохраняются |
| Интерком (назван VoIP в 2.7) | implemented | /call · /answer · /hangup | Фрагменты комнаты, голосовой приём, предел 30 минут; не Telegram calls |
| Саундборд / голосовое / TTS | implemented | /sounds · /play · /tts | ffmpeg/espeak-ng на хосте; audio.jobs.v1 с конечным результатом и очисткой |
| Темы / сирена / фейковый бан | implemented | /theme · /siren · /ban · /stop | Синтезированные темы, без сторонних звуковых лицензий |
| Спросить помощника | implemented | /ask | Как в 2.7: локальные намерения и энциклопедия; не облачная Алиса |
| История диалогов | implemented | /dialogs · /legacy_history | Диалоги помощника и read-only прежняя история |
| Камера / фото / видео / охрана | implemented | /photo · /video · /guard | Явно настроенная камера хоста, как в 2.7; не несуществующая камера колонки |
| Образы / backup / restore | implemented | /firmware · /backup · /restore | Сохранение образа с SHA-256 и ZIP прикладных данных; как в исходнике, без flash |
| Терминал / загрузка скрипта | implemented | /shell · /upload_script · /run_script | Owner tools включаются отдельно; timeout, ограниченный вывод, аудит |
| Очистка / система | implemented | /cleanup · /system | Только собственные временные файлы; неизвестные системные каталоги не удаляются |
| Автопоиск IP | implemented | /discover | Ограниченная частная подсеть; найденные ADB-порты — кандидаты, не идентификация модели |
| Автономная установка на колонку | partial | — | Требует отдельного Python/runtime и квалификации автозапуска; сейчас используется мини-ПК |

Реальные проверки и их пределы: [VALIDATION.md](VALIDATION.md). Для playback нужен новый LUNA audio.jobs.v1; HTTP202 означает принятие, конечный результат читается отдельно. Прежние alpha-функции, ошибочно считавшиеся невозможными, реализованы без запуска legacy-кода.
