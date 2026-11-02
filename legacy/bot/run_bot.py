#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Self-Healing Launcher for Universal Yandex Station Telegram Control Bot
(Поддержка моделей: Станция Мини 1/2/3, Лайт 1/2)
"""

import os
import sys
import time
import socket
import shutil
import subprocess
import configparser

# Force UTF-8 encoding on Windows and Linux terminals
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(BASE_DIR)

def print_banner():
    print("=" * 70)
    print("   🎙️ UNIVERSAL YANDEX STATION TELEGRAM CONTROL BOT (Mini 1/2/3, Lite 1/2)")
    print("      Умный интерактивный запуск с самодиагностикой и автоисправлением")
    print("   📢 Телеграм Канал: https://t.me/Yandex_Remote")
    print("=" * 70)

def fix_linux_permissions():
    """Ensure executable bits on Linux/macOS for scripts and binaries"""
    if sys.platform != "win32":
        targets = [
            os.path.join(BASE_DIR, "tools_adb", "adb"),
            os.path.join(BASE_DIR, "start_bot.sh"),
            os.path.join(BASE_DIR, "setup_bot.sh"),
            os.path.join(BASE_DIR, "manage_bot.sh"),
        ]
        scripts_dir = os.path.join(BASE_DIR, "speaker_scripts")
        if os.path.isdir(scripts_dir):
            for f in os.listdir(scripts_dir):
                if f.endswith(".sh"):
                    targets.append(os.path.join(scripts_dir, f))
        for p in targets:
            if os.path.isfile(p):
                try:
                    st = os.stat(p)
                    os.chmod(p, st.st_mode | 0o755)
                except Exception:
                    pass

def check_and_install_dependencies():
    """Checks required packages and automatically installs them if missing"""
    required = {
        "telethon": "telethon>=1.36.0",
        "cv2": "opencv-python>=4.8.0",
        "soundfile": "soundfile>=0.12.0",
        "numpy": "numpy>=1.20.0",
        "psutil": "psutil>=5.9.0",
        "requests": "requests>=2.31.0",
        "socks": "PySocks>=1.7.1",
        "python_socks": "python-socks[asyncio]>=2.0.0"
    }
    if sys.platform == "win32":
        required["keyboard"] = "keyboard>=0.13.5"

    missing = []
    for mod, pkg in required.items():
        try:
            __import__(mod)
        except (ImportError, ModuleNotFoundError):
            missing.append(pkg)
        except Exception:
            pass

    if missing:
        print("\n🔍 Обнаружены недостающие библиотеки Python:")
        for m in missing:
            print(f"   • {m}")
        print("\n⏳ Выполняется автоматическая установка через pip (пожалуйста, подождите)...")
        req_file = os.path.join(BASE_DIR, "requirements.txt")
        try:
            if os.path.exists(req_file):
                cmd = [sys.executable, "-m", "pip", "install", "-r", req_file]
            else:
                cmd = [sys.executable, "-m", "pip", "install"] + missing
            res = subprocess.run(cmd)
            if res.returncode == 0:
                print("✅ Все необходимые библиотеки успешно установлены!\n")
            else:
                print(f"\n⚠️ Предупреждение: pip завершился с кодом {res.returncode}.")
                print("Если бот не запустится, установите зависимости вручную:")
                print(f"   {sys.executable} -m pip install -r requirements.txt\n")
        except Exception as e:
            print(f"\n⚠️ Не удалось запустить автоматическую установку pip: {e}")
            print(f"Попробуйте выполнить вручную: {sys.executable} -m pip install -r requirements.txt\n")

def check_config():
    """Checks config.ini; if missing or unconfigured, triggers setup wizard"""
    cfg_path = os.path.join(BASE_DIR, "config.ini")
    example_path = os.path.join(BASE_DIR, "config_example.ini")

    if not os.path.exists(cfg_path):
        if os.path.exists(example_path):
            try:
                shutil.copy(example_path, cfg_path)
            except Exception:
                pass

    needs_setup = False
    if not os.path.exists(cfg_path):
        needs_setup = True
    else:
        cfg = configparser.ConfigParser()
        try:
            cfg.read(cfg_path, encoding='utf-8')
            token = cfg.get("TelegramBot", "token", fallback="").strip()
            if not token or "YOUR_BOT_TOKEN" in token:
                needs_setup = True
        except Exception:
            needs_setup = True

    if needs_setup:
        print("\n" + "=" * 70)
        print("⚙️  Бот еще не настроен! (в config.ini не указан токен Telegram)")
        print("Запуск пошагового мастера настройки setup.py...")
        print("=" * 70 + "\n")
        setup_script = os.path.join(BASE_DIR, "setup.py")
        if os.path.exists(setup_script):
            try:
                subprocess.run([sys.executable, setup_script])
            except Exception as e:
                print(f"⚠️ Ошибка запуска мастера настройки: {e}")
        else:
            print("❌ Файл setup.py не найден! Создайте config.ini вручную.")

def check_and_clear_port(port=49153):
    """Check if port 49153 is busy. Offer to kill stale process or do clean restart."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.close()
        return True
    except Exception:
        pass

    # Port is busy!
    print(f"\n⚠️ Порт {port} занят! Похоже, бот уже работает в фоне или предыдущий процесс завис.")
    print("Попытка безопасного перезапуска...")

    try:
        import psutil
        current_pid = os.getpid()
        for p in psutil.process_iter(['pid', 'name', 'cmdline']):
            if p.info['pid'] == current_pid:
                continue
            cmdline = p.info.get('cmdline') or []
            cmd_str = " ".join(cmdline).lower()
            if "bot.py" in cmd_str and ("yandex" in cmd_str or "telegram_control" in cmd_str or "06_telegram" in cmd_str):
                try:
                    p.kill()
                    print(f" -> Завершен зависший процесс бота (PID {p.info['pid']})")
                except Exception:
                    pass
    except Exception:
        pass

    time.sleep(1)
    s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s2.bind(("127.0.0.1", port))
        s2.close()
        print("✅ Порт освобожден. Продолжаем запуск...")
        return True
    except Exception:
        print("⚠️ Не удалось освободить порт. Возможно, процесс имеет другие права доступа.")
        return False

def main():
    print_banner()
    fix_linux_permissions()
    check_and_install_dependencies()
    check_config()
    check_and_clear_port(49153)

    print("\n🚀 Запуск Telegram Control Bot...")
    print("Откройте Telegram и отправьте команду /start вашему боту.")
    print("Для остановки бота нажмите Ctrl+C в этом окне.\n" + "-" * 70)

    bot_py = os.path.join(BASE_DIR, "bot.py")
    try:
        ret = subprocess.run([sys.executable, bot_py])
        if ret.returncode != 0:
            print(f"\n⚠️ Бот завершил работу с кодом {ret.returncode}.")
            print("Подробности и ошибки смотрите выше или в файле bot.log.")
            input("\n[Нажмите Enter для выхода...]")
    except KeyboardInterrupt:
        print("\n\n⏹️ Бот остановлен пользователем.")
    except Exception as e:
        print(f"\n❌ Критическая ошибка запуска: {e}")
        input("\n[Нажмите Enter для выхода...]")

if __name__ == "__main__":
    main()
