from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from stationbot.max_audio_probe import probe_max_audio
from stationbot.max_ssh_probe import MaxSshTarget
from stationbot.provision import ProvisionError


def test_audio_probe_is_read_only_after_identity_check():
    target = MaxSshTarget("192.168.1.5", "root", 2222)
    output = "MAX_AUDIO_PROBE_V1\n--- /proc/asound/cards\n0 Max"
    with (
        patch("stationbot.max_audio_probe.probe_max_ssh") as identity,
        patch(
            "stationbot.max_audio_probe.subprocess.run",
            return_value=SimpleNamespace(returncode=0, stdout=output),
        ) as run,
    ):
        assert probe_max_audio(target).startswith("--- /proc/asound/cards")
    identity.assert_called_once_with(target, "ssh")
    args = run.call_args.args[0]
    assert "StrictHostKeyChecking=yes" in args and "BatchMode=yes" in args
    command = args[-1]
    # Android toybox printf treats -- as the format string, not an option terminator.
    assert "printf --" not in command
    assert "/proc/asound/cards" in command and "/dev/snd/pcmC*D*" in command
    assert "pidof" in command and "maind aliced yio_audio" in command
    assert "/system/vendor/quasar/quasar.cfg" in command
    assert all(
        word not in command
        for word in ("tinyplay", "tinymix", "aplay", "arecord", "chmod", "reboot")
    )


def test_audio_probe_requires_exact_marker_and_output():
    target = MaxSshTarget("192.168.1.5", "root")
    for stdout in ("", "noise", "MAX_AUDIO_PROBE_V1\nMAX_AUDIO_PROBE_V1\ndata"):
        with patch("stationbot.max_audio_probe.probe_max_ssh", Mock()):
            with patch(
                "stationbot.max_audio_probe.subprocess.run",
                return_value=SimpleNamespace(returncode=0, stdout=stdout),
            ):
                with pytest.raises(ProvisionError):
                    probe_max_audio(target)


def test_audio_ssh_failure_does_not_disclose_remote_output():
    target = MaxSshTarget("192.168.1.5", "root")
    with patch("stationbot.max_audio_probe.probe_max_ssh", Mock()):
        with patch(
            "stationbot.max_audio_probe.subprocess.run",
            return_value=SimpleNamespace(returncode=255, stdout="", stderr="sensitive"),
        ):
            with pytest.raises(ProvisionError) as error:
                probe_max_audio(target)
    assert "sensitive" not in str(error.value)
