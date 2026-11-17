import io
import json
import shutil
import socket
import subprocess
import threading
import time
import urllib.request
import wave
from http.server import ThreadingHTTPServer

import pytest

from stationbot import max_gateway as g
from stationbot.max_ssh_probe import MaxSshTarget

JOB = "11111111-2222-4333-8444-555555555555"


def wav(rate=48000, width=2, frames=480, channels=1):
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(b"\0" * frames * width * channels)
    return out.getvalue()


def test_scripts_are_single_line_posix_shell():
    scripts = [g.volume_script(), g.volume_script(40), g.play_script(g.play_directory(JOB), "QUJD"),
               g.stop_script(g.play_directory(JOB)), g.cleanup_script(g.play_directory(JOB))]
    for script in scripts:
        assert "\n" not in script and "\r" not in script
    bash = shutil.which("bash")
    if bash:
        for script in scripts:
            assert subprocess.run([bash, "-n", "-c", script], capture_output=True).returncode == 0


def test_script_inputs_are_validated():
    for bad in (-1, 101, True, "5"):
        with pytest.raises(g.GatewayError):
            g.volume_script(bad)
    with pytest.raises(g.GatewayError):
        g.play_script("/data/local/tmp/../etc", "x")
    with pytest.raises(ValueError):
        g.play_directory("not-a-uuid; rm -rf /")


def test_parse_volume():
    assert g.parse_volume("[v] volume is 9 in range [0..100]") == 9
    assert g.parse_volume("volume is 5 in range [0..100]\nvolume is 9 in range [0..100]") == 9
    assert g.parse_volume("volume is 7 in range [0..15]") == 47
    for bad in ("", "volume is 200 in range [0..100]", "volume is 1 in range [5..5]"):
        with pytest.raises(g.GatewayError):
            g.parse_volume(bad)


def test_wav_validation():
    assert g.validate_wav(wav()) == pytest.approx(0.01)
    assert g.validate_wav(wav(channels=2, rate=44100)) > 0
    for bad in (wav(width=1), wav(rate=96000), wav(frames=0), b"x" * 100):
        with pytest.raises(g.GatewayError):
            g.validate_wav(bad)
    assert g.validate_wav(g.test_tone()) == pytest.approx(0.5)


class FakeStation(g.MaxStation):
    def __init__(self):
        super().__init__(MaxSshTarget("192.168.0.9", "root"))
        self.level = 30

    def run(self, command, data=None, timeout=20):
        raise AssertionError("SSH must not be used in this test")

    def volume(self, percent=None):
        if percent is not None:
            self.level = percent
        return self.level

    def _play(self, job):
        job.state = "cancelled" if job.cancel.is_set() else "succeeded"

    def _cleanup(self, job):
        job.cleanup = "complete"


@pytest.fixture
def api():
    station = FakeStation()
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    server = ThreadingHTTPServer(("127.0.0.1", port), g.make_handler(station, port))
    threading.Thread(target=server.serve_forever, daemon=True).start()

    def call(method, path, body=None, headers=None):
        req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, method=method,
                                     headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status, json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read() or b"null")

    yield call, port
    server.shutdown()
    server.server_close()


def test_device_contract_matches_bot_parser(api):
    from stationbot.luna import Device
    call, _ = api
    status, raw = call("GET", "/api/device")
    device = Device.parse(raw)
    assert status == 200 and device.model == "yandexstation_max"
    assert "audio.jobs.v1" in device.features and "microphone.capture" not in device.features
    assert not any(f.startswith("led.") for f in device.features) and device.ring_count == 0


def test_volume_and_jobs(api):
    call, _ = api
    assert call("GET", "/api/volume") == (200, {"percent": 30})
    assert call("POST", "/api/volume", b'{"percent": 55}') == (200, {"percent": 55})
    assert call("POST", "/api/volume", b'{"percent": 101}')[0] == 400
    status, job = call("POST", "/api/audio/jobs", wav(), {"Idempotency-Key": "k1"})
    assert status == 202 and job["state"] in {"queued", "playing", "succeeded"}
    assert call("POST", "/api/audio/jobs", wav(), {"Idempotency-Key": "k1"})[1]["id"] == job["id"]
    for _ in range(50):
        state = call("GET", f"/api/audio/jobs/{job['id']}")[1]
        if state["state"] == "succeeded" and state["cleanup"] == "complete":
            break
        time.sleep(0.05)
    assert state["state"] == "succeeded" and state["cleanup"] == "complete"
    assert call("POST", "/api/audio/jobs", wav(width=1))[0] == 400
    assert call("GET", f"/api/audio/jobs/{JOB}")[0] == 404
    assert call("GET", "/api/unknown")[0] == 404


def test_rejects_foreign_host_header(api):
    call, _ = api
    assert call("GET", "/api/device", headers={"Host": "evil.example:80"})[0] == 403


def test_bot_adapter_refuses_playback_at_zero_volume():
    import asyncio

    import httpx

    from stationbot.config import StationConfig
    from stationbot.errors import Unavailable
    from stationbot.luna import Luna

    def handler(request):
        if request.url.path == "/api/device":
            return httpx.Response(200, json={"model": "yandexstation_max", "architecture": "aarch64",
                                             "features": g.FEATURES, "led": {"ring_count": 0}})
        if request.url.path == "/api/volume":
            return httpx.Response(200, json={"percent": 0})
        return httpx.Response(500)

    async def run():
        client = Luna(StationConfig("max", "Max", "http://127.0.0.1:18300/api", "yandexstation_max"),
                      transport=httpx.MockTransport(handler))
        with pytest.raises(Unavailable):
            await client.play(wav(), "key")
        await client.close()

    asyncio.run(run())
