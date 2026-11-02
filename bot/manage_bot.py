#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Background Service Manager for Yandex Station Telegram Control Bot
Start, Stop, and Check Status of the bot daemon.
"""

import os
import sys
import psutil
import subprocess
import time

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPT_PATH = os.path.join(BASE_DIR, "bot.py")

def get_running_pids():
    pids = []
    my_pid = os.getpid()
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        if p.info['pid'] == my_pid:
            continue
        cmd = ' '.join(p.info['cmdline'] or []).lower()
        if 'manage_bot.py' in cmd or 'builder_bot.py' in cmd:
            continue
        if 'bot.py' in cmd and any(x in (p.info['name'] or '').lower() for x in ['python', 'py']):
            pids.append(p.info['pid'])
    return pids

def status():
    pids = get_running_pids()
    if pids:
        print(f"🟢 Bot Status: RUNNING (PID: {', '.join(map(str, pids))})")
    else:
        print("🔴 Bot Status: STOPPED")

def start():
    pids = get_running_pids()
    if pids:
        print(f"⚠️ Bot is already running! (PID: {', '.join(map(str, pids))})")
        return
    try:
        if sys.platform == "win32":
            pyw_exe = sys.executable.replace("python.exe", "pythonw.exe")
            if not os.path.exists(pyw_exe):
                pyw_exe = sys.executable
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)
            subprocess.Popen(
                [pyw_exe, SCRIPT_PATH],
                cwd=BASE_DIR,
                startupinfo=startupinfo,
                creationflags=flags,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            subprocess.Popen(
                [sys.executable, SCRIPT_PATH],
                cwd=BASE_DIR,
                start_new_session=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        time.sleep(1.5)
        pids = get_running_pids()
        if pids:
            print(f"✅ Бот успешно запущен в фоновом режиме (PID: {', '.join(map(str, pids))}).")
        else:
            print("✅ Бот запущен в фоновом режиме (скрыто, 0 окон).")
        print("Откройте Telegram и отправьте команду /start вашему боту!")
    except Exception as e:
        print(f"❌ Failed to start bot: {e}")

def stop():
    pids = get_running_pids()
    if not pids:
        print("Bot is not running.")
        return
    for pid in pids:
        try:
            psutil.Process(pid).kill()
            print(f"Stopped bot process PID {pid}")
        except Exception:
            pass
    print("✅ Bot successfully stopped.")

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd == "start":
            start()
        elif cmd == "stop":
            stop()
        elif cmd == "status":
            status()
        elif cmd == "restart":
            stop()
            time.sleep(1)
            start()
        return

    print("=" * 55)
    print("    TELEGRAM CONTROL BOT SERVICE MANAGER")
    print("=" * 55)
    status()
    print("-" * 55)
    print("1. Start Bot in background")
    print("2. Stop Bot")
    print("3. Check Status")
    print("4. Exit")
    choice = input("\nSelect an option [1-4]: ").strip()
    if choice == "1":
        start()
    elif choice == "2":
        stop()
    elif choice == "3":
        status()
    elif choice == "4":
        return
    else:
        print("Invalid choice.")
    input("\nPress Enter to exit...")

if __name__ == "__main__":
    main()
