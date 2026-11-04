import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path, PurePosixPath
from unittest.mock import Mock

import pytest

from stationbot import provision
from stationbot.provision import Adb, ProvisionError, identify, serial_address, starter


def test_model_qualification_never_aliases_midi_to_station2():
    assert identify('0', 'aarch64', 'Yandex Pickle EVT\0', '0.369.1.50.4795647264.20261021.107') == 'yandexmini_3_pro'
    assert identify('0', 'aarch64', 'Yandex Station Midi\0', '0.369.1.50.4794649087.20261021.295') == 'yandexstation_2'
    for values in [('0','aarch64','Yandex Station Midi','other-firmware'), ('1000','aarch64','Yandex Pickle EVT','.50.4795647264.'), ('0','armv7l','Yandex Pickle EVT','.50.4795647264.')]:
        with pytest.raises(ProvisionError, match='Найдено:|UID 0'):
            identify(*values)


@pytest.mark.parametrize('value', ['8.8.8.8', '0.0.0.0', '224.0.0.1', '192.168.1.2;reboot', '192.168.1.2:22', 'hostname', '::1'])
def test_device_address_cannot_be_a_shell_command_or_public_host(value):
    with pytest.raises(ProvisionError):
        serial_address(value)
    assert serial_address('192.168.1.2') == '192.168.1.2:5555'


def test_unqualified_probe_and_bad_binary_perform_no_remote_write(tmp_path):
    adb = Adb('adb', '192.168.1.2')
    adb.connect = Mock()
    adb.shell = Mock(return_value='0\naarch64\nYandex Station Midi\0\nunknown')
    adb.run = Mock()
    with pytest.raises(ProvisionError):
        adb.install(tmp_path, 18210)
    adb.run.assert_not_called()
    assert len(adb.shell.call_args_list) == 1
    adb.probe = Mock(return_value='yandexmini_3_pro')
    adb.shell.reset_mock()
    with pytest.raises(ProvisionError, match='SHA-256'):
        adb.install(tmp_path, 18210)
    adb.shell.assert_not_called()


def test_forward_does_not_overwrite_another_devices_mapping():
    adb = Adb('adb', '192.168.1.2')
    adb.run = Mock(return_value='192.168.1.3:5555 tcp:18210 tcp:8100\n')
    with pytest.raises(ProvisionError, match='занят'):
        adb.forward(18210)
    assert adb.run.call_count == 1
    adb.run = Mock(return_value='192.168.1.2:5555 tcp:18210 tcp:18100\n')
    adb.forward(18210)
    assert adb.run.call_count == 1


def test_adb_failure_reports_the_last_tool_diagnostic(monkeypatch):
    completed = subprocess.CompletedProcess(["adb"], 1, "", "error: device unauthorized")
    monkeypatch.setattr(provision.subprocess, "run", Mock(return_value=completed))
    adb = Adb("adb", "192.168.1.2")
    with pytest.raises(ProvisionError, match="device unauthorized"):
        adb.run(["get-state"])


def test_start_script_is_local_and_only_stops_its_own_binary():
    script = starter(True)
    assert '--listen 127.0.0.1:18100' in script and 'flock -n 9' in script
    assert 'LUNA_ENABLE_OWNER_TOOLS=1' in script
    assert not any(word in script for word in ['reboot', 'remount', 'killall', 'pkill', '/etc/init.d'])
    adb = Adb('adb', '192.168.1.2')
    adb.shell = Mock()
    adb.stop()
    assert 'readlink /proc/$p/exe' in adb.shell.call_args.args[0] and '/data/local/stationbot-luna/luna' in adb.shell.call_args.args[0]


def bootstrap_module():
    path = Path(__file__).resolve().parents[1] / 'deploy/bootstrap.py'
    spec = importlib.util.spec_from_file_location('bootstrap_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_bundle_integrity_and_path_escape(tmp_path):
    bootstrap = bootstrap_module()
    payload = tmp_path / 'wheel.whl'
    payload.write_bytes(b'wheel bytes')
    manifest = {'version': '3.0.0b2', 'wheel': 'wheel.whl', 'files': {'wheel.whl': hashlib.sha256(payload.read_bytes()).hexdigest()}}
    (tmp_path / 'bundle.json').write_text(json.dumps(manifest))
    bootstrap.verify_bundle(tmp_path)
    payload.write_bytes(b'corrupted')
    with pytest.raises(RuntimeError):
        bootstrap.verify_bundle(tmp_path)
    manifest['files'] = {'wheel.whl': hashlib.sha256(payload.read_bytes()).hexdigest(), '../outside': 'a' * 64}
    (tmp_path / 'bundle.json').write_text(json.dumps(manifest))
    with pytest.raises(RuntimeError, match='Invalid bundle file name'):
        bootstrap.verify_bundle(tmp_path)


def test_system_service_quotes_paths_and_uses_unprivileged_account():
    text = bootstrap_module().system_unit(PurePosixPath('/opt/my bot'), PurePosixPath('/opt/my bot/releases/venv/bin/python'))
    assert 'User=stationbot' in text and 'KillMode=mixed' in text
    assert 'ExecStart="/opt/my bot/releases/venv/bin/python"' in text
    with pytest.raises(ValueError):
        bootstrap_module().system_unit(Path('/tmp/injected\nExecStart=bad'), Path('/bin/python'))
