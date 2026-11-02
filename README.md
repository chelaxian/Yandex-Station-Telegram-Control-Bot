# Yandex Station Telegram Control Bot

Telegram-интерфейс управления Яндекс Станциями через **LUNA**. Исходный Bot Control 2.7 от **@q_cold_city и @mipight** сохранён в ветке [`alfa`](https://github.com/chelaxian/Yandex-Station-Telegram-Control-Bot/tree/alfa). Разработка нового runtime ведётся в `main` по запросу владельца.

> **3.0.0a1 — незавершённый ремейк, не production-релиз.** Новый runtime покрывает подтверждённую часть LUNA API. Полная совместимость с функциями 2.7 и всеми моделями ещё не достигнута. См. [матрицу функций](docs/FEATURE_PARITY.md) и [проверки](docs/VALIDATION.md). Исходные рекламные обещания не являются результатами тестов.

## Что изменилось

Вместо монолита с ADB-командами используется Python-пакет: асинхронный Telegram router → сервис доступа/операций → типизированный HTTP-адаптер LUNA → station backend. Новый runtime не угадывает пути sysfs, ALSA mixer, разделы Flash и коммерческую модель по похожему codename.

- Несколько станций; выбранное устройство хранится отдельно для каждого пользователя. Кнопки содержат конкретную станцию.
- Проверка `expected_model`, актуальных capabilities, topology LED, доступности часов и микрофонов перед действиями.
- Громкость, ring/logo и их release, часы, датчики, WAV-запись, тест звука, установленные пакеты и медиапровайдеры через существующие LUNA endpoints.
- Роли owner/operator/viewer; приглашение по `@username` требует подтверждения владельцем и затем закрепляется за числовым ID.
- SQLite WAL, сериализация действий на каждой станции, защита от дубликатов, явное `unknown` после сбоя, таймеры с восстановлением и ограниченный журнал метаданных.
- Записи комнаты передаются из памяти; новый runtime не сохраняет их на диск. Нельзя обещать удаление данных из Telegram, swap, дампов памяти или инфраструктуры Telegram.

## Быстрый старт

Нужны Python **3.10+**, Telegram bot token, уже работающая LUNA и защищённый доступ к ней. Корень файловой системы колонки не изменяется установкой этого Python-пакета.

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e .
Copy-Item config.example.toml config.toml
# Измените owner_id, станции, expected_model и адреса существующих туннелей.
# TELEGRAM_BOT_TOKEN задайте через локальное хранилище секретов/окружение.
.venv\Scripts\python.exe -m stationbot --config config.toml doctor
.venv\Scripts\python.exe -m stationbot --config config.toml run
```

Linux: используйте `.venv/bin/python`. `doctor` не требует токена Telegram, не посылает сообщения и не меняет устройства; он проверяет идентификацию LUNA. `/menu`, `/stations` и `/help` доступны в личном чате после запуска.

Секреты задаются только через переменные окружения. Рабочие конфигурации, записи, БД и сессии исключены из Git. Не запускайте второй poller с тем же Telegram token: блокировка state-dir защищает только один локальный каталог.

## Совместимость и доверие

Контракт закреплён на [`chelaxian/luna@3858d13`](https://github.com/chelaxian/luna/commit/3858d133a856adf35bb3af7eba0f91f1284bf987), ветка аппаратной адаптации [PR24](https://github.com/nyakokitsu/luna/pull/24), поверх upstream v0.2.18. Это не обещание наличия этих изменений в официальном релизе. Строка версии Cargo сама по себе не подтверждает нужный commit.

Административный HTTP API LUNA **не имеет аутентификации**. Используйте loopback через существующий SSH tunnel или собственный HTTPS proxy с Bearer-проверкой. `X-Luna-Token` предназначен для запущенного плагина, а не для защиты admin API. Не открывайте порт runtime в интернет. Клиент не следует redirect, не наследует системный HTTP proxy и проверяет TLS по умолчанию.

Код не содержит жёсткого списка поддерживаемых моделей: он проверяет runtime contract и возможности устройства. Аппаратная квалификация доступна пока для Станции 2 и Мини 3 Про и имеет [явные пределы](docs/LUNA_CONTRACT.md). Отсутствие квалификации других моделей не заменяется формулировкой «поддерживаются все».

## Разработка

```sh
python -m pip install -e '.[dev]' -c requirements.lock.txt
python -m ruff check src tests
python -m pytest -q
python -m build
```

CI проверяет Windows/Linux, Python 3.10/3.12. Тесты используют синтетический WAV, HTTP fixtures и fake Telegram session; реальные боты и микрофоны не задействуются. Снимок зависимостей — `requirements.lock.txt`, не lock для всех будущих платформ и версий Python.

В [`legacy/`](legacy/) находится сохранённый импорт 2.7. Он исключён из wheel и контейнера; его установщики и скрипты не используются новым runtime. Происхождение и санитарные изменения описаны в [IMPORT_PROVENANCE.json](IMPORT_PROVENANCE.json). Право переиздать сторонний код или звуковые материалы под новой лицензией не предполагается; см. [NOTICE](NOTICE.md).
