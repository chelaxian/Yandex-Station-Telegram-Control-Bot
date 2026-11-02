import asyncio

import httpx
import pytest
from conftest import device

from stationbot.config import StationConfig
from stationbot.errors import InvalidInput, TransportError, Unavailable
from stationbot.luna import Luna


async def test_model_mismatch_prevents_physical_write(config):
    calls = []
    def handler(req):
        calls.append(req.method)
        return httpx.Response(200, json=device("yandexmidi"))
    client = Luna(config.stations[0], transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(Unavailable, match="expected_model"):
            await client.volume(30)
        assert calls == ["GET"]
    finally:
        await client.close()


async def test_station_without_clock_does_not_write(service):
    with pytest.raises(Unavailable, match="часов"):
        await service.clients["station"].clock("12:34")
    assert all(req.method == "GET" for req in service.fakes[1].requests)


async def test_topology_rejects_absent_logo(service):
    with pytest.raises(Unavailable, match="отсутствует"):
        await service.clients["station"].led("logo", "#FFFFFF")


async def test_volume_range_and_color_validation(service):
    for value in [-1, 101, True]:
        with pytest.raises(InvalidInput):
            await service.clients["mini"].volume(value)
    with pytest.raises(InvalidInput):
        await service.clients["mini"].led("ring", "red; reboot")
    assert all(r.method == "GET" for r in service.fakes[0].requests)


async def test_mutation_timeout_is_not_retried(config):
    mutations = []
    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, json=device())
        mutations.append(req)
        raise httpx.ReadTimeout("secret URL must not be shown")
    client = Luna(config.stations[0], transport=httpx.MockTransport(handler))
    try:
        with pytest.raises(TransportError) as error:
            await client.volume(30)
        assert "secret" not in str(error.value)
        assert len(mutations) == 1
    finally:
        await client.close()


async def test_read_retries_once(config):
    attempts = 0
    def handler(req):
        nonlocal attempts
        attempts += 1
        return httpx.Response(503) if attempts == 1 else httpx.Response(200, json=device())
    client = Luna(config.stations[0], transport=httpx.MockTransport(handler))
    try:
        assert (await client.device()).model == "yandexmini_3_pro"
        assert attempts == 2
    finally:
        await client.close()


async def test_recording_validates_channel_and_wav(service):
    assert (await service.clients["mini"].record(1)).startswith(b"RIFF")
    with pytest.raises(Unavailable):
        await service.clients["mini"].record(1, "../../data")
    with pytest.raises(InvalidInput):
        await service.clients["mini"].record(31)


async def test_oversized_and_redirect_responses_fail_closed(config):
    for response in [httpx.Response(200, headers={"content-length": "9999999999"}),
                     httpx.Response(302, headers={"location": "http://evil.invalid"}),
                     httpx.Response(200, text="not JSON")]:
        client = Luna(config.stations[0], transport=httpx.MockTransport(lambda req, response=response: response))
        try:
            with pytest.raises(TransportError):
                await client.device()
        finally:
            await client.close()


@pytest.mark.parametrize("url", ["http://10.0.0.1/api", "https://remote.example/api", "http://user:pass@localhost/api", "http://localhost/api?token=x"])
def test_unprotected_remote_url_rejected(url):
    with pytest.raises(InvalidInput):
        StationConfig("test", "Test", url, "test")


async def test_stations_are_independent(service):
    a, b = await asyncio.gather(service.clients["mini"].device(), service.clients["station"].device())
    assert a.model != b.model
    assert a.ring_count == 16 and b.ring_count == 89
