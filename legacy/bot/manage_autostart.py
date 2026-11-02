#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cross-Platform Autostart Manager (Windows & Linux)
Supports Windows Startup folder (VBS) and Linux XDG Autostart (.desktop).
"""

import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_NAME = "Yandex_Station_Control_Bot"
SCRIPT_FILE = "bot.py"
SCRIPT_PATH = os.path.join(BASE_DIR, SCRIPT_FILE)

# Windows paths
STARTUP_DIR_WIN = os.path.join(os.environ.get("APPDATA", ""), r"Microsoft\Windows\Start Menu\Programs\Startup")
VBS_PATH = os.path.join(STARTUP_DIR_WIN, f"{APP_NAME}.vbs")

# Linux paths
AUTOSTART_DIR_LINUX = os.path.expanduser("~/.config/autostart")
DESKTOP_PATH = os.path.join(AUTOSTART_DIR_LINUX, f"{APP_NAME}.desktop")

def is_enabled():
    if sys.platform == "win32":
        return os.path.exists(VBS_PATH)
    else:
        return os.path.exists(DESKTOP_PATH)

def enable():
    if sys.platform == "win32":
        pyw_exe = sys.executable.replace("python.exe", "pythonw.exe")
        if not os.path.exists(pyw_exe):
            pyw_exe = sys.executable
        vbs_content = (
            f'Set WshShell = CreateObject("WScript.Shell")\n'
            f'WshShell.CurrentDirectory = "{BASE_DIR}"\n'
            f'WshShell.Run """{pyw_exe}"" """{SCRIPT_PATH}""", 0, False\n'
        )
        try:
            with open(VBS_PATH, "w", encoding="ascii", errors="ignore") as f:
                f.write(vbs_content)
            print(f"[OK] Autostart ENABLED for Windows! Shortcut placed in Startup folder.")
        except Exception as e:
            print(f"[ERROR] Could not enable Windows autostart: {e}")
    else:
        os.makedirs(AUTOSTART_DIR_LINUX, exist_ok=True)
        venv_py = os.path.abspath(os.path.join(BASE_DIR, "..", ".venv", "bin", "python3"))
        exec_py = venv_py if os.path.exists(venv_py) else sys.executable
        desktop_content = f"""[Desktop Entry]
Type=Application
Version=1.0
Name={APP_NAME}
Comment=Auto-launch {APP_NAME} silently on login
Path={BASE_DIR}
Exec={exec_py} {SCRIPT_PATH}
Terminal=false
Hidden=false
X-GNOME-Autostart-enabled=true
"""
        try:
            with open(DESKTOP_PATH, "w", encoding="utf-8") as f:
                f.write(desktop_content)
            os.chmod(DESKTOP_PATH, 0o755)
            print(f"[OK] Autostart ENABLED for Linux! Desktop file created at {DESKTOP_PATH}.")
        except Exception as e:
            print(f"[ERROR] Could not enable Linux autostart: {e}")

def disable():
    removed = False
    if sys.platform == "win32" and os.path.exists(VBS_PATH):
        os.remove(VBS_PATH)
        removed = True
    elif os.path.exists(DESKTOP_PATH):
        os.remove(DESKTOP_PATH)
        removed = True
        
    if removed:
        print("[OK] Autostart successfully DISABLED.")
    else:
        print("Autostart was not enabled.")

def main():
    print("=" * 60)
    print(f"    AUTOSTART MANAGER: {APP_NAME} (Platform: {sys.platform})")
    print("=" * 60)
    print(f"Status: {'[ENABLED]' if is_enabled() else '[DISABLED]'}")
    print("-" * 60)
    print("1. Enable autostart on system boot/login")
    print("2. Disable autostart")
    print("3. Exit")
    print("-" * 60)
    choice = input("Enter option [1-3]: ").strip()
    if choice == "1":
        enable()
    elif choice == "2":
        disable()
    else:
        print("Exiting.")

if __name__ == "__main__":
    main()
