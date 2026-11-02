#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PC Keyboard Soundpad for Yandex Station Mini 3
Press Numpad keys on your PC to trigger instant meme sounds on the speaker and your PC mic!
"""

import os
import sys
import time
import subprocess
import keyboard

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ADB_PATH = os.path.join(BASE_DIR, "..", "tools_adb", "adb.exe")
if not os.path.exists(ADB_PATH):
    ADB_PATH = r"C:\platform-tools\adb.exe"

TARGET = "192.168.0.100:5555"

def ensure_adb():
    try:
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.run(
            [ADB_PATH, "connect", TARGET],
            startupinfo=startupinfo,
            creationflags=creationflags,
            timeout=3,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except Exception:
        pass

def play_on_station(sound_name):
    ensure_adb()
    cmd = [ADB_PATH, "shell", f"aplay /bkupgrade/data/opt/sounds/{sound_name}.wav"]
    try:
        startupinfo = None
        creationflags = 0
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0
            creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        subprocess.Popen(
            cmd,
            startupinfo=startupinfo,
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        print(f"🔊 [PLAYING] -> {sound_name}")
    except Exception as e:
        print(f"Error: {e}")

def stop_sounds():
    ensure_adb()
    cmd = [ADB_PATH, "shell", "killall -9 aplay 2>/dev/null; sh /bkupgrade/data/opt/rgb_effects.sh stop; sh /bkupgrade/data/opt/led_helper.sh clear"]
    try:
        subprocess.run(cmd, capture_output=True, timeout=3)
        print("⏹️ [STOPPED ALL SOUNDS]")
    except Exception:
        pass

# Hotkey Mapping
KEY_MAP = {
    "num 1": "bruh",
    "num 2": "vine_boom",
    "num 3": "metal_pipe",
    "num 4": "discord",
    "num 5": "fart",
    "num 6": "airhorn",
    "num 7": "winxp",
    "num 8": "what",
    "num 9": "alarm_loud",
    "num 0": "rickroll"
}

def on_press(key_name, sound):
    def handler():
        play_on_station(sound)
    return handler

def main():
    print("=" * 65)
    print("      PC NUMPAD SOUNDPAD FOR YANDEX STATION MINI 3")
    print("=" * 65)
    print("Нажимай клавиши на цифровом блоке (Numpad) клавиатуры:")
    print("  [Num 1] -> 🗿 Bruh")
    print("  [Num 2] -> 💥 Vine Boom")
    print("  [Num 3] -> 🔩 Metal Pipe")
    print("  [Num 4] -> 💬 Discord notification")
    print("  [Num 5] -> 💨 Fart with reverb")
    print("  [Num 6] -> 📢 MLG Airhorn")
    print("  [Num 7] -> 💻 Windows XP Startup")
    print("  [Num 8] -> ❓ What the hell?!")
    print("  [Num 9] -> 🚨 Nuclear Alarm / Loud Siren")
    print("  [Num 0] -> 🕺 Rickroll")
    print("  [Num -] -> ⏹️ Stop all sounds")
    print("=" * 65)
    print("Слушаю нажатия клавиш... (Сверни это окно и играй, бинды работают везде!)")
    print("Для выхода нажми Ctrl + C в этом окне.")
    print("=" * 65)

    ensure_adb()

    for key, sound in KEY_MAP.items():
        keyboard.add_hotkey(key, on_press(key, sound))
    
    keyboard.add_hotkey("num -", stop_sounds)

    keyboard.wait()

if __name__ == "__main__":
    main()
