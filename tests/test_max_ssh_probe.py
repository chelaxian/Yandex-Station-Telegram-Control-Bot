from types import SimpleNamespace
from unittest.mock import patch

import pytest

from stationbot.max_ssh_probe import MaxSshTarget, probe_max_ssh
from stationbot.provision import ProvisionError


def test_root_geometry_probe_is_read_only_and_uses_strict_host_checking():
    lines = ["MAX_PROBE_V1", "0", "aarch64", "YNDX LED screen", "25,16", "24", "75", "YNDX LED ring", "24,1", "24", "72"]
    with patch("stationbot.max_ssh_probe.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="\n".join(lines))) as run:
        assert probe_max_ssh(MaxSshTarget("192.168.1.5", "root", 2222))
    args = run.call_args.args[0]
    assert "StrictHostKeyChecking=yes" in args and "BatchMode=yes" in args
    assert all(word not in args[-1] for word in ("chmod", "mkdir", "rm ", "reboot"))


@pytest.mark.parametrize("output", ["MAX_PROBE_V1\n2000\naarch64", "MAX_PROBE_V1\n0\naarch64", "noise"])
def test_unknown_identity_fails_closed(output):
    with patch("stationbot.max_ssh_probe.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout=output)):
        with pytest.raises(ProvisionError):
            probe_max_ssh(MaxSshTarget("192.168.1.5", "root"))


def test_ssh_failure_does_not_disclose_remote_output():
    result = SimpleNamespace(returncode=255, stdout="", stderr="sensitive host details")
    with patch("stationbot.max_ssh_probe.subprocess.run", return_value=result):
        with pytest.raises(ProvisionError) as error:
            probe_max_ssh(MaxSshTarget("192.168.1.5", "root"))
    assert "sensitive" not in str(error.value)


def test_max_probe_requires_screen_and_ring_signature():
    lines = ["MAX_PROBE_V1", "0", "aarch64", "YNDX LED screen", "25,16", "24", "75", "YNDX LED ring", "24,1", "24", "72"]
    for index in range(1, len(lines)):
        changed = lines.copy()
        changed[index] = "wrong"
        with patch("stationbot.max_ssh_probe.subprocess.run", return_value=SimpleNamespace(returncode=0, stdout="\n".join(changed))):
            with pytest.raises(ProvisionError):
                probe_max_ssh(MaxSshTarget("192.168.1.5", "root"))


@pytest.mark.parametrize("host,user,port", [("-oProxyCommand=x", "root", 22), ("127.0.0.1", "root;id", 22), ("127.0.0.1", "root", 0)])
def test_rejects_unsafe_target(host, user, port):
    with pytest.raises(ProvisionError):
        MaxSshTarget(host, user, port)
