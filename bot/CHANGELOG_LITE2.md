# Lite 2 (Plum) compatibility update

- Fixed hardware detection: `plum` / `Yandex-Lite-gen2` is identified as Yandex Station Lite 2, not Mini 3.
- Added Lite 2 RGB ring sysfs support (`plum:red|green|blue:ring1..3`) to RGB detection and rotating effects.
- Added Plum platform to RGB base detection.
- Extended matrix clearing to include row H (8x4 matrix).
- Made clock sync LED lookup generic rather than hard-coded to cucumber.

Important:
- This is a first compatibility pass based on the supplied read-only device inventory.
- Microphone capture, exact screen animation mapping, brightness calibration, and ADB transport still require device-side validation.
- SSH port 2222 is not necessarily the ADB port. The bot's Station port setting is for ADB, not SSH.


## Исправления сирены и звонков (следующий тестовый проход)

- Добавлен `speaker_scripts/alarm_helper.sh`: режимы `start`, `siren_only`, `stop`; сирена повторяется до остановки, исходная громкость сохраняется и восстанавливается.
- Установщик теперь загружает также `record_helper.sh` и `alarm_helper.sh` (раньше он загружал только RGB- и LED-скрипты).
- Запись микрофона и воспроизведение сообщений в звонке синхронизированы блокировкой, чтобы запись не останавливала интерфейс в момент озвучки.
- Во время звонка TTS больше не заменяет зелёный индикатор вызова фиолетовым и ждёт завершения воспроизведения.
- Лимит звонка изменён с жёстких 2 минут на настраиваемые 30 минут; `call_max_minutes = 0` отключает автоматический лимит.
- `siren.wav` и `alarm_loud.wav` нормализованы по пиковому уровню без клиппинга.

Это всё ещё тестовая адаптация. Реальный режим микрофона/звонка нужно проверить на конкретной Лайт 2 после установки. Текущая функция звонка передаёт аудио фрагментами через Telegram и не является низколатентным полноценным VoIP.
