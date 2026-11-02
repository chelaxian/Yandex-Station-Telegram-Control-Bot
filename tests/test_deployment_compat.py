import json

import pytest
from test_telegram import bot as bot
from test_telegram import update

from stationbot.errors import InvalidInput
from stationbot.legacy_history import read_legacy_history
from stationbot.telegram import make_dispatcher


def test_proxy_only_loaded_from_environment(config, monkeypatch):
    from dataclasses import replace
    config = replace(config, telegram_proxy_env="TEST_TELEGRAM_PROXY")
    with pytest.raises(InvalidInput):
        config.telegram_proxy()
    monkeypatch.setenv("TEST_TELEGRAM_PROXY", "http://127.0.0.1:1081")
    assert config.telegram_proxy() == "http://127.0.0.1:1081"


def test_legacy_history_read_only_and_station_isolated(tmp_path):
    p = tmp_path / "history-mini.json"
    original = json.dumps({"01.11.26": [{"time": "12:00", "user": "volume", "alice": "done", "type": "command"}]})
    p.write_text(original)
    assert "volume" in read_legacy_history(tmp_path, "mini")
    assert "нет сохранённой" in read_legacy_history(tmp_path, "station")
    assert p.read_text() == original


async def test_old_station_command_keeps_selection_per_user(service, bot):
    await make_dispatcher(service).feed_update(bot, update("/station station"))
    assert await service.station_for(1) == "station"
    assert await service.station_for(2) == "mini"


async def test_guest_cannot_read_owner_legacy_history(service, bot):
    await service.store.write("INSERT INTO members VALUES (2,'viewer')")
    await make_dispatcher(service).feed_update(bot, update("/legacy_history", user=2))
    assert "Недостаточно" in bot.session.sent[-1].text


async def test_old_system_alias_uses_luna_without_shell(service, bot):
    await make_dispatcher(service).feed_update(bot, update("/system"))
    assert "sensors" in bot.session.sent[-1].text
    assert all(r.method == "GET" for r in service.fakes[0].requests)


async def test_pending_commands_from_previous_runtime_are_not_replayed(service, bot):
    old = update("/volume 100")
    old = old.model_copy(update={"message": old.message.model_copy(
        update={"date": old.message.date.replace(year=2020)})})
    await make_dispatcher(service).feed_update(bot, old)
    assert not service.fakes[0].requests
    assert not bot.session.sent
