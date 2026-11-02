#!/bin/sh
PIDFILE="/var/run/alarm_helper.pid"
MODE=${1:-start}

# Determine script base dir dynamically
if [ -d "/bkupgrade/data/opt" ]; then
    OPT_DIR="/bkupgrade/data/opt"
elif [ -d "/data/opt" ]; then
    OPT_DIR="/data/opt"
else
    OPT_DIR="$(dirname "$0")"
fi

if [ "$MODE" = "stop" ]; then
    if [ -f "$PIDFILE" ]; then
        PID=$(cat "$PIDFILE")
        if [ -n "$PID" ]; then
            kill -9 "$PID" 2>/dev/null
        fi
        rm -f "$PIDFILE"
    fi
    killall -9 aplay tinyplay 2>/dev/null
    rm -f /tmp/tcb_alarm_active /tmp/tcb_alarm_loop.pid /tmp/tcb_alarm_player.pid 2>/dev/null
    [ -f "$OPT_DIR/rgb_effects.sh" ] && sh "$OPT_DIR/rgb_effects.sh" stop >/dev/null 2>&1
    [ -f "$OPT_DIR/led_helper.sh" ] && sh "$OPT_DIR/led_helper.sh" clear >/dev/null 2>&1
    # Turn off leds in sysfs if present
    for l in /sys/class/leds/*red* /sys/class/leds/*blue* /sys/class/leds/*green*; do
        [ -f "$l/brightness" ] && echo 0 > "$l/brightness" 2>/dev/null
    done
    amixer -q set Master 65% 2>/dev/null || amixer -q set Master 165 2>/dev/null || amixer -q set Playback 65% 2>/dev/null
    exit 0
fi

# Stop any previous instance
if [ -f "$PIDFILE" ]; then
    PID=$(cat "$PIDFILE")
    if [ -n "$PID" ]; then
        kill -9 "$PID" 2>/dev/null
    fi
    rm -f "$PIDFILE"
fi
killall -9 aplay tinyplay rgb_loop.sh 2>/dev/null

echo $$ > "$PIDFILE"

# Maximum loud volume across all known mixers
amixer -q set Master 100% 2>/dev/null || amixer -q set Master 255 2>/dev/null || amixer -q set Playback 100% 2>/dev/null || amixer -q set 'Line Out' 100% 2>/dev/null || amixer -q set Speaker 100% 2>/dev/null

# Visual alert
if [ -f "$OPT_DIR/rgb_effects.sh" ]; then
    sh "$OPT_DIR/rgb_effects.sh" police 0.04 >/dev/null 2>&1 &
fi
if [ -f "$OPT_DIR/led_helper.sh" ]; then
    sh "$OPT_DIR/led_helper.sh" show B0 C0 E0 F0 G0 A1 D1 E1 F1 G1 D2 E2 F2 A3 B3 E3 F3 G3 >/dev/null 2>&1
fi

SOUNDS_DIR="$OPT_DIR/sounds"
WARN_FILE="$SOUNDS_DIR/police_warning.wav"
ALARM_FILE="$SOUNDS_DIR/alarm_loud.wav"
[ ! -f "$ALARM_FILE" ] && ALARM_FILE="$SOUNDS_DIR/alarm.wav"
[ ! -f "$ALARM_FILE" ] && ALARM_FILE="$SOUNDS_DIR/siren.wav"

if [ "$MODE" != "siren_only" ] && [ -f "$WARN_FILE" ]; then
    aplay -q "$WARN_FILE" 2>/dev/null || tinyplay "$WARN_FILE" 2>/dev/null
fi

# Continuous siren loop until stopped!
while [ -f "$PIDFILE" ]; do
    if [ -f "$ALARM_FILE" ]; then
        aplay -q "$ALARM_FILE" 2>/dev/null || tinyplay "$ALARM_FILE" 2>/dev/null
    else
        # Fallback beep if sound file is missing
        echo -e "\a" > /dev/tty0 2>/dev/null
        sleep 1
    fi
done

rm -f "$PIDFILE"
