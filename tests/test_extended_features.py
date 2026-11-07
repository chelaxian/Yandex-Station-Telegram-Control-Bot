import io
import struct
import wave
import zipfile
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from stationbot.audio import effect
from stationbot.errors import Forbidden, TransportError, Unavailable
from stationbot.luna import Device, Luna

JOB = {"id": "2e0c280b-6ae7-459a-a9a1-985d92463517", "state": "queued", "cleanup": "pending"}


async def test_audio_uses_bounded_job_contract_and_never_retries_post(config):
    requests = []
    def response(request):
        requests.append(request)
        if request.url.path.endswith("device"):
            return httpx.Response(200, json={"model": "yandexmini_3_pro", "architecture": "aarch64", "features": ["audio.jobs.v1"]})
        return httpx.Response(202, json=JOB)
    client = Luna(config.stations[0], transport=httpx.MockTransport(response))
    try:
        assert (await client.play(effect("alarm", 1), "request-1"))["id"] == JOB["id"]
        assert requests[-1].headers["Idempotency-Key"] == "request-1"
        assert requests[-1].content[:4] == b"RIFF"
        assert requests[-1].url.path == "/api/audio/jobs"
    finally:
        await client.close()


async def test_plum_playback_follows_station_volume_and_blocks_zero(config):
    async def check(percent):
        requests = []
        def response(request):
            requests.append(request)
            if request.url.path.endswith("device"):
                return httpx.Response(200, json={"model": "yandexplum", "architecture": "aarch64",
                                               "features": ["audio.jobs.v1", "audio.volume.alsa"]})
            if request.url.path.endswith("volume"):
                return httpx.Response(200, json={"percent": percent})
            return httpx.Response(202, json=JOB)
        station = replace(config.stations[0], expected_model="yandexplum")
        client = Luna(station, transport=httpx.MockTransport(response))
        try:
            result = await client.play(effect("alarm", 1), f"plum-{percent}")
            return result, requests
        finally:
            await client.close()

    result, requests = await check(40)
    assert result["station_volume_percent"] == 40
    assert result["playback_volume_percent"] == 40
    with wave.open(io.BytesIO(requests[-1].content), "rb") as wav:
        assert max(abs(sample) for sample in struct.unpack(f"<{wav.getnframes()}h", wav.readframes(wav.getnframes()))) <= 1801

    with pytest.raises(Unavailable):
        await check(0)


@pytest.mark.parametrize("job", [{}, {**JOB, "id": "../../shell"}, {**JOB, "state": "done"}, {**JOB, "cleanup": False}])
def test_untrusted_job_cannot_be_used_as_endpoint(job):
    with pytest.raises(TransportError):
        Luna.audio_job(job)


async def test_owner_tools_are_typed_and_source_qualified(config):
    requests = []
    def response(request):
        requests.append(request)
        if request.url.path.endswith("device"):
            return httpx.Response(200, json={"model": "yandexmini_3_pro", "architecture": "aarch64", "features": ["owner.tools.v1"]})
        return httpx.Response(200, json={"exit_code": 0, "stdout": "ok", "timed_out": False})
    client = Luna(replace(config.stations[0], allow_owner_tools=True), transport=httpx.MockTransport(response))
    try:
        assert (await client.shell("printf ok"))["exit_code"] == 0
        assert requests[-1].url.path == "/api/owner/execute"
        assert b'"timeout":15' in requests[-1].content
    finally:
        await client.close()


async def test_intercom_is_opt_in_bounded_and_cancellable(service):
    client = service.clients["mini"]
    client.device = AsyncMock(return_value=Device("yandexmini_3_pro", "aarch64", frozenset({"audio.jobs.v1", "microphone.capture"}), 16, 6))
    client.play = AsyncMock(return_value=JOB)
    client.stop_audio = AsyncMock(return_value=[])
    message = SimpleNamespace(chat=SimpleNamespace(id=1), answer=AsyncMock())
    assert not service.interactions.calls
    await service.interactions.command(message, 1, "mini", "call", [])
    assert not service.interactions.calls["mini"].active
    await service.interactions.command(message, 1, "mini", "answer", [])
    assert service.interactions.calls["mini"].active
    await service.interactions.command(message, 1, "mini", "hangup", [])
    assert not service.interactions.calls
    await service.interactions.close()


async def test_viewer_cannot_enable_background_capture(service):
    await service.store.write("INSERT INTO members VALUES (?,?)", (2, "viewer"))
    for command, args in [("call", []), ("guard", ["on"]), ("led_effect", ["rainbow"])]:
        with pytest.raises(Forbidden):
            await service.interactions.command(SimpleNamespace(), 2, "mini", command, args)
    assert not service.interactions.calls and not service.interactions.guards


async def test_backup_includes_dialogs_and_suggestions_without_credentials(service):
    await service.store.write("INSERT INTO dialogs VALUES (?,?,?,?)", ("mini", "question", "answer", 1))
    await service.store.write("INSERT INTO suggestions VALUES (?,?,?)", (1, "idea", 2))
    data = await service.features.execute(service.clients["mini"], "backup", [])
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert set(archive.namelist()) == {"dialogs/dialogs.json", "settings/suggestions.json", "manifest.json"}
        assert b"question" in archive.read("dialogs/dialogs.json")


async def test_restore_then_run_script_uses_restored_source(service):
    features = service.features
    features.assets.put("scripts", "action.sh", b"printf restored")
    data = features.assets.backup()
    features.assets.delete("scripts", "action.sh")
    await features.execute(service.clients["mini"], "restore", [], data)
    client = SimpleNamespace(owner=AsyncMock(return_value={"exit_code": 0}))
    await features.execute(client, "run_script", ["action.sh"])
    assert client.owner.call_args.kwargs["json"] == {"name": "action.sh", "source": "printf restored"}


async def test_intercom_does_not_capture_its_own_playback(service):
    from conftest import wav_bytes

    from stationbot.interactions import Session
    client = service.clients["mini"]
    session = Session(1, 1, active=True)
    client.stop_audio = AsyncMock(return_value=[])
    client.audio_jobs = AsyncMock(side_effect=[[{**JOB, "state": "playing"}], []])
    async def record(seconds):
        session.end_requested = True
        return wav_bytes(5)
    client.record = AsyncMock(side_effect=record)
    message = SimpleNamespace(answer=AsyncMock(), answer_audio=AsyncMock())
    await service.interactions._intercom(message, "mini", session)
    assert client.audio_jobs.await_count == 2
    client.record.assert_awaited_once_with(5)
    message.answer_audio.assert_awaited_once()


async def test_intercom_stops_when_microphone_returns_short_fragment(service):
    from conftest import wav_bytes

    from stationbot.interactions import Session
    client = service.clients["mini"]
    session = Session(1, 1, active=True)
    client.stop_audio = AsyncMock(return_value=[])
    client.audio_jobs = AsyncMock(return_value=[])
    client.record = AsyncMock(return_value=wav_bytes(1))
    message = SimpleNamespace(answer=AsyncMock(), answer_audio=AsyncMock())
    service.interactions.calls["mini"] = session
    await service.interactions._intercom(message, "mini", session)
    message.answer_audio.assert_not_awaited()
    assert any("слишком короткий фрагмент" in call.args[0] for call in message.answer.await_args_list)
    assert "mini" not in service.interactions.calls
    assert client.stop_audio.await_count == 2


async def test_voice_hangup_uses_verified_transcript_event(service):
    from stationbot.interactions import Session
    session = Session(1, 1, active=True)
    client = SimpleNamespace(json=AsyncMock(return_value={"transcript": "Алиса, отбой!"}))
    await service.interactions._voice_hangup(client, session)
    assert session.end_requested


async def test_theme_is_per_station_and_toggles_are_persisted(service):
    mini, station = service.clients["mini"], service.clients["station"]
    await service.features.execute(mini, "theme", ["windows"])
    await service.features.execute(mini, "theme_flags", ["reply", "on"])
    assert (await service.features.theme_settings(mini))["theme"] == "windows"
    assert (await service.features.theme_settings(mini))["reply"] is True
    assert (await service.features.theme_settings(station))["theme"] == "off"


async def test_theme_does_not_replay_snapshots_or_repeated_phases(service):
    import asyncio

    from stationbot.interactions import Session
    client = service.clients["mini"]
    await service.features.execute(client, "theme", ["mario"])
    client.owner = AsyncMock(side_effect=[
        {"phase": "listening", "initial_snapshot": True},
        {"phase": "idle", "initial_snapshot": False},
        {"phase": "listening", "initial_snapshot": False},
        {"phase": "listening", "initial_snapshot": False},
        {"phase": "speaking", "initial_snapshot": False}, asyncio.CancelledError(),
    ])
    client.audio_jobs = AsyncMock(return_value=[])
    service.features.theme_sound = AsyncMock(return_value=JOB)
    with pytest.raises(asyncio.CancelledError):
        await service.interactions._theme("mini", Session(1, 1))
    service.features.theme_sound.assert_awaited_once_with(client, "ask")
