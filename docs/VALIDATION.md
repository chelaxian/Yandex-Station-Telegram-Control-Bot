# Проверки 02.11.2026

Статус: **3.0.0a1, незавершённая миграция**. Полная parity 2.7 и аппаратная поддержка всех моделей не заявляются.

## Выполнено локально

- Windows, CPython 3.10.11, aiogram 3.31.0, httpx 0.28.1, aiosqlite 0.22.1.
- `ruff check src tests scripts`: PASS.
- `pytest -q`: 29 PASS. Включены модельная идентификация и topology, запрет clock без backend, диапазоны аргументов, отсутствие повторов mutating timeout, один read retry, WAV/channel validation, redirects/response limits, RBAC и ID pinning, идемпотентность, crash recovery, concurrency приглашений и таймеров, fake Telegram private-chat/menu/recording tests, отзыв доступа в очереди, независимость двух станций и OS instance-lock.
- `python -m build`: sdist и pure-Python wheel успешно собраны. Новый wheel содержит только `stationbot` и метаданные, без legacy/ADB/media/config/session.
- Credential guard: PASS по поддерживаемым regex для tracked files. Это ограниченная проверка, не гарантия отсутствия любого секрета.
- Новый `doctor` выполнил **только GET `/api/device`** через существующие локальные forwards. Оба устройства online: `yandexstation_2` и `yandexmini_3_pro`; advertising capabilities прочитаны. Модель и API shape совпали с конфигурацией.

## Что это не проверяет

Реальный Telegram token не загружался, новый poller не запускался в production. Ни реальная запись комнаты, ни изменение LED/громкости/часов, ни проигрывание звука этой версией бота не выполнялись. Аудио в тестах синтетическое. Предыдущие аппаратные испытания LUNA описаны отдельно в [контракте](LUNA_CONTRACT.md); они не являются E2E-тестом нового бота.

Для commit `fe68cdd` [CI](https://github.com/chelaxian/Yandex-Station-Telegram-Control-Bot/actions/runs/41490307734) прошёл во всех четырёх сочетаниях Linux/Windows и Python3.10/3.12: lint, 26 тестов первоначального набора, build, credential guard. Три последующих регрессионных сценария проверены локально; их CI запускается отдельно. Docker и systemd — шаблоны, не испытанный deployment. Station-local runtime, boot persistence, остальные модели, длительная нагрузка и полное восстановление после сетевых/аппаратных сбоев остаются неквалифицированными.
