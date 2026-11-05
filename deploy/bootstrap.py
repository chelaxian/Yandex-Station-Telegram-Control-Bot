"""Standard-library host bootstrap for the verified release bundle."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path


def verify_bundle(bundle):
    manifest = json.loads((bundle / "bundle.json").read_text(encoding="utf-8"))
    if manifest.get("wheel") not in manifest["files"] or not manifest["wheel"].endswith(".whl"):
        raise RuntimeError("Wheel is not covered by the manifest")
    if Path(manifest["version"]).name != manifest["version"] or any(c in manifest["version"] for c in "/\\\r\n"):
        raise RuntimeError("Invalid release version")
    for name, expected in manifest["files"].items():
        if Path(name).is_absolute() or ".." in Path(name).parts:
            raise RuntimeError("Invalid bundle file name")
        file = (bundle / name).resolve()
        if not file.is_relative_to(bundle.resolve()) or not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != expected:
            raise RuntimeError("Release bundle checksum mismatch")
    return manifest


def run(command, **kwargs):
    result = subprocess.run(command, **kwargs)
    if result.returncode:
        raise RuntimeError("Installation command failed; previous release retained")


def system_unit(root, python):
    def quote(path):
        return '"' + str(path).replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'
    if any(c in str(root) + str(python) for c in "\r\n"):
        raise ValueError("Invalid service path")
    return f"""[Unit]
Description=Yandex Station Telegram Control Bot (one-click)
After=network-online.target
Wants=network-online.target
StartLimitIntervalSec=120
StartLimitBurst=3
[Service]
Type=simple
User=stationbot
Group=stationbot
Environment=HOME={quote(root)}
WorkingDirectory={quote(root)}
ExecStart={quote(python)} -m stationbot.supervisor --root {quote(root)}
Restart=on-failure
RestartSec=10
TimeoutStopSec=25
KillMode=mixed
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths={quote(root)}
[Install]
WantedBy=multi-user.target
"""


def windows_task(root, python, start):
    # Paths are literals in generated PowerShell, not shell-concatenated commands.
    def ps(value):
        return "'" + str(value).replace("'", "''") + "'"
    runner = root / "run.ps1"
    runner.write_text(f"$ErrorActionPreference='Stop'\n& {ps(python)} -m stationbot.supervisor --root {ps(root)} >> {ps(root/'service.log')} 2>&1\nexit $LASTEXITCODE\n", encoding="utf-8-sig")
    registration = root / "register-task.ps1"
    arguments = '-NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + str(runner) + '"'
    startup_check = (
        "Start-Sleep -Seconds 6\n"
        "$serviceState = (Get-ScheduledTask -TaskName YandexStationTelegramControlBot).State.ToString()\n"
        "if ($serviceState -ne 'Running') { throw 'Служба бота не запустилась; откройте service.log' }\n"
        "Start-Sleep -Seconds 12\n"
        "$serviceState = (Get-ScheduledTask -TaskName YandexStationTelegramControlBot).State.ToString()\n"
        "if ($serviceState -ne 'Running') { throw 'Служба бота остановилась; откройте service.log' }"
    ) if start else ""
    registration.write_text(f"""$ErrorActionPreference='Stop'
$action=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument {ps(arguments)}
$trigger=New-ScheduledTaskTrigger -AtLogOn -User ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)
$principal=New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
$settings=New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew -StartWhenAvailable
Register-ScheduledTask -TaskName 'YandexStationTelegramControlBot' -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
{'Start-ScheduledTask -TaskName YandexStationTelegramControlBot' if start else ''}
{startup_check}
""", encoding="utf-8-sig")
    run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(registration)])


def restrict_windows(root):
    import csv
    identity = subprocess.check_output(["whoami", "/user", "/fo", "csv", "/nh"], text=True)
    sid = next(csv.reader([identity.strip()]))[1]
    run(["icacls", str(root), "/inheritance:r", "/grant:r", f"*{sid}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F"], stdout=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--answers", type=Path)
    parser.add_argument("--no-service", action="store_true")
    parser.add_argument("--no-start", action="store_true")
    parser.add_argument("--prepare-only", action="store_true", help="Stage host only; no station changes or poller")
    parser.add_argument("--check", action="store_true", help="Verify the release and dependencies without installing")
    parser.add_argument("--register-system-service", action="store_true")
    args = parser.parse_args()
    root, bundle = args.root.resolve(), args.bundle.resolve()
    if args.register_system_service:
        if os.name == "nt" or os.geteuid() != 0:
            raise RuntimeError("System registration requires Linux root")
        plan = json.loads((root / "launch.json").read_text())
        python = Path(plan["python"]).resolve()
        if not python.is_relative_to(root / "releases"):
            raise RuntimeError("Invalid managed Python path")
        unit = Path('/etc/systemd/system/stationbot-oneclick.service')
        if unit.exists() and "(one-click)" not in unit.read_text():
            raise RuntimeError("Existing unrelated service retained")
        old_unit = unit.read_text() if unit.exists() else None
        try:
            unit.write_text(system_unit(root, python))
            run(["systemctl", "daemon-reload"])
            run(["systemctl", "enable", "stationbot-oneclick.service"])
            if not args.no_start:
                run(["systemctl", "restart", "stationbot-oneclick.service"])
                time.sleep(3)
                run(["systemctl", "is-active", "--quiet", "stationbot-oneclick.service"])
        except Exception:
            if old_unit:
                unit.write_text(old_unit)
                run(["systemctl", "daemon-reload"])
                run(["systemctl", "restart", "stationbot-oneclick.service"])
            else:
                subprocess.run(["systemctl", "disable", "--now", "stationbot-oneclick.service"], capture_output=True)
                unit.unlink(missing_ok=True)
                run(["systemctl", "daemon-reload"])
            raise
        return
    manifest = verify_bundle(bundle)
    if not (3, 10) <= sys.version_info[:2] < (3, 14):
        raise RuntimeError("Python 3.10–3.13 required")
    for executable in ["adb", "ffmpeg", "espeak-ng"]:
        if not shutil.which(executable):
            raise RuntimeError(f"Missing dependency: {executable}")
    if args.check:
        print("Release SHA-256 and host dependencies verified; no changes")
        return
    if root.exists() and any(root.iterdir()) and not (root / "managed-v1").is_file():
        raise RuntimeError("Install directory is not managed; existing files retained")
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    if os.name == "nt":
        restrict_windows(root)
    else:
        root.chmod(0o700)
    (root / "managed-v1").touch(mode=0o600)
    wheel = bundle / manifest["wheel"]
    digest = hashlib.sha256(wheel.read_bytes()).hexdigest()[:12]
    release = root / "releases" / (manifest["version"] + "-" + digest)
    python = release / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if not (release / "ready").exists():
        run([sys.executable, "-m", "venv", str(release)])
        with (root / "install.log").open("w", encoding="utf-8") as output:
            run([str(python), "-m", "pip", "install", "--disable-pip-version-check", "-c", str(bundle / "requirements.lock.txt"), str(wheel)], stdout=output, stderr=subprocess.STDOUT)
        (release / "ready").touch()
    if args.prepare_only:
        print("Host venv prepared; stations/configuration/services unchanged")
        return
    backups = root / "backups" / time.strftime("%Y%m%dT%H%M%S")
    backups.mkdir(parents=True)
    for name in ["config.toml", "secrets.env", "installation.json", "launch.json", "run.ps1"]:
        if (root / name).exists():
            shutil.copy2(root / name, backups / name)
    command = [str(python), "-m", "stationbot.setup", "--root", str(root), "--bundle", str(bundle)]
    if args.answers:
        command += ["--answers", str(args.answers.resolve())]
    user_unit = Path.home() / ".config/systemd/user/stationbot-oneclick.service"
    old_user_unit = user_unit.read_text() if os.name != "nt" and user_unit.exists() else None
    old_task = None
    if os.name == "nt" and not args.no_service:
        task = subprocess.run(["schtasks", "/Query", "/TN", "YandexStationTelegramControlBot", "/XML"], capture_output=True, text=True)
        if task.returncode == 0:
            if not (backups / "launch.json").exists():
                raise RuntimeError("Existing unmanaged scheduled task retained")
            old_task = task.stdout
    try:
        run(command)
        run([str(python), "-m", "stationbot.supervisor", "--root", str(root), "--check"])
        launch = root / "launch.json"
        launch.write_text(json.dumps({"python": str(python), "version": manifest["version"], "sha256": hashlib.sha256(wheel.read_bytes()).hexdigest()}))
        if not args.no_service:
            if os.name == "nt":
                subprocess.run(["schtasks", "/End", "/TN", "YandexStationTelegramControlBot"], capture_output=True)
                windows_task(root, python, not args.no_start)
            else:
                unit = user_unit
                unit.parent.mkdir(parents=True, exist_ok=True)
                if unit.exists() and "(one-click)" not in unit.read_text():
                    raise RuntimeError("Existing unrelated service retained")
                content = system_unit(root, python).replace("User=stationbot\nGroup=stationbot\n", "").replace("WantedBy=multi-user.target", "WantedBy=default.target")
                content = "\n".join(line for line in content.splitlines() if not line.startswith(("ProtectSystem=", "ProtectHome=", "ReadWritePaths=", "Environment=HOME="))) + "\n"
                unit.write_text(content)
                run(["systemctl", "--user", "daemon-reload"])
                run(["systemctl", "--user", "enable", "stationbot-oneclick.service"])
                if not args.no_start:
                    run(["systemctl", "--user", "restart", "stationbot-oneclick.service"])
                    time.sleep(3)
                    run(["systemctl", "--user", "is-active", "--quiet", "stationbot-oneclick.service"])
        print("Установка завершена. Служба бота запущена; ПК/сервер должен оставаться включённым.")
        print(f"Журнал службы: {root / 'service.log'}")
        print("Откройте чат с ботом и отправьте /menu.")
    except Exception:
        for original in backups.iterdir():
            shutil.copy2(original, root / original.name)
        if not args.no_service:
            if os.name == "nt" and old_task:
                xml = root / "previous-task.xml"
                xml.write_text(old_task, encoding="utf-16")
                subprocess.run(["schtasks", "/Create", "/TN", "YandexStationTelegramControlBot", "/XML", str(xml), "/F"], capture_output=True)
                subprocess.run(["schtasks", "/Run", "/TN", "YandexStationTelegramControlBot"], capture_output=True)
            elif os.name != "nt":
                if old_user_unit:
                    user_unit.write_text(old_user_unit)
                elif user_unit.exists() and "(one-click)" in user_unit.read_text():
                    subprocess.run(["systemctl", "--user", "disable", "--now", "stationbot-oneclick.service"], capture_output=True)
                    user_unit.unlink()
                subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
                if old_user_unit:
                    subprocess.run(["systemctl", "--user", "restart", "stationbot-oneclick.service"], capture_output=True)
        raise


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"Установка остановлена: {type(error).__name__}: {error}", file=sys.stderr)
        raise SystemExit(1) from None
