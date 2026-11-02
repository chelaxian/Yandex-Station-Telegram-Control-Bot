import hashlib
import io
import json
import wave
import zipfile

import pytest

from stationbot.assets import Assets
from stationbot.assistant import calculate
from stationbot.audio import effect, normalize_wav
from stationbot.errors import InvalidInput, Unavailable


def test_backup_restore_verifies_hashes_and_retains_previous(tmp_path):
    assets = Assets(tmp_path)
    assets.put("sounds", "one.wav", b"original")
    backup = assets.backup()
    assets.put("scripts", "old.sh", b"echo old")
    assert assets.restore(backup) == 1
    assert assets.get("sounds", "one.wav") == b"original"
    assert len(list(tmp_path.glob("assets-previous-*"))) == 1
    assert not (tmp_path / "assets/scripts/old.sh").exists()


@pytest.mark.parametrize("name", ["../../outside", "scripts/../../x", "scripts/evil\\name", "/tmp/x"])
def test_restore_rejects_paths_without_changing_existing(tmp_path, name):
    assets = Assets(tmp_path)
    assets.put("settings", "old.json", b"{}")
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr(name, b"bad")
        archive.writestr("manifest.json", json.dumps({"format": 1, "files": {name: hashlib.sha256(b"bad").hexdigest()}}))
    with pytest.raises(InvalidInput):
        assets.restore(data.getvalue())
    assert assets.get("settings", "old.json") == b"{}"


def test_restore_rejects_tamper_and_duplicate_entries(tmp_path):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("scripts/file.sh", b"bad")
        archive.writestr("manifest.json", json.dumps({"format": 1, "files": {"scripts/file.sh": "0" * 64}}))
    with pytest.raises(InvalidInput):
        Assets(tmp_path).restore(data.getvalue())


def test_effect_is_bounded_wav_and_pipe_wav_gets_finite_header():
    data = effect("siren", 1)
    unknown = bytearray(data)
    unknown[4:8] = b"\xff" * 4
    unknown[40:44] = b"\xff" * 4
    with wave.open(io.BytesIO(normalize_wav(bytes(unknown)))) as sound:
        assert sound.getnframes() == 48000
        assert sound.getframerate() == 48000
        assert sound.getsampwidth() == 2
    with pytest.raises(InvalidInput):
        effect("siren", 300)


def test_calculator_never_executes_python():
    assert calculate("2*(3+4)") == 14
    for value in ["__import__('os').system('x')", "2**10000", "[1]*1000000"]:
        with pytest.raises(ValueError):
            calculate(value)


def test_legacy_backup_import_preserves_files_without_executing(tmp_path):
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as old:
        old.writestr("sounds/test.wav", b"old sound")
        old.writestr("configs/custom_actions.json", b"[]")
        old.writestr("station/custom_scripts/test.sh", b"echo legacy")
    assets = Assets(tmp_path)
    assert assets.restore(assets.import_legacy(data.getvalue())) == 3
    assert assets.get("scripts", "test.sh") == b"echo legacy"
    assert assets.get("settings", "legacy_custom_actions.json") == b"[]"


def test_legacy_backup_does_not_accept_arbitrary_system_files():
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as old:
        old.writestr("etc/passwd", b"not an application backup")
    with pytest.raises(InvalidInput):
        Assets.import_legacy(data.getvalue())


async def test_unqualified_audio_and_owner_tools_fail_closed(service):
    client = service.clients["mini"]
    with pytest.raises(Unavailable):
        await client.play(effect("alarm", 1), "test-key")
    with pytest.raises(Unavailable):
        await client.shell("echo safe")
    assert all("owner" not in str(r.url) for r in service.fakes[0].requests)


async def test_viewer_cannot_backup_shell_or_start_siren(service):
    await service.store.write("INSERT INTO members VALUES (?,?)", (2, "viewer"))
    for action in ["backup", "shell", "siren", "play_upload", "upload_script"]:
        from stationbot.errors import Forbidden
        with pytest.raises(Forbidden):
            await service.run(2, "mini", action, [], action)
    assert not service.fakes[0].requests
