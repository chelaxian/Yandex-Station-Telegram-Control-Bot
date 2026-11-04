from unittest.mock import AsyncMock

import pytest

from stationbot.discovery import discover
from stationbot.errors import InvalidInput
from stationbot.provision import Adb, ProvisionError, serial_address


@pytest.mark.parametrize("address", ["198.18.0.1", "198.19.255.1", "169.254.1.2",
                                     "100.64.0.2", "127.0.0.1", "240.0.0.1", "8.8.8.8"])
async def test_non_lan_targets_rejected_before_connect(monkeypatch, address):
    connect = AsyncMock()
    monkeypatch.setattr("stationbot.discovery.asyncio.open_connection", connect)
    with pytest.raises(ProvisionError):
        Adb("adb", address)
    with pytest.raises(InvalidInput):
        await discover(address + "/24")
    connect.assert_not_awaited()


@pytest.mark.parametrize("address", ["10.20.1.2", "172.16.1.2", "172.31.255.1", "192.168.5.4"])
def test_lan_addresses_remain_valid(address):
    assert serial_address(address) == address + ":5555"


async def test_explicit_lan_scan_is_bounded_and_never_uses_default_route(monkeypatch):
    connect = AsyncMock(side_effect=OSError("closed"))
    monkeypatch.setattr("stationbot.discovery.asyncio.open_connection", connect)
    assert await discover("192.168.5.0/30") == []
    assert [call.args for call in connect.await_args_list] == [
        ("192.168.5.1", 5555), ("192.168.5.2", 5555),
    ]


@pytest.mark.parametrize("cidr", ["10.0.0.0/8", "192.168.0.0/16", "::1/128", "invalid"])
async def test_large_or_invalid_networks_never_scanned(monkeypatch, cidr):
    connect = AsyncMock()
    monkeypatch.setattr("stationbot.discovery.asyncio.open_connection", connect)
    with pytest.raises(InvalidInput):
        await discover(cidr)
    connect.assert_not_awaited()
