# Проверки 02.11.2026

Статус: **3.0.0a2, незавершённая миграция**. Полная parity 2.7 и аппаратная поддержка всех моделей не заявляются.

## Личный Linux deployment владельца

Commit `7773047` установлен в отдельный release/venv внутри существующего Linux LXC по прямому поручению владельца. Прежние код, config, Telethon session и per-station history сохранены; новые secrets/state отделены. После активации защищённые файлы прежнего бота проверены по SHA256 и не изменились. Проверен manual rollback script; автоматический откат дважды сработал при ошибках подготовки (формат времени journalctl, затем права новой SQLite). Обе ошибки исправлены, финальный процесс работает от исходного непривилегированного пользователя без рестартов.

- 35 тестов PASS на Windows3.10 и отдельно Linux3.11. [CI7773047](https://github.com/chelaxian/Yandex-Station-Telegram-Control-Bot/actions/runs/41493788604) PASS во всех4jobs Linux/Windows Python3.10/3.12.
- Реальные GET/device, volume, sensors и microphone/devices обеих моделей прошли из LXC; каналов4/3. Транспорт — уже доступный ADB, отдельные local forwards и foreground server только на loopback. SSH TCP forwarding оказался запрещён; конфигурация SSH станций не менялась.
- Telegram getMe и webhook preflight PASS через прежний HTTP proxy. Runtime polling активен; прежний poller остановлен. Native Menu Commands, global/owner scopes и14команд прочитаны обратно.
- В router поданы два синтетических `/menu` с тестовым read-only selection; ответы реально отправлены владельцу через Telegram API. Ответные Message/markup проверены: часы видны у Mini3Pro, отсутствуют у Station2. Это реальный outbound API и тест router, а не подтверждение реального входящего клика пользователя.
- Аудио, LED/clock/volume writes, reboot, OTA, Flash, сеть/ALSA колонок не менялись. Проверки автозапуска после reboot не выполнялись. LUNA на колонках остаётся временной: её persistence требует отдельного завершения.

## Выполнено локально

- Windows, CPython 3.10.11, aiogram 3.31.0, httpx 0.28.1, aiosqlite 0.22.1.
- `ruff check src tests scripts`: PASS.
- `pytest -q`: 29 PASS. Включены модельная идентификация и topology, запрет clock без backend, диапазоны аргументов, отсутствие повторов mutating timeout, один read retry, WAV/channel validation, redirects/response limits, RBAC и ID pinning, идемпотентность, crash recovery, concurrency приглашений и таймеров, fake Telegram private-chat/menu/recording tests, отзыв доступа в очереди, независимость двух станций и OS instance-lock.
- `python -m build`: sdist и pure-Python wheel успешно собраны. Новый wheel содержит только `stationbot` и метаданные, без legacy/ADB/media/config/session.
- Credential guard: PASS по поддерживаемым regex для tracked files. Это ограниченная проверка, не гарантия отсутствия любого секрета.
- Новый `doctor` выполнил **только GET `/api/device`** через существующие локальные forwards. Оба устройства online: `yandexstation_2` и `yandexmini_3_pro`; advertising capabilities прочитаны. Модель и API shape совпали с конфигурацией.

## Что это не проверяет

Ни реальная запись комнаты, ни изменение LED/громкости/часов, ни проигрывание звука этой версией бота не выполнялись. Аудио в unit tests синтетическое. Предыдущие аппаратные испытания LUNA описаны отдельно в [контракте](LUNA_CONTRACT.md); они не являются E2E-тестом нового бота.

Для commit `3db9c33` [CI](https://github.com/chelaxian/Yandex-Station-Telegram-Control-Bot/actions/runs/41490893383) прошёл во всех четырёх сочетаниях Linux/Windows и Python3.10/3.12: lint, 29 тестов, build, credential guard. Docker и systemd — шаблоны, не испытанный deployment. Station-local runtime, boot persistence, остальные модели, длительная нагрузка и полное восстановление после сетевых/аппаратных сбоев остаются неквалифицированными.
