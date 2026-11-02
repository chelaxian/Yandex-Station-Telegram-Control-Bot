#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Запуск Yandex Station Telegram Control Bot из внутренней папки bot/
"""
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BOT_DIR = os.path.join(BASE_DIR, "bot")
RUN_BOT = os.path.join(BOT_DIR, "run_bot.py")

if not os.path.exists(RUN_BOT):
    print("=" * 60)
    print("❌ ОШИБКА: Файл запуска бота не найден по пути:")
    print(f"   {RUN_BOT}")
    print("=" * 60)
    sys.exit(1)

# Переходим в рабочую папку бота
os.chdir(BOT_DIR)
sys.path.insert(0, BOT_DIR)

# Запуск бота с автоперезапуском при сбоях сети
with open(RUN_BOT, "rb") as f:
    code = compile(f.read(), RUN_BOT, "exec")
    exec(code, {"__name__": "__main__", "__file__": RUN_BOT})
