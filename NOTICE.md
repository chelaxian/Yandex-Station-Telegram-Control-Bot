# Происхождение

Оригинальный Telegram Control Bot 2.7 предоставлен владельцем как `Telegram_Control_Bot (2).zip`.
Авторы, указанные в исходном описании: **@q_cold_city**, **@mipight**.
SHA-256 ZIP: `62912a8b0b8a991b10966b07b9b0fa62cd73d612431f60b9d61cf3a2f179b463`.

Импорт сохранён только в исторической ветке `alfa`; исходники и материалы 2.7 удалены из актуального дерева `main`. До первого коммита удалены встроенные/примерные Telegram credentials и настроечные owner IDs; перечень затронутых файлов и исходные хеши находятся в `IMPORT_PROVENANCE.json`. Не используйте опубликованные авторами общие API keys.

В архиве не найдено явного разрешения на перелицензирование исходников и звуковых фрагментов. Наличие файлов в публичном GitHub не заменяет такое разрешение. Новый Python runtime не включает legacy в wheel или контейнер и не запускает его скрипты.

LUNA — отдельный проект [nyakokitsu/luna](https://github.com/nyakokitsu/luna); исходники LUNA не скопированы в этот пакет. Используется HTTP-контракт закреплённого commit.

Изученные архитектурные референсы: [alice-control-center](https://github.com/chrometechhype/alice-control-center), [yapanel-web](https://github.com/dimap/yapanel-web) (прежнее имя yandex-station-web). Код из этих репозиториев не переносился. Telegram framework — [aiogram](https://docs.aiogram.dev/en/latest/), контракт — [Telegram Bot API](https://core.telegram.org/bots/api).
