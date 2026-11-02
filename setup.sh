#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR/bot" || exit 1

chmod +x "$0" 2>/dev/null
chmod +x "$SCRIPT_DIR/start.sh" 2>/dev/null
chmod +x "$SCRIPT_DIR/bot/tools_adb/adb" 2>/dev/null
chmod +x "$SCRIPT_DIR/bot/speaker_scripts/"*.sh 2>/dev/null
chmod +x "$SCRIPT_DIR/bot/manage_bot.sh" 2>/dev/null

if [ -f "$SCRIPT_DIR/../../.venv/bin/python3" ]; then
    PY="$SCRIPT_DIR/../../.venv/bin/python3"
elif [ -f "$SCRIPT_DIR/../.venv/bin/python3" ]; then
    PY="$SCRIPT_DIR/../.venv/bin/python3"
elif [ -f "$SCRIPT_DIR/.venv/bin/python3" ]; then
    PY="$SCRIPT_DIR/.venv/bin/python3"
elif [ -f "$SCRIPT_DIR/bot/.venv/bin/python3" ]; then
    PY="$SCRIPT_DIR/bot/.venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
else
    echo "================================================================="
    echo "❌ ОШИБКА: Python 3 не найден!"
    echo "Установите Python 3: sudo apt install -y python3 python3-pip"
    echo "================================================================="
    exit 1
fi

"$PY" setup.py "$@"
