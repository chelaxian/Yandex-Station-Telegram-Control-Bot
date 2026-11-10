import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path, PurePosixPath
from unittest.mock import Mock

import pytest

from stationbot import provision, supervisor
from stationbot.provision import (
    PROFILES,
    RUNTIME_COMMIT,
    RUNTIME_RELEASE,
    Adb,
    ProvisionError,
    identify,
    missing_features,
    serial_address,
    starter,
)


def test_model_qualification_never_aliases_midi_to_station2():
    assert identify('0', 'aarch64', 'Yandex Pickle EVT\0', '0.369.1.50.4795647264.20261021.107') == 'yandexmini_3_pro'
    assert identify('0', 'aarch64', 'Yandex Station Midi\0', '0.369.1.50.4794649087.20261021.295') == 'yandexstation_2'
    assert identify('0', 'aarch64', 'Yandex Plum EVT2\0', '0.369.1.50.4795647582.20261021.133') == 'yandexplum'
    # Max reports an Android platform name also used by Station 2; its board
    # identity must not authorize the Station 2 installer profile.
    with pytest.raises(ProvisionError):
        identify('0', 'aarch64', 'Amlogic', 'PPR1.180610.011.5000000921')
    for values in [
        ('0','aarch64','Yandex Station Midi','other-firmware'),
        ('1000','aarch64','Yandex Pickle EVT','.50.4795647264.'),
        ('0','armv7l','Yandex Pickle EVT','.50.4795647264.'),
        ('0','aarch64','Yandex Prune EVT2','0.369.1.50.4795647582.20261021.133'),
        ('0','aarch64','Yandex Plum EVT2','0.369.1.50.4794654278.20261021.133'),
    ]:
        with pytest.raises(ProvisionError, match='Найдено:|UID 0'):
            identify(*values)


@pytest.mark.parametrize('value', ['8.8.8.8', '0.0.0.0', '224.0.0.1', '192.168.1.2;reboot', '192.168.1.2:22', 'hostname', '::1'])
def test_device_address_cannot_be_a_shell_command_or_public_host(value):
    with pytest.raises(ProvisionError):
        serial_address(value)
    assert serial_address('192.168.1.2') == '192.168.1.2:5555'


def test_runtime_is_pinned_to_official_luna_release():
    assert RUNTIME_RELEASE == 'v0.2.23'
    assert RUNTIME_COMMIT == 'b6ddd7f4e70f985256d01343899697a076f6ce05'
    assert PROFILES['yandexmini_3_pro']['sha256'] == 'f953d7d80c64e71822839d01933ba4a97254c9d974710f911edfe9d16f01668d'
    assert PROFILES['yandexstation_2']['sha256'] == '5659c67c8d40fd0091173a186cf2ed7de4ff047cfb107c8cac932c64b13b6cdb'
    assert PROFILES['yandexplum']['sha256'] == '442028c98420d42dd9a61ff21c70f638c48644a41b524c1025afd6a753b9a5af'


def test_contract_check_reports_exact_missing_capability():
    good = {'model': 'yandexplum', 'features': ['audio.jobs.v1', 'owner.tools.v1', 'owner.speech.phase.v1']}
    bad = {'model': 'yandexplum', 'features': ['audio.jobs.v1']}
    assert missing_features(good, 'yandexplum', True) == set()
    assert missing_features(bad, 'yandexplum', True) == {'owner.tools.v1', 'owner.speech.phase.v1'}
    assert missing_features(good, 'yandexstation_2', True) == {'model'}


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


def test_forward_refresh_replaces_only_its_own_stale_mapping():
    adb = Adb('adb', '192.168.1.2')
    calls = []

    def run(args, **kwargs):
        calls.append(args)
        if args[-1] == '--list':
            return '192.168.1.2:5555 tcp:18210 tcp:18100\n'
        return ''

    adb.run = Mock(side_effect=run)
    adb.forward(18210, refresh=True)
    assert calls == [
        ['forward', '--list'],
        ['-s', '192.168.1.2:5555', 'forward', '--remove', 'tcp:18210'],
        ['-s', '192.168.1.2:5555', 'forward', '--no-rebind', 'tcp:18210', 'tcp:18100'],
    ]


def test_recover_recreates_forward_after_transport_reconnect(monkeypatch):
    class FakeAdb:
        def __init__(self, executable, serial):
            self.forwarded = None

        def connect(self):
            pass

        def probe(self):
            return 'yandexplum'

        def start(self):
            pass

        def forward(self, port, *, refresh=False):
            self.forwarded = (port, refresh)

        def promote_qualified(self):
            pass

    fake = FakeAdb('adb', '192.168.1.2')
    monkeypatch.setattr(supervisor, 'Adb', lambda executable, serial: fake)
    device_json = Mock(side_effect=[OSError('stale tunnel'), {
        'model': 'yandexplum',
        'features': ['audio.jobs.v1', 'owner.tools.v1', 'owner.speech.phase.v1'],
    }])
    monkeypatch.setattr(supervisor, 'device_json', device_json)
    supervisor.recover({'serial': '192.168.1.2:5555', 'model': 'yandexplum', 'port': 18210}, 'adb')
    assert fake.forwarded == (18210, True)


def test_recover_rolls_back_update_that_loses_owner_contract(monkeypatch):
    class FakeAdb:
        def __init__(self, executable, serial):
            self.restored = None

        def restore_qualified(self, port, model, owner_tools=True):
            self.restored = (port, model, owner_tools)
            return {'model': model, 'features': ['audio.jobs.v1', 'owner.tools.v1', 'owner.speech.phase.v1']}

        def promote_qualified(self):
            pass

    fake = FakeAdb('adb', '192.168.1.2')
    monkeypatch.setattr(supervisor, 'Adb', lambda executable, serial: fake)
    monkeypatch.setattr(
        supervisor,
        'device_json',
        Mock(return_value={'model': 'yandexplum', 'features': ['audio.jobs.v1']}),
    )
    station = {'id': 'station_1', 'serial': '192.168.1.2:5555', 'model': 'yandexplum', 'port': 18210, 'owner_tools': True}
    supervisor.recover(station, 'adb')
    assert fake.restored == (18210, 'yandexplum', True)


def test_recover_reports_forward_that_still_does_not_reach_luna(monkeypatch):
    class FakeAdb:
        def __init__(self, executable, serial):
            pass

        def connect(self): pass
        def probe(self): return 'yandexplum'
        def start(self): pass
        def forward(self, port, *, refresh=False): pass

        def restore_qualified(self, port, model, owner_tools=True):
            raise ProvisionError('qualified runtime unavailable')

    monkeypatch.setattr(supervisor, 'Adb', FakeAdb)
    monkeypatch.setattr(supervisor, 'device_json', Mock(side_effect=OSError('forward still dead')))
    monkeypatch.setattr(supervisor.time, 'sleep', lambda seconds: None)
    with pytest.raises(ProvisionError, match='qualified runtime unavailable'):
        supervisor.recover({'serial': '192.168.1.2:5555', 'model': 'yandexplum', 'port': 18210}, 'adb')


def test_adb_failure_reports_the_last_tool_diagnostic(monkeypatch):
    completed = subprocess.CompletedProcess(["adb"], 1, "", "error: device unauthorized")
    monkeypatch.setattr(provision.subprocess, "run", Mock(return_value=completed))
    adb = Adb("adb", "192.168.1.2")
    with pytest.raises(ProvisionError, match="device unauthorized"):
        adb.run(["get-state"])


def test_adb_shell_protocol_avoids_backslash_escapes(monkeypatch):
    adb = Adb("adb", "192.168.1.2")
    output = chr(10).join(["__STATIONBOT_RESULT__", "value", "", "__STATIONBOT_EXIT__0", ""])
    monkeypatch.setattr(
        provision.subprocess,
        "run",
        Mock(return_value=subprocess.CompletedProcess(["adb"], 0, output, "")),
    )
    assert adb.shell("id -u") == "value"
    command = provision.subprocess.run.call_args.args[0]
    assert "echo __STATIONBOT_RESULT__" in command[-1]
    assert "echo __STATIONBOT_EXIT__$rc" in command[-1]
    assert "printf" not in command[-1]


def test_adb_shell_protocol_accepts_output_without_trailing_newline(monkeypatch):
    adb = Adb("adb", "192.168.1.2")
    output = "__STATIONBOT_RESULT__" + chr(10) + "firmware-value__STATIONBOT_EXIT__0"
    monkeypatch.setattr(
        provision.subprocess,
        "run",
        Mock(return_value=subprocess.CompletedProcess(["adb"], 0, output, "")),
    )
    assert adb.shell("cat firmware") == "firmware-value"


def test_install_previous_binary_uses_hard_link_without_second_copy(monkeypatch, tmp_path):
    adb = Adb("adb", "192.168.1.2")
    commands = []
    adb.probe = Mock(return_value="yandexplum")
    adb.shell = Mock(side_effect=lambda command: commands.append(command) or "")
    adb.run = Mock()
    adb.stop = Mock()
    adb.start = Mock()
    adb.forward = Mock()
    binary = tmp_path / "luna-yandexplum"
    binary.write_bytes(b"qualified")
    good = {"model": "yandexplum", "features": ["audio.jobs.v1", "owner.tools.v1", "owner.speech.phase.v1"]}
    expected = provision.hashlib.sha256(b"qualified").hexdigest()
    monkeypatch.setitem(PROFILES, "yandexplum", {**PROFILES["yandexplum"], "sha256": expected})
    monkeypatch.setattr(provision, "device_json", Mock(return_value=good))
    monkeypatch.setattr(provision, "apply_update_policy", Mock())

    assert adb.install(tmp_path, 18210)["model"] == "yandexplum"

    joined = "\n".join(commands)
    assert "ln -f /data/local/stationbot-luna/luna /data/local/stationbot-luna/luna.previous" in joined
    assert "cp -p /data/local/stationbot-luna/luna /data/local/stationbot-luna/luna.previous" not in joined


def test_qualified_rollback_uses_hard_link_without_copy(monkeypatch):
    adb = Adb("adb", "192.168.1.2")
    commands = []
    adb.shell = Mock(side_effect=lambda command: commands.append(command) or "")
    adb.stop = Mock()
    adb.start = Mock()
    adb.forward = Mock()
    good = {'model': 'yandexplum', 'features': ['audio.jobs.v1', 'owner.tools.v1', 'owner.speech.phase.v1']}
    monkeypatch.setattr(provision, "device_json", Mock(return_value=good))
    monkeypatch.setattr(provision, "suspend_updates", Mock())
    assert adb.restore_qualified(18210, "yandexplum", True) == good
    joined = "\n".join(commands)
    assert "ln /data/local/stationbot-luna/luna.qualified /data/local/stationbot-luna/luna" in joined
    assert "cp /data/local/stationbot-luna/luna.qualified" not in joined


def test_probe_with_adapter_noise_reports_unqualified_profile_not_opaque_failure():
    adb = Adb("adb", "192.168.1.2")
    adb.connect = Mock()
    adb.shell = Mock(return_value="adapter banner\r\n0\r\naarch64\r\nYandex Pickle EVT2\r\n0.369.1.50.4795647582.20261021.133\r\n")
    with pytest.raises(ProvisionError, match="Yandex Pickle EVT2.*4795647582"):
        adb.probe()


def test_probe_with_adapter_noise_identifies_experimental_plum():
    adb = Adb("adb", "192.168.1.2")
    adb.connect = Mock()
    adb.shell = Mock(return_value="adb adapter ready\r\n0\r\naarch64\r\nYandex Plum EVT2\0\r\n0.369.1.50.4795647582.20261021.133\r\n")
    assert adb.probe() == "yandexplum"


def test_probe_rejects_ambiguous_identification():
    adb = Adb("adb", "192.168.1.2")
    adb.connect = Mock()
    adb.shell = Mock(return_value="0\naarch64\nYandex Plum EVT2\nYandex Prune EVT2\n0.369.1.50.4795647582.20261021.133\n")
    with pytest.raises(ProvisionError, match="однозначно"):
        adb.probe()


def test_start_script_is_local_and_only_stops_its_own_binary():
    script = starter(True, PROFILES["yandexplum"])
    assert '--listen 127.0.0.1:18100' in script and 'flock -n 9' in script
    assert 'LUNA_ENABLE_OWNER_TOOLS=1' in script
    assert 'LUNA_AUDIO_PCM=plug:dmix_spk' in script
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


def test_windows_startup_is_visible_and_survives_supervisor_restarts(tmp_path, monkeypatch):
    bootstrap = bootstrap_module()
    commands = []
    monkeypatch.setattr(bootstrap, 'run', lambda command, **kwargs: commands.append(command))
    bootstrap.windows_task(tmp_path, tmp_path / 'python.exe', start=True)
    registration = (tmp_path / 'register-task.ps1').read_text(encoding='utf-8-sig')
    assert 'Start-ScheduledTask -TaskName YandexStationTelegramControlBot' in registration
    assert 'Stop-ScheduledTask -TaskName YandexStationTelegramControlBot' in registration
    assert '$stopDeadline = (Get-Date).AddSeconds(10)' in registration
    assert '$startDeadline = (Get-Date).AddSeconds(15)' in registration
    assert 'Start-Sleep -Seconds 18' in registration
    assert '$serviceLog =' in registration
    assert registration.count('Get-Content $serviceLog -Tail 30') == 2
    assert registration.count("$serviceState -ne 'Running'") == 2
    assert commands and commands[0][0] == 'powershell.exe'


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows PowerShell integration')
def test_windows_runner_survives_normal_stderr_logging(tmp_path, monkeypatch):
    bootstrap = bootstrap_module()
    monkeypatch.setattr(bootstrap, 'run', lambda *args, **kwargs: None)
    bootstrap.windows_task(tmp_path, Path(sys.executable), start=False)
    runner = tmp_path / 'run.ps1'
    text = runner.read_text(encoding='utf-8-sig')
    begin = text.index(' -m stationbot.supervisor --root ')
    end = text.index(' >> ', begin)
    text = text[:begin] + ' -c "import sys; print(123, file=sys.stderr); sys.exit(0)"' + text[end:]
    runner.write_text(text, encoding='utf-8-sig')
    result = subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-File', str(runner)],
                            capture_output=True, timeout=15)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert '123' in (tmp_path / 'service.log').read_text(encoding='utf-16')


def test_windows_update_stops_only_managed_stationbot_processes(tmp_path, monkeypatch):
    bootstrap = bootstrap_module()
    commands = []
    monkeypatch.setattr(bootstrap, 'run', lambda command, **kwargs: commands.append(command))
    bootstrap.stop_managed_windows(tmp_path)
    script = (tmp_path / 'stop-managed.ps1').read_text(encoding='utf-8-sig')
    assert "CommandLine.Contains('-m stationbot')" in script
    assert 'ExecutablePath.StartsWith($releasePrefix' in script
    assert 'Stop-Process -Id $_.ProcessId -Force' in script
    assert commands and commands[0][0] == 'powershell.exe'
