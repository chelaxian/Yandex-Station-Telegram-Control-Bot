"""The 2.7 local helper: typed station intents and reference lookup, not a cloud Alice impersonation."""
from __future__ import annotations

import ast
import datetime
import operator
import re
import secrets

import httpx

from .errors import InvalidInput, Unavailable

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
       ast.Div: operator.truediv, ast.Mod: operator.mod}


def calculate(text: str) -> float:
    tree = ast.parse(text, mode="eval")
    if sum(1 for _ in ast.walk(tree)) > 40:
        raise ValueError

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) in {int, float} and abs(node.value) <= 1e12:
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            return visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        if isinstance(node, ast.BinOp) and type(node.op) in OPS:
            result = OPS[type(node.op)](visit(node.left), visit(node.right))
            if abs(result) <= 1e15:
                return result
        raise ValueError
    return visit(tree.body)


async def answer(client, question: str) -> str:
    if not question or len(question) > 1000:
        raise InvalidInput("/ask текст — до 1000 символов")
    query = re.sub(r"^алиса[,!\s]*", "", question.lower()).strip()
    match = re.fullmatch(r"(?:установи |сделай )?громкость\s*(?:на\s*)?(\d+)", query)
    if match:
        percent = int(match[1])
        if percent <= 10:
            percent *= 10
        result = await client.volume(percent)
        return f"Громкость: {result['percent']}%."
    if query in {"стоп", "тишина", "выключи звук", "пауза"}:
        await client.stop_audio()
        return "Запрошена остановка звуков бота."
    if "сколько времени" in query or "который час" in query:
        return datetime.datetime.now().astimezone().strftime("Время хоста: %H:%M, %Z.")
    if "дат" in query and "какая" in query:
        return datetime.date.today().isoformat()
    if "кубик" in query:
        return f"Кубик: {secrets.randbelow(6)+1}."
    if "монет" in query:
        return secrets.choice(["Орёл", "Решка"])
    if query in {"привет", "здравствуй"}:
        return "Здравствуйте! Я локальный помощник бота. Могу изменить громкость, назвать время, посчитать пример и найти статью в энциклопедии."
    expression = re.sub(r"^(?:сколько будет|посчитай|вычисли)\s*", "", query).rstrip("? ")
    if re.fullmatch(r"[\d\s()+*/%.\-]+", expression):
        try:
            return str(calculate(expression))
        except (ValueError, SyntaxError, ZeroDivisionError, OverflowError) as e:
            raise InvalidInput("Не удалось вычислить пример") from e
    if "подсветку" in query:
        off = "выключ" in query or "погаси" in query
        await client.led("ring", None if off else "#6E00F0")
        return "Подсветка: команда выполнена."
    async with httpx.AsyncClient(timeout=10, follow_redirects=False) as http:
        try:
            response = await http.get("https://ru.wikipedia.org/w/api.php", params={
                "action": "query", "generator": "search", "gsrsearch": question,
                "gsrlimit": 1, "prop": "extracts", "exintro": 1, "explaintext": 1,
                "exchars": 1000, "format": "json"}, headers={"User-Agent": "YandexStationTelegramBot/3.0"})
            response.raise_for_status()
            if len(response.content) > 128 * 1024:
                raise ValueError
            pages = response.json().get("query", {}).get("pages", {})
            page = next(iter(pages.values()), {})
            extract = page.get("extract", "").strip()
            if extract:
                return f"{page['title']}\n{extract[:1000]}\nhttps://ru.wikipedia.org/?curid={int(page['pageid'])}"
            return "В энциклопедии не найден ответ. Попробуйте уточнить вопрос."
        except (httpx.HTTPError, ValueError, KeyError, TypeError) as e:
            raise Unavailable("Энциклопедия недоступна; управление станцией работает независимо") from e
