from types import SimpleNamespace
from unittest.mock import patch

import pytest

from stationbot.max_ssh_probe import MaxSshTarget
from stationbot.max_volume_probe import probe_max_volume
from stationbot.provision import ProvisionError

TARGET = MaxSshTarget("192.168.1.5", "root")


def _ok():
    return SimpleNamespace(returncode=0, stdout=b"MAX_VOLUME_PROBE_V1\n--- x\nvolume is 15\n", stderr=b"private")


def test_default_probe_reads_only_and_sends_unix_newlines():
    with patch("stationbot.max_volume_probe.probe_max_ssh"), \
         patch("stationbot.max_volume_probe.subprocess.run", return_value=_ok()) as run:
        assert "volume is 15" in probe_max_volume(TARGET)
    script = run.call_args.kwargs["input"]
    assert b"\r" not in script and b"--set" not in script and b"--get" in script
    assert b"rm -rf" in script and run.call_args.args[0][-1] == "sh -s"


def test_round_trip_restores_even_on_early_exit_and_validates_indexes():
    with patch("stationbot.max_volume_probe.probe_max_ssh"), \
         patch("stationbot.max_volume_probe.subprocess.run", return_value=_ok()) as run:
        probe_max_volume(TARGET, test_index=10, restore_index=15)
    script = run.call_args.kwargs["input"].decode()
    assert "--set 10" in script and "--set 15" in script and "trap 'restore; rm -rf" in script
    assert "@TEST@" not in script and "@RESTORE@" not in script
    for bad in ((10, None), (None, 15), (101, 15), (-1, 15), (True, 15)):
        with pytest.raises(ProvisionError):
            probe_max_volume(TARGET, test_index=bad[0], restore_index=bad[1])


def test_failures_do_not_disclose_stderr_or_accept_unmarked_output():
    for result in (SimpleNamespace(returncode=1, stdout=b"", stderr=b"private"),
                   SimpleNamespace(returncode=0, stdout=b"noise", stderr=b"private")):
        with patch("stationbot.max_volume_probe.probe_max_ssh"), \
             patch("stationbot.max_volume_probe.subprocess.run", return_value=result):
            with pytest.raises(ProvisionError) as error:
                probe_max_volume(TARGET)
        assert "private" not in str(error.value)
