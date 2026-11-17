from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

from stationbot.max_android_probe import probe_max_android
from stationbot.max_ssh_probe import MaxSshTarget
from stationbot.provision import ProvisionError


def _run(output="MAX_ANDROID_PROBE_V1\n--- build\nx\n", code=0):
    return SimpleNamespace(returncode=code, stdout=output, stderr="private")


def test_inventory_is_read_only_and_does_not_play_or_stage_by_default():
    target = MaxSshTarget("192.168.1.5", "root", 2222, "separate")
    with patch("stationbot.max_android_probe.probe_max_ssh") as identity, \
         patch("stationbot.max_android_probe.subprocess.run", return_value=_run()) as run:
        assert probe_max_android(target).startswith("--- build")
    identity.assert_called_once_with(target, "ssh")
    script = run.call_args.kwargs["input"].decode()
    assert run.call_args.args[0][-1] == "sh -s" and "separate" in run.call_args.args[0]
    assert b"\r" not in run.call_args.kwargs["input"]
    assert "app_process" not in script and "mktemp" not in script
    assert all(word not in script for word in ("write(", "setprop", "settings put", "reboot"))
    assert not any(line.startswith(("tinyplay", "aplay", "stagefright")) for line in script.splitlines())
    assert "cut -d= -f1" in script


def test_binder_test_is_opt_in_and_cleans_up():
    resource = Mock()
    resource.joinpath.return_value.read_bytes.return_value = b"jar"
    with patch("stationbot.max_android_probe.probe_max_ssh"), \
         patch("stationbot.max_android_probe.importlib.resources.files", return_value=resource), \
         patch("stationbot.max_android_probe.subprocess.run", return_value=_run()) as run:
        probe_max_android(MaxSshTarget("192.168.1.5", "root"), binder_test=True)
    script = run.call_args.kwargs["input"].decode()
    assert "MaxBinder" in script and "mktemp -d" in script and "trap " in script
    assert "@PAYLOAD@" not in script and "MaxTone" not in script


def test_failures_do_not_disclose_remote_stderr_or_accept_unmarked_output():
    target = MaxSshTarget("192.168.1.5", "root")
    for result in (_run(code=1), _run(output="noise"), _run(output="MAX_ANDROID_PROBE_V1\n")):
        with patch("stationbot.max_android_probe.probe_max_ssh", Mock()), \
             patch("stationbot.max_android_probe.subprocess.run", return_value=result):
            with pytest.raises(ProvisionError) as error:
                probe_max_android(target)
        assert "private" not in str(error.value)
