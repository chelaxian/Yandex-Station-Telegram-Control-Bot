from unittest.mock import Mock, patch

import pytest

from stationbot.max_hybrid import MaxHybridTarget, MaxNonRootAdb, open_forward, verify_max_hybrid
from stationbot.max_ssh_probe import MaxSshTarget
from stationbot.provision import Adb, ProvisionError


def test_hybrid_target_requires_same_lan_host():
    target = MaxHybridTarget("192.168.1.5", MaxSshTarget("192.168.1.5", "root", 2222))
    assert target.adb_serial == "192.168.1.5:5555"
    with pytest.raises(ProvisionError):
        MaxHybridTarget("192.168.1.5", MaxSshTarget("192.168.1.6", "root", 2222))


def test_non_root_adb_accepts_only_max_shell_identity():
    target = MaxHybridTarget("192.168.1.5", MaxSshTarget("192.168.1.5", "root"))
    adb = MaxNonRootAdb("adb", target)
    adb.client = Mock(spec=Adb)
    adb.client.shell.return_value = "2000\naarch64\r\n"
    adb.verify()
    assert adb.client.connect.call_count == 1
    assert adb.client.shell.call_args.args == ("id -u; uname -m",)

    for output in ("0\naarch64", "2000\narmv7l", "2000\naarch64\nextra", "noise"):
        adb.client.shell.return_value = output
        with pytest.raises(ProvisionError):
            adb.verify()


def test_hybrid_verification_checks_adb_then_strict_ssh_without_writes():
    target = MaxHybridTarget("192.168.1.5", MaxSshTarget("192.168.1.5", "root", 2222))
    with (
        patch("stationbot.max_hybrid.MaxNonRootAdb") as adb_transport,
        patch("stationbot.max_hybrid.probe_max_ssh") as ssh_probe,
    ):
        verify_max_hybrid(target, "adb")
    adb_transport.assert_called_once_with("adb", target)
    adb_transport.return_value.verify.assert_called_once_with()
    ssh_probe.assert_called_once_with(target.ssh)
    client = adb_transport.return_value.client
    assert not any(call for call in client.method_calls if call[0] in {"push", "install", "start"})


def test_hybrid_failure_does_not_continue_to_ssh_or_forward():
    target = MaxHybridTarget("192.168.1.5", MaxSshTarget("192.168.1.5", "root"))
    with (
        patch("stationbot.max_hybrid.MaxNonRootAdb") as adb_transport,
        patch("stationbot.max_hybrid.probe_max_ssh") as ssh_probe,
    ):
        adb_transport.return_value.verify.side_effect = ProvisionError("adb identity")
        with pytest.raises(ProvisionError):
            verify_max_hybrid(target, "adb")
    ssh_probe.assert_not_called()


def test_forward_rejects_identity_failure_before_touching_adb_server(monkeypatch):
    target = MaxHybridTarget("192.168.1.5", MaxSshTarget("192.168.1.5", "root"))
    adb_class = Mock()
    monkeypatch.setattr(
        "stationbot.max_hybrid.verify_max_hybrid",
        Mock(side_effect=ProvisionError("identity failed")),
    )
    monkeypatch.setattr("stationbot.max_hybrid.Adb", adb_class)
    with pytest.raises(ProvisionError):
        open_forward(target, "adb", 18210)
    assert adb_class.call_count == 0
