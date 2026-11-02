#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Ensure executable permissions on Linux
chmod +x "$0" 2>/dev/null
chmod +x "$SCRIPT_DIR/tools_adb/adb" 2>/dev/null
chmod +x "$SCRIPT_DIR/start_bot.sh" 2>/dev/null
chmod +x "$SCRIPT_DIR/setup_bot.sh" 2>/dev/null
chmod +x "$SCRIPT_DIR/speaker_scripts/"*.sh 2>/dev/null

if [ -f "$SCRIPT_DIR/../../../.venv/bin/python3" ]; then
    PY="$SCRIPT_DIR/../../../.venv/bin/python3"
elif [ -f "$SCRIPT_DIR/../../.venv/bin/python3" ]; then
    PY="$SCRIPT_DIR/../../.venv/bin/python3"
elif [ -f "$SCRIPT_DIR/../.venv/bin/python3" ]; then
    PY="$SCRIPT_DIR/../.venv/bin/python3"
elif [ -f "$SCRIPT_DIR/.venv/bin/python3" ]; then
    PY="$SCRIPT_DIR/.venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PY="python3"
elif command -v python >/dev/null 2>&1; then
    PY="python"
else
    echo "================================================================="
    echo "❌ ОШИБКА: Python 3 не найден на вашей системе!"
    echo "================================================================="
    echo "Пожалуйста, установите Python 3:"
    echo "• Ubuntu / Debian / Mint:  sudo apt update && sudo apt install -y python3 python3-pip python3-venv"
    echo "• Fedora / RHEL:           sudo dnf install -y python3 python3-pip"
    echo "• Arch Linux / Manjaro:    sudo pacman -S python python-pip"
    echo "• openSUSE:                sudo zypper install python3 python3-pip"
    echo "================================================================="
    read -p "Нажмите Enter для выхода..." _dummy
    exit 1
fi

"$PY" manage_bot.py "$@"
EXIT_CODE=$?
if [ $EXIT_CODE -ne 0 ]; then
    echo ""
    read -p "Нажмите Enter для закрытия окна..." _dummy
fi
