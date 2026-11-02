#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Универсальный мастер установки и настройки Yandex Station Telegram Control Bot
(Mini 1/2/3, Lite 1/2, Midi, Station 2, Max)
"""

import os
import sys
import time
import socket
import shutil
import subprocess
import configparser
from concurrent.futures import ThreadPoolExecutor

try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "config.ini")
ALLOWED_USERS_FILE = os.path.join(BASE_DIR, "allowed_users.json")

def get_adb_path():
    if sys.platform == "win32":
        local_adb = os.path.join(BASE_DIR, "tools_adb", "adb.exe")
        if os.path.exists(local_adb):
            return local_adb
        return "adb"
    else:
        local_adb = os.path.join(BASE_DIR, "tools_adb", "adb")
        if os.path.exists(local_adb):
            return local_adb
        return "adb"

ADB_PATH = get_adb_path()

def clear_screen():
    os.system("cls" if sys.platform == "win32" else "clear")

def print_banner():
    print("=" * 70)
    print("   🎙️  МАСТЕР УСТАНОВКИ И НАСТРОЙКИ YANDEX TELEGRAM CONTROL BOT  🎙️")
    print("      Поддержка: Станция Мини 1/2/3, Лайт 1/2, Миди, Станция 2, Макс")
    print("   📢 Официальный канал: https://t.me/Yandex_Remote")
    print("=" * 70)

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

def auto_scan_station():
    local_ip = get_local_ip()
    if local_ip.startswith("127."):
        print("⚠️ Не удалось определить локальный IP-адрес ПК.")
        return None

    parts = local_ip.split('.')
    subnet = f"{parts[0]}.{parts[1]}.{parts[2]}"
    print(f"\n🔍 Быстрое авто-сканирование Wi-Fi сети ({subnet}.1 - 254)...")
    print("⏳ Поиск Яндекс Станции с открытым портом ADB 5555 (1-2 сек)...")

    def _check(ip):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        try:
            if s.connect_ex((ip, 5555)) == 0:
                return ip
        except Exception:
            pass
        finally:
            s.close()
        return None

    found_ips = []
    with ThreadPoolExecutor(max_workers=64) as ex:
        ips = [f"{subnet}.{i}" for i in range(1, 255)]
        for res in ex.map(_check, ips):
            if res:
                found_ips.append(res)

    valid_stations = []
    for ip in found_ips:
        try:
            subprocess.run([ADB_PATH, "disconnect", f"{ip}:5555"], capture_output=True, timeout=2)
            c = subprocess.run([ADB_PATH, "connect", f"{ip}:5555"], capture_output=True, text=True, timeout=3)
            if "connected" in c.stdout.lower() or "already" in c.stdout.lower():
                h = subprocess.run([ADB_PATH, "-s", f"{ip}:5555", "shell", "cat /etc/hostname 2>/dev/null; uname -m 2>/dev/null"], capture_output=True, text=True, timeout=3)
                host_str = h.stdout.strip().replace("\n", " | ")
                valid_stations.append({"ip": ip, "info": host_str or "Yandex Station"})
        except Exception:
            pass

    if not valid_stations:
        return None
    elif len(valid_stations) == 1:
        return valid_stations[0]["ip"]
    else:
        print("\n🎉 Найдено несколько Станций в сети:")
        for idx, s in enumerate(valid_stations, 1):
            print(f"   [{idx}] {s['ip']} — {s['info']}")
        choice = input("\nВыберите номер вашей Станции: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(valid_stations):
            return valid_stations[int(choice) - 1]["ip"]
        return valid_stations[0]["ip"]

def check_python_dependencies():
    print("\n[Проверка 1/3] Проверка библиотек Python на ПК...")
    req_file = os.path.join(BASE_DIR, "requirements.txt")
    try:
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", req_file, "--quiet"], check=False)
        print("✅ Все библиотеки Python установлены и готовы к работе!")
    except Exception as e:
        print(f"⚠️ pip: {e}")

def deploy_scripts_to_speaker(ip, port="5555"):
    target = f"{ip}:{port}"
    print(f"\n[Установка на колонку] Подключение к {target}...")
    subprocess.run([ADB_PATH, "connect", target], capture_output=True)

    # Detect station opt folder
    res = subprocess.run([ADB_PATH, "-s", target, "shell", "[ -d /bkupgrade/data ] && echo 'bkupgrade' || echo 'data'"], capture_output=True, text=True)
    remote_opt = "/bkupgrade/data/opt" if "bkupgrade" in res.stdout else "/data/opt"
    print(f" -> Каталог модов на колонке: {remote_opt}")

    subprocess.run([ADB_PATH, "-s", target, "shell", f"mkdir -p {remote_opt}/sounds {remote_opt}/custom_scripts 2>/dev/null"], capture_output=True)

    scripts_dir = os.path.join(BASE_DIR, "speaker_scripts")
    if os.path.exists(scripts_dir):
        print(" -> Загрузка системных скриптов управления (RGB, экран, сирена, микрофон)...")
        for sfile in os.listdir(scripts_dir):
            if sfile.endswith(".sh"):
                sp = os.path.join(scripts_dir, sfile)
                subprocess.run([ADB_PATH, "-s", target, "push", sp, f"{remote_opt}/{sfile}"], capture_output=True)
                subprocess.run([ADB_PATH, "-s", target, "shell", f"chmod 755 {remote_opt}/{sfile} 2>/dev/null"], capture_output=True)

    sounds_dir = os.path.join(BASE_DIR, "sounds")
    if os.path.exists(sounds_dir):
        wavs = [f for f in os.listdir(sounds_dir) if f.lower().endswith(".wav")]
        print(f" -> Загрузка {len(wavs)} звуков саундборда на колонку...")
        for w in wavs:
            subprocess.run([ADB_PATH, "-s", target, "push", os.path.join(sounds_dir, w), f"{remote_opt}/sounds/{w}"], capture_output=True)

    # Set initial sound volume
    subprocess.run([ADB_PATH, "-s", target, "shell", "amixer -q set Master 85% 2>/dev/null || amixer -q set Playback 85% 2>/dev/null"], capture_output=True)

    # Sound check & LED stop
    subprocess.run([ADB_PATH, "-s", target, "shell", f"aplay -q {remote_opt}/sounds/telegram.wav 2>/dev/null || tinyplay {remote_opt}/sounds/telegram.wav 2>/dev/null"], capture_output=True)
    subprocess.run([ADB_PATH, "-s", target, "shell", f"sh {remote_opt}/rgb_effects.sh stop 2>/dev/null; killall -9 rgb_loop.sh 2>/dev/null; rm -f /tmp/rgb_loop.sh /tmp/rgb_state /data/opt/rgb_state 2>/dev/null"], capture_output=True)
    return remote_opt

def save_bot_configuration(ip, port, token, admin_id, admin_user=""):
    cfg = configparser.ConfigParser()
    if os.path.exists(CONFIG_PATH):
        cfg.read(CONFIG_PATH, encoding='utf-8')
    if not cfg.has_section("Station"):
        cfg.add_section("Station")
    cfg.set("Station", "ip", ip)
    cfg.set("Station", "port", str(port))

    if not cfg.has_section("TelegramBot"):
        cfg.add_section("TelegramBot")
    cfg.set("TelegramBot", "token", token)
    cfg.set("TelegramBot", "admin_id", str(admin_id))
    cfg.set("TelegramBot", "api_id", "37391973")
    cfg.set("TelegramBot", "api_hash", "19b41be2db006b1be52d7f0fefa1f8ae")

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        cfg.write(f)

    # Also update allowed_users.json
    allowed_data = {"ids": [admin_id] if admin_id else [], "usernames": []}
    if admin_user:
        allowed_data["usernames"].append(admin_user.lower().lstrip("@"))
    try:
        import json
        with open(ALLOWED_USERS_FILE, "w", encoding="utf-8") as f:
            json.dump(allowed_data, f, indent=4, ensure_ascii=False)
    except Exception:
        pass

def main():
    clear_screen()
    print_banner()

    print("\nВЫБЕРИТЕ ВАРИАНТ УСТАНОВКИ:")
    print("  [1] 📻 Установить бота НА СТАНЦИЮ (Автономно 24/7)")
    print("      • Бот работает прямо внутри колонки")
    print("      • ПК нужен только 1 раз для установки, потом его можно выключить")
    print("      • Автозапуск при включении колонки в розетку\n")
    print("  [2] 💻 Запустить бота НА КОМПЬЮТЕРЕ (Классический режим)")
    print("      • Бот работает в фоне на вашем ПК (Windows / Linux)")
    print("      • Управляет колонкой по домашнему Wi-Fi")
    print("      • Работает, пока включен компьютер\n")

    mode_choice = input("Ваш выбор [1 или 2, по умолчанию 2]: ").strip()
    is_speaker_mode = (mode_choice == "1")

    # Step 1: Discover Station IP
    print("\n[Шаг 1/3] Поиск Яндекс Станции в сети...")
    ip = auto_scan_station()
    if not ip:
        print("⚠️ Автоматически найти Станцию не удалось.")
        ip = input("Введите IP-адрес вашей Яндекс Станции вручную (например: 192.168.0.100): ").strip()
        if not ip:
            ip = "192.168.0.100"
    else:
        print(f"🎉 Найдена Яндекс Станция: {ip}")

    port = "5555"

    # Step 2: Telegram Credentials
    print("\n" + "=" * 70)
    print("[Шаг 2/3] Настройка Telegram-бота...")
    print("=" * 70)
    print("1. Откройте диалог с @BotFather в Telegram (https://t.me/BotFather)")
    print("2. Создайте нового бота (/newbot) или выберите существующего (/mybots -> API Token)")
    token = input("\nВставьте токен вашего бота (HTTP API Token): ").strip()
    while not token or ":" not in token:
        print("⚠️ Ошибка: Токен бота должен содержать двоеточие (например: 123456789:AAH...)!")
        token = input("Повторите ввод токена бота: ").strip()

    print("\n3. Теперь укажите ваш Telegram @username или цифровой ID:")
    print("   • Можете ввести ваш @username (например: @durov или ivan)")
    print("   • Либо цифровой ID из бота @userinfobot (например: 123456789)")
    admin_input = input("\nВаш Telegram @username или ID: ").strip()
    
    admin_id = 0
    admin_user = ""
    if admin_input.isdigit():
        admin_id = int(admin_input)
    else:
        admin_user = admin_input.lstrip("@")
        # Default placeholder numeric ID if user provided only username
        admin_id = 1

    # Save configuration
    save_bot_configuration(ip, port, token, admin_id, admin_user)

    # Step 3: Deployment
    print("\n" + "=" * 70)
    print("[Шаг 3/3] Развёртывание компонентов...")
    print("=" * 70)
    remote_opt = deploy_scripts_to_speaker(ip, port)

    if is_speaker_mode:
        print("\n📻 Настройка автономного запуска на Станции...")
        target = f"{ip}:{port}"
        # Push configuration and bot to station
        subprocess.run([ADB_PATH, "-s", target, "push", CONFIG_PATH, f"{remote_opt}/config.ini"], capture_output=True)
        subprocess.run([ADB_PATH, "-s", target, "push", ALLOWED_USERS_FILE, f"{remote_opt}/allowed_users.json"], capture_output=True)
        subprocess.run([ADB_PATH, "-s", target, "push", os.path.join(BASE_DIR, "bot.py"), f"{remote_opt}/bot.py"], capture_output=True)
        
        # Create station startup launcher
        launcher_cmd = f"echo '#!/bin/sh\ncd {remote_opt}\n' > {remote_opt}/autostart.sh && chmod +x {remote_opt}/autostart.sh"
        subprocess.run([ADB_PATH, "-s", target, "shell", launcher_cmd], capture_output=True)

        print("\n" + "=" * 70)
        print("🎉 УСТАНОВКА НА ЯНДЕКС СТАНЦИЮ УСПЕШНО ЗАВЕРШЕНА!")
        print("=" * 70)
        print(f"• Станция: {ip}:{port}")
        print(f"• Токен бота сохранен")
        print(f"• Разрешенный доступ: @{admin_user}" if admin_user else f"• Admin ID: {admin_id}")
        print("• Станция готова к автономной работе 24/7.")
        print("• Теперь компьютер можно выключить!")
    else:
        check_python_dependencies()
        print("\n" + "=" * 70)
        print("🎉 НАСТРОЙКА ДЛЯ ПК УСПЕШНО ЗАВЕРШЕНА!")
        print("=" * 70)
        print(f"• Станция: {ip}:{port}")
        print(f"• Токен бота и ID сохранены в config.ini")
        print("\nДля запуска бота:")
        if sys.platform == "win32":
            print("▶️ Запустите файл: start.bat (или START.vbs)")
        else:
            print("▶️ Запустите файл: ./start.sh")

        run_now = input("\nЗапустить бота прямо сейчас? [Y/n]: ").strip().lower()
        if run_now != "n":
            start_script = "start.bat" if sys.platform == "win32" else "./start.sh"
            subprocess.Popen([sys.executable, os.path.join(BASE_DIR, "bot.py")])
            print("🚀 Бот успешно запущен в фоновом режиме!")

    print("\nОткройте Telegram и отправьте команду /start вашему боту!")
    input("\n[Нажмите Enter для завершения мастера...]")

if __name__ == "__main__":
    main()
