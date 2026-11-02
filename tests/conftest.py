import io
import wave
from pathlib import Path

import httpx
import pytest
import pytest_asyncio

from stationbot.config import Config, StationConfig
from stationbot.luna import Luna
from stationbot.service import Service
from stationbot.store import Store


def device(model="yandexmini_3_pro", clock=True):
    return {"model": model, "architecture": "aarch64",
            "features": ["audio.volume.alsa", "microphone.capture", "audio.play.aplay", "led.ring.rgb", "led.logo"]
                        + (["display.clock.segment.v1"] if clock else []),
            "led": {"ring_count": 16 if clock else 89, "logo_count": 6 if clock else 0}}


def wav_bytes(seconds=1):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(b"\x01\x00" * 16000 * seconds)
    return stream.getvalue()


@pytest.fixture
def config(tmp_path: Path):
    return Config(1, (StationConfig("mini", "Мини", "http://127.0.0.1:8100/api", "yandexmini_3_pro"),
                      StationConfig("station", "Станция", "http://127.0.0.1:8101/api", "yandexstation_2")),
                  tmp_path, rate_seconds=0.1)


@pytest_asyncio.fixture
async def store(tmp_path):
    s = Store(tmp_path / "state.db", 1)
    await s.open()
    yield s
    await s.close()


class FakeLuna:
    def __init__(self, clock=True):
        self.requests = []
        self.clock = clock
        self.volume = 20

    def __call__(self, request):
        self.requests.append(request)
        path = request.url.path.removeprefix("/api/")
        if path == "device":
            return httpx.Response(200, json=device("yandexmini_3_pro" if self.clock else "yandexstation_2", self.clock))
        if path == "clock":
            return httpx.Response(200, json={"available": self.clock, "text_available": False, "segments": []})
        if path == "sensors":
            return httpx.Response(200, json=[{"name": "CPU", "kind": "temperature", "value": 40, "unit": "°C"}])
        if path == "volume":
            if request.method == "POST":
                import json
                self.volume = json.loads(request.content)["percent"]
            return httpx.Response(200, json={"percent": self.volume})
        if path == "microphone/devices":
            return httpx.Response(200, json=[{"id": "raw_mic_0", "name": "Raw 0"}])
        if path == "microphone/record":
            return httpx.Response(200, content=wav_bytes(), headers={"content-type": "audio/wav"})
        if path == "plugins":
            return httpx.Response(200, json=[])
        if path == "media":
            return httpx.Response(200, json={"providers": [], "selected": None})
        if path.startswith("led/"):
            return httpx.Response(200, json={})
        return httpx.Response(404, json={"error": "missing"})


@pytest_asyncio.fixture
async def service(config, store):
    fake_mini, fake_station = FakeLuna(), FakeLuna(clock=False)
    clients = {s.id: Luna(s, transport=httpx.MockTransport(fake))
               for s, fake in zip(config.stations, [fake_mini, fake_station], strict=True)}
    service = Service(config, store, clients)
    service.fakes = [fake_mini, fake_station]
    yield service
    for client in clients.values():
        await client.close()
