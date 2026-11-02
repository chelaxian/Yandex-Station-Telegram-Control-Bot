import time
from datetime import datetime, timezone

import pytest_asyncio
from aiogram import Bot
from aiogram.client.session.base import BaseSession
from aiogram.methods import SendDocument, SendMessage
from aiogram.types import Chat, Message, Update, User

from stationbot.telegram import make_dispatcher


class RecordingSession(BaseSession):
    def __init__(self):
        super().__init__()
        self.sent = []

    async def close(self):
        pass

    async def make_request(self, bot, method, timeout=None):
        self.sent.append(method)
        if isinstance(method, (SendMessage, SendDocument)):
            return Message(message_id=100, date=datetime.now(timezone.utc),
                           chat=Chat(id=int(method.chat_id), type="private"),
                           text=method.text if isinstance(method, SendMessage) else None)
        return True

    async def stream_content(self, url, headers=None, timeout=30, chunk_size=65536, raise_for_status=True):
        yield b""


@pytest_asyncio.fixture
async def bot():
    session = RecordingSession()
    bot = Bot("123456789:" + "a" * 35, session=session)
    yield bot
    await session.close()


def update(text, *, user=1, private=True, mid=1):
    return Update.model_validate({"update_id": mid, "message": {
        "message_id": mid, "date": int(time.time()), "text": text,
        "from": {"id": user, "is_bot": False, "first_name": "Owner", "username": "friend"},
        "chat": {"id": user if private else -1000001, "type": "private" if private else "supergroup"}}})


async def test_menu_uses_live_capabilities_and_never_mutates(service, bot):
    dp = make_dispatcher(service)
    await dp.feed_update(bot, update("/menu"))
    menu = bot.session.sent[-1]
    labels = [b.text for row in menu.reply_markup.inline_keyboard for b in row]
    assert "🕒 Часы" in labels
    assert "🌈 Подсветка" in labels
    assert all(r.method == "GET" for r in service.fakes[0].requests)
    await service.store.select(1, "station")
    await dp.feed_update(bot, update("/menu", mid=2))
    menu = bot.session.sent[-1]
    assert all(b.text != "🕒 Часы" for row in menu.reply_markup.inline_keyboard for b in row)


async def test_unauthorized_and_groups_never_reach_luna(service, bot):
    dp = make_dispatcher(service)
    await dp.feed_update(bot, update("/volume 100", user=99))
    await dp.feed_update(bot, update("/record 10", private=False, mid=2))
    assert not service.fakes[0].requests
    assert not service.fakes[1].requests
    assert not bot.session.sent


async def test_unavailable_function_has_no_fallback_shell(service, bot):
    await make_dispatcher(service).feed_update(bot, update("/firmware"))
    assert "не реализована" in bot.session.sent[-1].text
    assert not service.fakes[0].requests


async def test_recording_uploaded_from_memory(service, bot, tmp_path):
    before = set(tmp_path.rglob("*.wav"))
    await make_dispatcher(service).feed_update(bot, update("/record 1"))
    sent = bot.session.sent[-1]
    assert isinstance(sent, SendDocument)
    assert sent.document.data.startswith(b"RIFF")
    assert set(tmp_path.rglob("*.wav")) == before


async def test_invited_user_still_cannot_control_before_approval(service, bot):
    await service.store.invite(1, "friend", "operator")
    dp = make_dispatcher(service)
    await dp.feed_update(bot, update("/start", user=2))
    assert "подтверждения" in bot.session.sent[-1].text
    await dp.feed_update(bot, update("/volume 90", user=2, mid=2))
    assert not service.fakes[0].requests


async def test_viewer_cannot_forge_mutation_callback(service, bot):
    await service.store.write("INSERT INTO members VALUES (2,'viewer')")
    event = Update(update_id=1, callback_query={
        "id": "forged", "from_user": User(id=2, is_bot=False, first_name="Viewer"),
        "chat_instance": "x", "data": "act:mini:audio_test",
        "message": Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=2, type="private"))})
    await make_dispatcher(service).feed_update(bot, event)
    assert not service.fakes[0].requests
    assert "Недопустимая" in bot.session.sent[-1].text
