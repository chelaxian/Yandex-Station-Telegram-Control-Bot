import httpx
import pytest
from conftest import device

from stationbot.display import PRESETS, segment_frame
from stationbot.errors import InvalidInput, Unavailable
from stationbot.luna import Luna


def test_display_renders_only_advertised_topology():
    for start in (0, 1):
        available = [f"{p}{i}" for p in "ABCDEFG" for i in range(start, start + 4)]
        for text in PRESETS.values():
            frame = segment_frame(text, 25, available)
            assert frame and set(frame) <= set(available) and set(frame.values()) == {25}
        assert set(segment_frame("1111", 100, available)) == {f"{p}{i}" for p in "BC" for i in range(start, start + 4)}
    with pytest.raises(Unavailable):
        segment_frame("1337", 100, [])
    with pytest.raises(InvalidInput):
        segment_frame("Алиса", 100, [])


async def test_display_uses_actual_zero_based_backend(config):
    calls = []
    def handle(req):
        calls.append(req)
        if req.url.path.endswith("device"):
            return httpx.Response(200, json=device())
        if req.method == "GET":
            return httpx.Response(200, json={"available": True, "text_available": False, "segments": [f"{p}{i}" for p in "ABCDEFGH" for i in range(4)]})
        return httpx.Response(200, json={})
    client = Luna(config.stations[0], transport=httpx.MockTransport(handle))
    try:
        await client.screen("HELP", 25)
        assert b'"F0":25' in calls[-1].content and calls[-1].url.path == "/api/clock"
        before = len(calls)
        with pytest.raises(InvalidInput):
            await client.screen("HELP", 256)
        assert len(calls) == before
    finally:
        await client.close()
