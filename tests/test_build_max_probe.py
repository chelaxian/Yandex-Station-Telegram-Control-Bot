from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from scripts.build_max_probe import PROBES, build


def test_audio_probe_archive_contains_only_intended_modules(tmp_path):
    output = tmp_path / "max-audio-probe.pyz"
    with patch("scripts.build_max_probe.shutil.copy2") as copy, patch(
        "scripts.build_max_probe.hashlib.sha256",
        return_value=Mock(hexdigest=Mock(return_value="digest")),
    ) as digest_factory:
        assert build("audio", output) == "digest"
    copied = {Path(call.args[0]).name for call in copy.call_args_list}
    assert copied == set(PROBES["audio"]["files"])
    digest_factory.assert_called_once_with(output.read_bytes())


def test_unknown_probe_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        build("installer", tmp_path / "invalid.pyz")
