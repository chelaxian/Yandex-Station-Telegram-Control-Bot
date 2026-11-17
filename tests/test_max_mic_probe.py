from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from stationbot.max_mic_probe import run_mic
from stationbot.max_ssh_probe import MaxSshTarget
from stationbot.provision import ProvisionError

TARGET = MaxSshTarget("192.168.1.5", "root", 22, "separate")


def _resource():
    resource = Mock()
    resource.joinpath.return_value.read_bytes.return_value = b"jar"
    return resource


def test_mic_probe_prints_only_numeric_evidence_and_cleans_up():
    result = SimpleNamespace(returncode=0, stdout="MAX_MIC_RESULT source=1 rate=16000 frames=32000 nonzero=900 peak=400 rms=33.5\nraw audio\n", stderr="")
    with patch("stationbot.max_mic_probe.probe_max_ssh") as identity, \
         patch("stationbot.max_mic_probe.importlib.resources.files", return_value=_resource()), \
         patch("stationbot.max_mic_probe.subprocess.run", return_value=result) as run:
        output = run_mic(TARGET)
    identity.assert_called_once_with(TARGET, "ssh")
    command = run.call_args.args[0][-1]
    assert output.startswith("MAX_MIC_RESULT") and "raw audio" not in output
    assert "trap 'rm -rf" in command and "MaxMic 1 16000 2" in command and "/dev/snd" not in command
    assert not any(word in command for word in (".wav", "cat >", "tee ", "nc ", "curl"))


def test_invalid_parameters_and_failures_are_not_success():
    with pytest.raises(ProvisionError):
        run_mic(TARGET, source="camera")
    with pytest.raises(ProvisionError):
        run_mic(TARGET, rate=44100)
    for result in (SimpleNamespace(returncode=1, stdout="", stderr="private"),
                   SimpleNamespace(returncode=0, stdout="", stderr="")):
        with patch("stationbot.max_mic_probe.probe_max_ssh"), \
             patch("stationbot.max_mic_probe.importlib.resources.files", return_value=_resource()), \
             patch("stationbot.max_mic_probe.subprocess.run", return_value=result):
            with pytest.raises(ProvisionError) as error:
                run_mic(TARGET)
        assert "private" not in str(error.value)
