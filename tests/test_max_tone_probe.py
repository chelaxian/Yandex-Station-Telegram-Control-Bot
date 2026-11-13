from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from stationbot.max_ssh_probe import MaxSshTarget
from stationbot.max_tone_probe import run_tone
from stationbot.provision import ProvisionError


def test_tone_verifies_identity_and_uses_private_temporary_payload():
    target = MaxSshTarget("192.168.1.5", "root", 2222, "separate-config")
    resource = Mock()
    resource.joinpath.return_value.read_bytes.return_value = b"fake jar"
    result = SimpleNamespace(returncode=0, stdout="MAX_TONE_RESULT written=24000 played=24000\n", stderr="")
    with patch("stationbot.max_tone_probe.probe_max_ssh") as identity, \
         patch("stationbot.max_tone_probe.importlib.resources.files", return_value=resource), \
         patch("stationbot.max_tone_probe.subprocess.run", return_value=result) as run:
        assert "played=24000" in run_tone(target)
    identity.assert_called_once_with(target, "ssh")
    args = run.call_args.args[0]
    assert "StrictHostKeyChecking=yes" in args and "separate-config" in args
    assert "mktemp -d" in args[-1] and "trap " in args[-1] and "app_process" in args[-1]
    assert "/dev/snd" not in args[-1]


def test_tone_failure_and_missing_marker_are_not_success():
    target = MaxSshTarget("192.168.1.5", "root")
    resource = Mock()
    resource.joinpath.return_value.read_bytes.return_value = b"jar"
    with patch("stationbot.max_tone_probe.probe_max_ssh"), \
         patch("stationbot.max_tone_probe.importlib.resources.files", return_value=resource):
        for result in (SimpleNamespace(returncode=1, stdout="", stderr="private"),
                       SimpleNamespace(returncode=0, stdout="", stderr="")):
            with patch("stationbot.max_tone_probe.subprocess.run", return_value=result):
                with pytest.raises(ProvisionError) as error:
                    run_tone(target)
                assert "private" not in str(error.value)
