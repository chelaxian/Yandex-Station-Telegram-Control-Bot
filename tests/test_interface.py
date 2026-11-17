import asyncio
import json
import time
from dataclasses import replace
from datetime import datetime, timezone

import pytest
from aiogram.methods import SendDocument
from aiogram.types import Chat, Message, Update, User
from test_telegram import bot as bot
from test_telegram import update

from stationbot.luna import Device
from stationbot.presentation import result_card
from stationbot.telegram import main_menu, make_dispatcher


def click(data, user=1, mid=10):
    # A Telegram callback message is authored by the bot, not by the clicking
    # user. Accidentally using message.from_user would bypass the real actor.
    return Update(update_id=mid, callback_query={
        "id": f"click-{mid}", "from_user": User(id=user, is_bot=False, first_name="Owner"),
        "chat_instance": "private", "data": data,
        "message": Message(message_id=1, date=datetime.now(timezone.utc), chat=Chat(id=user, type="private"),
                           from_user=User(id=999999, is_bot=True, first_name="Bot"))})


def button(message, label):
    return next(b.callback_data for row in message.reply_markup.inline_keyboard for b in row if b.text == label)


async def test_volume_button_sets_value_once_as_clicking_user(service, bot):
    dp = make_dispatcher(service)
    await dp.feed_update(bot, click("act:mini:volume_get"))
    panel = bot.session.sent[-1]
    assert panel.parse_mode == "HTML" and "20%" in panel.text and '"percent"' not in panel.text
    data = button(panel, "25%")
    await dp.feed_update(bot, click(data, mid=11))
    assert service.fakes[0].volume == 25 and "25%" in bot.session.sent[-1].text
    await dp.feed_update(bot, click(data, mid=12))
    assert "устарела" in bot.session.sent[-1].text
    assert len([r for r in service.fakes[0].requests if r.method == "POST"]) == 1


async def test_record_button_warns_when_returned_wav_is_short(service, bot):
    dp = make_dispatcher(service)
    await dp.feed_update(bot, click("guide:mini:record"))
    await dp.feed_update(bot, click(button(bot.session.sent[-1], "🎙 5 сек"), mid=11))
    document = next(item for item in bot.session.sent if isinstance(item, SendDocument))
    assert "Длительность записи: 1.00 сек." in document.caption
    assert "Запись короче запрошенных 5 сек." in document.caption


async def test_mutation_button_is_bound_to_station_and_user(service, bot):
    dp = make_dispatcher(service)
    await dp.feed_update(bot, click("act:mini:volume_get"))
    data = button(bot.session.sent[-1], "25%")
    await service.store.write("INSERT INTO members VALUES (2,'operator')")
    await dp.feed_update(bot, click(data, user=2, mid=11))
    assert "другому пользователю" in bot.session.sent[-1].text
    await service.store.select(1, "station")
    await dp.feed_update(bot, click(data, mid=12))
    assert "другую станцию" in bot.session.sent[-1].text
    assert not any(r.method == "POST" for f in service.fakes for r in f.requests)


async def test_viewer_sees_reading_without_mutating_controls(service, bot):
    await service.store.write("INSERT INTO members VALUES (2,'viewer')")
    dp = make_dispatcher(service)
    await dp.feed_update(bot, click("act:mini:volume_get", user=2))
    labels = [b.text for row in bot.session.sent[-1].reply_markup.inline_keyboard for b in row]
    assert "25%" not in labels and "🏠 Главное меню" in labels


async def test_logo_only_station_exposes_working_led_controls(service, bot, monkeypatch):
    async def logo_only():
        return Device("yandexmini_3_pro", "aarch64", frozenset({"led.logo"}), 0, 6)

    monkeypatch.setattr(service.clients["mini"], "device", logo_only)
    _, menu = await main_menu(service, 1)
    assert any(b.text == "🌈 Подсветка" for row in menu.inline_keyboard for b in row)
    dp = make_dispatcher(service)
    await dp.feed_update(bot, click("guide:mini:led"))
    panel = bot.session.sent[-1]
    labels = [b.text for row in panel.reply_markup.inline_keyboard for b in row]
    assert "🔴 Красный" in labels and "🔅 Штатная подсветка" in labels
    assert "🌈 Радуга" not in labels and "🎨 Свой цвет кольца" not in labels
    await dp.feed_update(bot, click(button(panel, "🔴 Красный"), mid=11))
    assert any(r.url.path == "/api/led/logo" and r.method == "POST" for r in service.fakes[0].requests)
    await asyncio.sleep(0.11)
    await dp.feed_update(bot, click("guide:mini:led", mid=12))
    await dp.feed_update(bot, click(button(bot.session.sent[-1], "🔅 Штатная подсветка"), mid=13))
    assert any(r.url.path == "/api/led/off/logo" and r.method == "POST" for r in service.fakes[0].requests)


async def test_station_with_ring_and_logo_keeps_separate_controls(service, bot):
    dp = make_dispatcher(service)
    await dp.feed_update(bot, click("guide:mini:led"))
    panel = bot.session.sent[-1]
    labels = [b.text for row in panel.reply_markup.inline_keyboard for b in row]
    assert "🌈 Радуга" in labels and "✨ Цвет логотипа" in labels
    await dp.feed_update(bot, click(button(panel, "🔴 Красный"), mid=11))
    assert any(r.url.path == "/api/led/ring" and r.method == "POST" for r in service.fakes[0].requests)


async def test_experimental_max_ring_uses_capabilities(service, bot, monkeypatch):
    async def max_device():
        return Device("yandexstation_max", "aarch64", frozenset({"led.ring.rgb", "led.ring.24"}), 24, 0)

    monkeypatch.setattr(service.clients["mini"], "device", max_device)
    _, menu = await main_menu(service, 1)
    assert any(b.text == "🌈 Подсветка" for row in menu.inline_keyboard for b in row)
    dp = make_dispatcher(service)
    await dp.feed_update(bot, click("guide:mini:led"))
    await dp.feed_update(bot, click(button(bot.session.sent[-1], "🔴 Красный"), mid=11))
    assert any(r.url.path == "/api/led/ring" and r.method == "POST" for r in service.fakes[0].requests)


async def test_unavailable_led_zones_do_not_offer_commands(service, bot, monkeypatch):
    async def no_led():
        return Device("yandexmini_3_pro", "aarch64", frozenset(), 0, 0)

    monkeypatch.setattr(service.clients["mini"], "device", no_led)
    _, menu = await main_menu(service, 1)
    assert all(b.text != "🌈 Подсветка" for row in menu.inline_keyboard for b in row)
    dp = make_dispatcher(service)
    await dp.feed_update(bot, click("guide:mini:led"))
    labels = [b.text for row in bot.session.sent[-1].reply_markup.inline_keyboard for b in row]
    assert "🔴 Красный" not in labels and "🔅 Штатная подсветка" not in labels


async def test_expired_button_does_not_reach_hardware(service, bot):
    dp = make_dispatcher(service)
    await dp.feed_update(bot, click("act:mini:volume_get"))
    data = button(bot.session.sent[-1], "25%")
    ui = dp["interface"]
    token = data[2:]
    ui.buttons[token] = replace(ui.buttons[token], expires=time.monotonic() - 1)
    await dp.feed_update(bot, click(data, mid=11))
    assert "устарела" in bot.session.sent[-1].text
    assert not any(r.method == "POST" for r in service.fakes[0].requests)


async def test_prompt_accepts_text_and_cancel_prevents_execution(service, bot):
    dp = make_dispatcher(service)
    await dp.feed_update(bot, click("guide:mini:system"))
    await dp.feed_update(bot, click(button(bot.session.sent[-1], "💡 Предложить улучшение"), mid=11))
    assert "Жду ваше сообщение" in bot.session.sent[-1].text
    await dp.feed_update(bot, update("<b>Идея</b> & текст", mid=12))
    rows = await service.store.rows("SELECT text FROM suggestions")
    assert [r['text'] for r in rows] == ["<b>Идея</b> & текст"]
    await dp.feed_update(bot, click("guide:mini:system", mid=13))
    await dp.feed_update(bot, click(button(bot.session.sent[-1], "💡 Предложить улучшение"), mid=14))
    await dp.feed_update(bot, update("/cancel", mid=15))
    await dp.feed_update(bot, update("do not save this", mid=16))
    assert len(await service.store.rows("SELECT text FROM suggestions")) == 1


@pytest.mark.parametrize("page", ["led", "record", "call", "theme", "tts", "siren", "timer", "backup", "terminal", "camera", "ask", "system"])
async def test_every_original_section_is_an_html_panel_with_navigation(service, bot, page):
    await make_dispatcher(service).feed_update(bot, click(f"guide:mini:{page}"))
    panel = bot.session.sent[-1]
    assert panel.parse_mode == "HTML" and panel.text.startswith("<b>")
    assert panel.reply_markup and button(panel, "🏠 Главное меню")
    assert not panel.text.startswith(("{", "[", "/"))
    assert all(r.method == "GET" for f in service.fakes for r in f.requests)


def test_html_escapes_device_data_and_keeps_long_output_bounded():
    for action, data in [("shell", {"exit_code": 0, "stdout": "<>&" * 10000}),
                         ("dialogs", [{"question": "<b>injection</b>", "answer": "&" * 10000}]),
                         ("sounds", [{"name": "<script>.wav", "bytes": 2048}]),
                         ("status", {"online": True})]:
        text = result_card(action, data, "<Unsafe station>")
        assert len(text) <= 4096 and "<Unsafe station>" not in text and "<script>" not in text
        assert '"exit_code"' not in text and '"online"' not in text
    assert "Пакеты пока не установлены" in result_card("plugins", [])
    assert "Плеер пока не подключён" in result_card("media_get", {"providers": []})


async def test_soundboard_filename_is_not_embedded_in_callback_data(service, bot):
    name = "owner_sound_" + "a" * 60 + ".wav"
    service.features.assets.put("sounds", name, b"RIFF")
    dp = make_dispatcher(service)
    await dp.feed_update(bot, click("guide:mini:soundboard"))
    panel = bot.session.sent[-1]
    assert name in panel.text
    controls = [b for row in panel.reply_markup.inline_keyboard for b in row]
    assert any(b.text.startswith("▶️") for b in controls)
    assert all(len(b.callback_data.encode()) <= 64 and name not in b.callback_data for b in controls)
    assert not any(r.method == "POST" for r in service.fakes[0].requests)


async def test_formatted_diagnostics_does_not_change_http_contract(service, bot):
    await make_dispatcher(service).feed_update(bot, click("act:mini:health"))
    assert "40 °C" in bot.session.sent[-1].text
    assert not any(json.dumps(key) + ":" in bot.session.sent[-1].text for key in ("sensors", "model", "kind"))
