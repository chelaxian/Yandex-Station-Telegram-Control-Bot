#!/bin/sh
if [ -d "/sys/class/leds/bergamot:white:clockA0" ]; then
    D=/sys/class/leds/bergamot:white:clock
elif [ -d "/sys/class/leds/chive:white:clockA0" ]; then
    D=/sys/class/leds/chive:white:clock
else
    FOUND_CLOCK=$(ls -d /sys/class/leds/*clockA0 2>/dev/null | head -n 1)
    if [ -n "$FOUND_CLOCK" ]; then
        D=$(echo "$FOUND_CLOCK" | sed 's/A0$//')
    else
        D=/sys/class/leds/bergamot:white:clock
    fi
fi
PIDFILE=/var/run/led_anim.pid

stop_anim() {
    if [ -f "$PIDFILE" ]; then
        kill -9 $(cat "$PIDFILE") 2>/dev/null
    fi
    start-stop-daemon --stop -p "$PIDFILE" 2>/dev/null
    for p in $(ps | grep led_anim | grep -v grep | awk '{print $1}'); do
        kill -9 "$p" 2>/dev/null
    done
    rm -f "$PIDFILE" /tmp/led_anim.sh /tmp/led_mini3.sh 2>/dev/null
}

clear_all_leds() {
    for s in A B C D E F G H; do
        for p in 0 1 2 3; do
            echo 0 > ${D}${s}${p}/brightness 2>/dev/null
        done
    done
    echo 0 > ${D}DEGREE/brightness 2>/dev/null
    echo 0 > ${D}DH/brightness 2>/dev/null
    echo 0 > ${D}DL/brightness 2>/dev/null
    echo 0 > ${D}DM/brightness 2>/dev/null
}

clock_pause() {
    echo '{"brightness":1.0,"clockEnabled":false,"isClockOn":false,"showClockDuringDnd":false}' > /bkupgrade/data/quasar/data/clock_display_settings.dat 2>/dev/null
    echo '{"brightness":1.0,"clockEnabled":false,"isClockOn":false,"showClockDuringDnd":false}' > /data/quasar/data/clock_display_settings.dat 2>/dev/null
    clear_all_leds
}

clock_resume() {
    stop_anim
    echo '{"brightness":1.0,"clockEnabled":true,"isClockOn":true,"showClockDuringDnd":true}' > /bkupgrade/data/quasar/data/clock_display_settings.dat 2>/dev/null
    echo '{"brightness":1.0,"clockEnabled":true,"isClockOn":true,"showClockDuringDnd":true}' > /data/quasar/data/clock_display_settings.dat 2>/dev/null
    SYNC=$(ls -d /sys/class/leds/*sync*clock* 2>/dev/null | head -n 1)
    [ -n "$SYNC" ] && echo 255 > "$SYNC/brightness" 2>/dev/null
    echo 255 > /sys/class/leds/cucumber:sync:clock-0/brightness 2>/dev/null
}

adaptive_off() {
    # 1. Force light sensor to report blinding daylight (50000 lux) via bind mount
    echo "50000.0" > /tmp/fake_lux 2>/dev/null
    umount /sys/bus/iio/devices/iio:device1/in_intensity_input 2>/dev/null
    mount -o bind /tmp/fake_lux /sys/bus/iio/devices/iio:device1/in_intensity_input 2>/dev/null

    # 2. Force hardware brightness scale table to 255 (maximum) across all lux levels
    echo "2;255;104;255;162;255;255;255" > /tmp/fake_scale 2>/dev/null
    umount /sys/bus/i2c/devices/0-0035/brightness_scale 2>/dev/null
    mount -o bind /tmp/fake_scale /sys/bus/i2c/devices/0-0035/brightness_scale 2>/dev/null

    # 3. Force Global Current Control (GCC) and sync brightness to 255
    echo 255 > /sys/bus/i2c/devices/0-0035/gcc 2>/dev/null
    echo 255 > /sys/class/leds/cucumber:sync:clock-0/brightness 2>/dev/null
    echo '{"brightness":1.0,"clockEnabled":true,"isClockOn":true,"showClockDuringDnd":true}' > /bkupgrade/data/quasar/data/clock_display_settings.dat 2>/dev/null
    echo '{"brightness":1.0,"clockEnabled":true,"isClockOn":true,"showClockDuringDnd":true}' > /data/quasar/data/clock_display_settings.dat 2>/dev/null
}

adaptive_on() {
    umount /sys/bus/iio/devices/iio:device1/in_intensity_input 2>/dev/null
    umount /sys/bus/i2c/devices/0-0035/brightness_scale 2>/dev/null
    rm -f /tmp/fake_lux /tmp/fake_scale 2>/dev/null
    echo 160 > /sys/bus/i2c/devices/0-0035/gcc 2>/dev/null
}

set_brightness() {
    val=${1:-255}
    if [ "$val" -ge 180 ]; then
        adaptive_off
    elif [ "$val" -le 40 ]; then
        echo "0.0" > /tmp/fake_lux 2>/dev/null
        umount /sys/bus/iio/devices/iio:device1/in_intensity_input 2>/dev/null
        mount -o bind /tmp/fake_lux /sys/bus/iio/devices/iio:device1/in_intensity_input 2>/dev/null

        echo "2;15;104;15;162;15;255;15" > /tmp/fake_scale 2>/dev/null
        umount /sys/bus/i2c/devices/0-0035/brightness_scale 2>/dev/null
        mount -o bind /tmp/fake_scale /sys/bus/i2c/devices/0-0035/brightness_scale 2>/dev/null

        echo "$val" > /sys/bus/i2c/devices/0-0035/gcc 2>/dev/null
        echo "$val" > /sys/class/leds/cucumber:sync:clock-0/brightness 2>/dev/null
    else
        umount /sys/bus/iio/devices/iio:device1/in_intensity_input 2>/dev/null
        umount /sys/bus/i2c/devices/0-0035/brightness_scale 2>/dev/null
        echo "$val" > /sys/bus/i2c/devices/0-0035/gcc 2>/dev/null
        echo "$val" > /sys/class/leds/cucumber:sync:clock-0/brightness 2>/dev/null
    fi
}

show_segs() {
    stop_anim
    clock_pause
    echo 255 > /sys/class/leds/cucumber:sync:clock-0/brightness 2>/dev/null
    for seg in "$@"; do
        echo 255 > ${D}${seg}/brightness 2>/dev/null
    done
}

show_face() {
    case "$1" in
        smiley) show_segs G0 G3 E1 D1 D2 C2 ;;
        sad) show_segs G0 G3 F1 A1 A2 B2 ;;
        neutral) show_segs G0 G3 G1 G2 ;;
        surprised) show_segs G0 G3 A1 D1 ;;
        angry) show_segs A0 A3 G0 G3 G1 G2 ;;
        wink) show_segs G0 E1 D1 D2 C2 ;;
        bigsmile) show_segs G0 G3 F1 E1 D1 D2 E2 C2 ;;
        sleepy) show_segs D0 D3 G1 G2 ;;
        dead) show_segs C0 E0 F0 G0 C3 E3 F3 G3 D1 D2 ;;
        cool) show_segs B0 F0 B3 F3 E1 D1 D2 C2 ;;
        love) show_segs F0 E0 F3 E3 E1 D1 D2 C2 ;;
        uwu) show_segs C0 D0 E0 C3 D3 E3 C1 D1 E1 C2 D2 E2 ;;
        owo) show_segs A0 B0 F0 A3 B3 F3 D1 D2 ;;
        *) echo "Unknown face: $1" ;;
    esac
}

case "$1" in
    clear) stop_anim; clock_pause ;;
    resume|clock_on) clock_resume ;;
    clock_off) clock_pause ;;
    max|adaptive_off) adaptive_off ;;
    auto|adaptive_on) adaptive_on ;;
    brightness) set_brightness "$2" ;;
    show) shift; show_segs "$@" ;;
    face) show_face "$2" ;;
    stop) stop_anim ;;
    *) echo "Usage: $0 {max|auto|brightness val|clock_on|clock_off|face name|show segs...|clear|resume}" ;;
esac
