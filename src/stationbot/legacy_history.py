"""Read-only access to the owner's previous action journal; never import executable code."""
import json
from pathlib import Path

from .errors import InvalidInput, Unavailable


def read_legacy_history(root: Path | None, station: str) -> str:
    if root is None:
        raise Unavailable("Каталог прежней истории не настроен")
    path = root / f"history-{station}.json"
    try:
        if path.stat().st_size > 1024 * 1024:
            raise InvalidInput("Прежний журнал слишком большой для просмотра")
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
        lines = []
        for date, entries in data.items():
            if not isinstance(entries, list):
                raise ValueError
            for event in entries:
                if not isinstance(event, dict):
                    raise ValueError
                lines.append(f"{date} {event.get('time', '')}\n{event.get('user', '')}\n{event.get('alice', '')}")
        return "История действий прежнего бота (не полная история диалогов Алисы):\n\n" + "\n\n".join(lines[-10:])[-3400:]
    except FileNotFoundError:
        return "У прежнего бота нет сохранённой истории этой станции"
    except (ValueError, TypeError, OSError) as e:
        raise Unavailable("Прежняя история недоступна или повреждена; файл сохранён без изменений") from e
