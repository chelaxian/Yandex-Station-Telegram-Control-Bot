import subprocess
import sys
import zipfile

import pytest

from scripts.build_max_probe import PROBES, build


def test_audio_archive_is_reproducible_and_runs(tmp_path):
    first, second = tmp_path / "first.pyz", tmp_path / "second.pyz"
    assert build("audio", first) == build("audio", second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert set(archive.namelist()) == {"__main__.py"} | {
            f"stationbot/{name}" for name in PROBES["audio"]["files"]
        }
    result = subprocess.run([sys.executable, str(first), "--help"], capture_output=True, timeout=10)
    assert result.returncode == 0


def test_unknown_probe_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        build("installer", tmp_path / "invalid.pyz")
