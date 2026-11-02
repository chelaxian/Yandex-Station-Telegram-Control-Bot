#!/bin/sh
DURATION=${1:-5}
OUTFILE=${2:-/tmp/rec_room.wav}

# 1. Boost microphone gain if control exists
amixer cset numid=12 40 >/dev/null 2>&1 || amixer set 'Capture' 100% >/dev/null 2>&1

# 2. Pause launcher so ALSA capture device is released
LPID=$(pidof quasar_launcher2)
if [ -n "$LPID" ]; then
    kill -STOP $LPID 2>/dev/null
fi
killall -9 maind 2>/dev/null
usleep 150000

# 3. Adaptive recording across models:
# - Mini 3: 8 channels on hw:0,1
# - Mini 2 / Lite 2: 4/2 channels on hw:0,0 or hw:0,1
# - Mini 1 / Lite 1: 4/2 channels on default or hw:0,0
if arecord -D hw:0,1 -d "$DURATION" -c 8 -r 48000 -f S16_LE "$OUTFILE" 2>/dev/null; then
    :
elif arecord -D hw:0,0 -d "$DURATION" -c 4 -r 16000 -f S16_LE "$OUTFILE" 2>/dev/null; then
    :
elif arecord -D default -d "$DURATION" -c 2 -r 16000 -f S16_LE "$OUTFILE" 2>/dev/null; then
    :
else
    arecord -d "$DURATION" -f S16_LE "$OUTFILE" 2>/dev/null
fi

# 4. Instantly resume launcher
if [ -n "$LPID" ]; then
    kill -CONT $LPID 2>/dev/null
fi
