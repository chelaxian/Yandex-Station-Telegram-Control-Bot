#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Универсальный установщик и мастер настройки Yandex Station Telegram Control Bot
Запускает установщик из внутренней папки bot/
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.join(BASE_DIR, "bot")
SETUP_PY = os.path.join(BOT_DIR, "setup.py")

if not os.path.exists(SETUP_PY):
    print("=" * 60)
    print("❌ ОШИБКА: Файл установщика не найден по пути:")
    print(f"   {SETUP_PY}")
    print("=" * 60)
    sys.exit(1)

# Переходим в рабочую папку бота
os.chdir(BOT_DIR)
sys.path.insert(0, BOT_DIR)

# Запуск основного мастера установки
with open(SETUP_PY, "rb") as f:
    code = compile(f.read(), SETUP_PY, "exec")
    exec(code, {"__name__": "__main__", "__file__": SETUP_PY})
