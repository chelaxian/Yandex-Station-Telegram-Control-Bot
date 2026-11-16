# Экспериментальный backend Станции Макс (max-gateway)

**Статус: экспериментальный, не проверен на реальном Максе вместе с ботом.** Подтверждены отдельные пробы на одной колонке и одной прошивке (см. [MAX_EXPERIMENT.md](MAX_EXPERIMENT.md)). Микрофон, интерком, запись, подсветка и экран для Макса не объявляются и скрыты в меню.

Бинарник LUNA на Максе не запускается, поэтому на ПК/сервере работает отдельный шлюз: `python -m stationbot.max_gateway` или `max-gateway.pyz`. Он слушает только `127.0.0.1` (порт `18300`, проверяется заголовок Host) и по уже работающему root SSH выполняет только подтверждённые операции:

- `GET /api/device`: модель `yandexstation_max`, возможности `audio.jobs.v1`, `audio.play.android`, `audio.volume.android`;
- `GET/POST /api/volume`: `media volume --stream 3` (шкала 0–100), значение читается обратно;
- `POST /api/audio/jobs` (PCM16 WAV, моно/стерео, 8–48 кГц, до 64 МиБ, заголовок `Idempotency-Key`), `GET /api/audio/jobs[/id]`, `POST /api/audio/jobs/id/cancel`, `POST /api/audio/test`.

При старте шлюз проверяет root SSH и геометрию fb4/fb5 (как `max-ssh-probe`) и при расхождении не запускается. Каждое задание копирует маленький dex-плеер (`MaxPlay`, исходник в `experiments/max-audio`) и WAV в приватный каталог `/data/local/tmp/max-play-<uuid>`, запускает `app_process` с окружением adbd; отмена создаёт файл `stop`; затем каталог удаляется, удаление проверяется (`cleanup: complete|failed`). Задания идут по одному. Громкость 0% блокирует воспроизведение в боте; громкость звука задаёт системная громкость музыки.

## Запуск

```powershell
py .\max-gateway.pyz --host <IP> --user <root-пользователь> --port <порт> --ssh-config "<путь к SSH-конфигу>"
```

Проверка без бота: `curl http://127.0.0.1:18300/api/device`, `curl http://127.0.0.1:18300/api/volume`, `curl -X POST http://127.0.0.1:18300/api/audio/test` (короткий тон 660 Гц; начните с низкой громкости).

Станция в `config.toml` бота:

```toml
[[stations]]
id = "max"
label = "Станция Макс (эксперимент)"
url = "http://127.0.0.1:18300/api"
expected_model = "yandexstation_max"
```
