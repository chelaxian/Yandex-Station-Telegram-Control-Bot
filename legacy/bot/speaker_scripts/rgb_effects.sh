#!/bin/sh
PIDFILE=/var/run/rgb_effect.pid
STATEFILE=/tmp/rgb_state
if [ -d "/bkupgrade/data/opt" ]; then
    OPT_DIR="/bkupgrade/data/opt"
elif [ -d "/data/opt" ]; then
    OPT_DIR="/data/opt"
else
    OPT_DIR="/tmp"
fi
BACKUP_STATEFILE="$OPT_DIR/rgb_state"

# Dynamic Universal Hardware Detection (Mini 1/2/3, Lite 1/2)
D=""
for prefix in /sys/class/leds/plum /sys/class/leds/bergamot /sys/class/leds/chive /sys/class/leds/lemon /sys/class/leds/onion /sys/class/leds/cucumber; do
    if ls -d ${prefix}* 2>/dev/null | grep -q .; then
        D="$prefix"
        break
    fi
done
if [ -z "$D" ]; then
    FOUND_LOGO=$(ls -d /sys/class/leds/*logo0 2>/dev/null | head -n 1)
    [ -n "$FOUND_LOGO" ] && D=$(echo "$FOUND_LOGO" | sed 's/:.*//')
fi
[ -z "$D" ] && D="/sys/class/leds/bergamot"

CHIP=""
for c in /sys/bus/i2c/devices/1-0020 /sys/bus/i2c/devices/0-0020 /sys/bus/i2c/devices/*0020; do
    if [ -f "${c}/gcc" ]; then
        CHIP="$c"
        break
    fi
done

LED_IDXS=""
for idx in 0 1 2 3 4 5 6 7; do
    if ls -d /sys/class/leds/*logo${idx} 2>/dev/null | grep -q . || ls -d /sys/class/leds/*:${idx} 2>/dev/null | grep -q .; then
        LED_IDXS="$LED_IDXS $idx"
    fi
done
if [ -n "$D" ] && [ "$D" = "/sys/class/leds/plum" ]; then
    # Lite 2 exposes three RGB ring zones instead of logo0..logoN LEDs
    LED_IDXS="1 2 3"
else
    [ -z "$LED_IDXS" ] && LED_IDXS="0 1 2 3 4 5"
fi

ALL_RED=$(ls -d /sys/class/leds/*red* /sys/class/leds/*:r:* 2>/dev/null | grep -v clock | grep -v sync)
ALL_GREEN=$(ls -d /sys/class/leds/*green* /sys/class/leds/*:g:* 2>/dev/null | grep -v clock | grep -v sync)
ALL_BLUE=$(ls -d /sys/class/leds/*blue* /sys/class/leds/*:b:* 2>/dev/null | grep -v clock | grep -v sync)

save_state() {
    echo "$*" > "$STATEFILE" 2>/dev/null
    echo "$*" > "$BACKUP_STATEFILE" 2>/dev/null
}

get_state() {
    if [ -f "$STATEFILE" ]; then
        cat "$STATEFILE" 2>/dev/null
    elif [ -f "$BACKUP_STATEFILE" ]; then
        cat "$BACKUP_STATEFILE" 2>/dev/null
    fi
}

apply_rgb() {
    r=$1; g=$2; b=$3
    [ -n "$CHIP" ] && echo 255 > ${CHIP}/gcc 2>/dev/null
    for i in $LED_IDXS; do
        echo "$r" > ${D}:red:logo${i}/brightness 2>/dev/null
        echo "$g" > ${D}:green:logo${i}/brightness 2>/dev/null
        echo "$b" > ${D}:blue:logo${i}/brightness 2>/dev/null
        echo "$r" > ${D}:red:ring${i}/brightness 2>/dev/null
        echo "$g" > ${D}:green:ring${i}/brightness 2>/dev/null
        echo "$b" > ${D}:blue:ring${i}/brightness 2>/dev/null
    done
    for f in $ALL_RED; do echo "$r" > "$f/brightness" 2>/dev/null; done
    for f in $ALL_GREEN; do echo "$g" > "$f/brightness" 2>/dev/null; done
    for f in $ALL_BLUE; do echo "$b" > "$f/brightness" 2>/dev/null; done
}

stop_effect() {
    if [ -f "$PIDFILE" ]; then
        kill -9 $(cat "$PIDFILE") 2>/dev/null
        rm -f "$PIDFILE"
    fi
    start-stop-daemon --stop -p "$PIDFILE" 2>/dev/null
    for p in $(ps | grep rgb_loop | grep -v grep | awk '{print $1}'); do
        kill -9 "$p" 2>/dev/null
    done
    killall -9 rgb_loop.sh 2>/dev/null
    rm -f "$PIDFILE" /tmp/rgb_loop.sh 2>/dev/null
    apply_rgb 0 0 0
    for f in $ALL_RED $ALL_GREEN $ALL_BLUE; do
        echo 0 > "$f/brightness" 2>/dev/null
    done
}

set_static() {
    stop_effect
    r=${1:-255}; g=${2:-255}; b=${3:-255}
    save_state static "$r" "$g" "$b"
    apply_rgb "$r" "$g" "$b"
}

run_rainbow() {
    stop_effect
    delay=${1:-0.1}
    save_state rainbow "$delay"
    cat << EOF > /tmp/rgb_loop.sh
#!/bin/sh
D="$D"
CHIP="$CHIP"
LED_IDXS="$LED_IDXS"
ALL_RED="$ALL_RED"
ALL_GREEN="$ALL_GREEN"
ALL_BLUE="$ALL_BLUE"
delay=\$1
[ -n "\$CHIP" ] && echo 255 > \${CHIP}/gcc 2>/dev/null

set_c() {
    r=\$1; g=\$2; b=\$3
    for i in \$LED_IDXS; do
        echo \$r > \${D}:red:logo\${i}/brightness 2>/dev/null
        echo \$g > \${D}:green:logo\${i}/brightness 2>/dev/null
        echo \$b > \${D}:blue:logo\${i}/brightness 2>/dev/null
    done
    for f in \$ALL_RED; do echo \$r > "\$f/brightness" 2>/dev/null; done
    for f in \$ALL_GREEN; do echo \$g > "\$f/brightness" 2>/dev/null; done
    for f in \$ALL_BLUE; do echo \$b > "\$f/brightness" 2>/dev/null; done
}

while true; do
    set_c 255 0 0; sleep \$delay
    set_c 255 60 0; sleep \$delay
    set_c 255 140 0; sleep \$delay
    set_c 255 220 0; sleep \$delay
    set_c 180 255 0; sleep \$delay
    set_c 60 255 0; sleep \$delay
    set_c 0 255 0; sleep \$delay
    set_c 0 255 80; sleep \$delay
    set_c 0 255 200; sleep \$delay
    set_c 0 200 255; sleep \$delay
    set_c 0 80 255; sleep \$delay
    set_c 0 0 255; sleep \$delay
    set_c 80 0 255; sleep \$delay
    set_c 180 0 255; sleep \$delay
    set_c 255 0 200; sleep \$delay
    set_c 255 0 80; sleep \$delay
done
EOF
    chmod 755 /tmp/rgb_loop.sh
    start-stop-daemon --start -b -m -p "$PIDFILE" -x /bin/sh -- /tmp/rgb_loop.sh "$delay"
}

run_breathe() {
    stop_effect
    r=${1:-180}; g=${2:-0}; b=${3:-255}
    delay=${4:-0.04}
    save_state breathe "$r" "$g" "$b" "$delay"
    apply_rgb "$r" "$g" "$b"
    cat << EOF > /tmp/rgb_loop.sh
#!/bin/sh
CHIP="$CHIP"
D="$D"
LED_IDXS="$LED_IDXS"
ALL_RED="$ALL_RED"
ALL_GREEN="$ALL_GREEN"
ALL_BLUE="$ALL_BLUE"
r=$r
g=$g
b=$b
delay=\$1
STEPS="10 18 28 42 60 82 110 145 185 225 255 225 185 145 110 82 60 42 28 18 10"
while true; do
    for val in \$STEPS; do
        if [ -n "\$CHIP" ]; then
            echo \$val > \${CHIP}/gcc 2>/dev/null
        else
            cur_r=\$(( r * val / 255 ))
            cur_g=\$(( g * val / 255 ))
            cur_b=\$(( b * val / 255 ))
            for i in \$LED_IDXS; do
                echo \$cur_r > \${D}:red:logo\${i}/brightness 2>/dev/null
                echo \$cur_g > \${D}:green:logo\${i}/brightness 2>/dev/null
                echo \$cur_b > \${D}:blue:logo\${i}/brightness 2>/dev/null
            done
            for f in \$ALL_RED; do echo \$cur_r > "\$f/brightness" 2>/dev/null; done
            for f in \$ALL_GREEN; do echo \$cur_g > "\$f/brightness" 2>/dev/null; done
            for f in \$ALL_BLUE; do echo \$cur_b > "\$f/brightness" 2>/dev/null; done
        fi
        sleep \$delay
    done
done
EOF
    chmod 755 /tmp/rgb_loop.sh
    start-stop-daemon --start -b -m -p "$PIDFILE" -x /bin/sh -- /tmp/rgb_loop.sh "$delay"
}

run_spin() {
    stop_effect
    delay=${1:-0.08}
    save_state spin "$delay"
    cat << EOF > /tmp/rgb_loop.sh
#!/bin/sh
D="$D"
CHIP="$CHIP"
LED_IDXS="$LED_IDXS"
delay=\$1
[ -n "\$CHIP" ] && echo 255 > \${CHIP}/gcc 2>/dev/null

set_led() {
    idx=\$1; r=\$2; g=\$3; b=\$4
    echo \$r > \${D}:red:logo\${idx}/brightness 2>/dev/null
    echo \$g > \${D}:green:logo\${idx}/brightness 2>/dev/null
    echo \$b > \${D}:blue:logo\${idx}/brightness 2>/dev/null
}

count=0
for i in \$LED_IDXS; do
    count=\$(( count + 1 ))
done

while true; do
    for target in \$LED_IDXS; do
        for i in \$LED_IDXS; do
            if [ "\$i" -eq "\$target" ]; then
                set_led \$i 0 255 255
            else
                set_led \$i 0 0 0
            fi
        done
        sleep \$delay
    done
done
EOF
    chmod 755 /tmp/rgb_loop.sh
    start-stop-daemon --start -b -m -p "$PIDFILE" -x /bin/sh -- /tmp/rgb_loop.sh "$delay"
}

run_spin_color() {
    stop_effect
    r=${1:-0}; g=${2:-255}; b=${3:-255}
    delay=${4:-0.08}
    save_state spin_color "$r" "$g" "$b" "$delay"
    cat << EOF > /tmp/rgb_loop.sh
#!/bin/sh
D="$D"
CHIP="$CHIP"
LED_IDXS="$LED_IDXS"
r=$r
g=$g
b=$b
delay=\$1
[ -n "\$CHIP" ] && echo 255 > \${CHIP}/gcc 2>/dev/null

set_led() {
    idx=\$1; scale=\$2
    echo \$(( r * scale / 100 )) > \${D}:red:logo\${idx}/brightness 2>/dev/null
    echo \$(( g * scale / 100 )) > \${D}:green:logo\${idx}/brightness 2>/dev/null
    echo \$(( b * scale / 100 )) > \${D}:blue:logo\${idx}/brightness 2>/dev/null
}

while true; do
    for target in \$LED_IDXS; do
        for i in \$LED_IDXS; do
            if [ "\$i" -eq "\$target" ]; then
                set_led \$i 100
            else
                set_led \$i 10
            fi
        done
        sleep \$delay
    done
done
EOF
    chmod 755 /tmp/rgb_loop.sh
    start-stop-daemon --start -b -m -p "$PIDFILE" -x /bin/sh -- /tmp/rgb_loop.sh "$delay"
}

run_police() {
    stop_effect
    delay=${1:-0.08}
    save_state police "$delay"
    cat << EOF > /tmp/rgb_loop.sh
#!/bin/sh
D="$D"
CHIP="$CHIP"
LED_IDXS="$LED_IDXS"
ALL_RED="$ALL_RED"
ALL_BLUE="$ALL_BLUE"
delay=\$1
[ -n "\$CHIP" ] && echo 255 > \${CHIP}/gcc 2>/dev/null

count=0
for i in \$LED_IDXS; do count=\$(( count + 1 )); done
half=\$(( count / 2 ))
[ "\$half" -lt 1 ] && half=1

while true; do
    for k in 1 2 3; do
        # Flash RED
        idx=0
        for i in \$LED_IDXS; do
            if [ "\$idx" -lt "\$half" ]; then
                echo 255 > \${D}:red:logo\${i}/brightness 2>/dev/null
                echo 0 > \${D}:blue:logo\${i}/brightness 2>/dev/null
                echo 0 > \${D}:green:logo\${i}/brightness 2>/dev/null
            else
                echo 0 > \${D}:red:logo\${i}/brightness 2>/dev/null
                echo 0 > \${D}:blue:logo\${i}/brightness 2>/dev/null
                echo 0 > \${D}:green:logo\${i}/brightness 2>/dev/null
            fi
            idx=\$(( idx + 1 ))
        done
        for f in \$ALL_RED; do echo 255 > "\$f/brightness" 2>/dev/null; done
        for f in \$ALL_BLUE; do echo 0 > "\$f/brightness" 2>/dev/null; done
        sleep \$delay

        # Off
        for i in \$LED_IDXS; do echo 0 > \${D}:red:logo\${i}/brightness 2>/dev/null; done
        for f in \$ALL_RED; do echo 0 > "\$f/brightness" 2>/dev/null; done
        sleep 0.04
    done

    for k in 1 2 3; do
        # Flash BLUE
        idx=0
        for i in \$LED_IDXS; do
            if [ "\$idx" -ge "\$half" ]; then
                echo 0 > \${D}:red:logo\${i}/brightness 2>/dev/null
                echo 255 > \${D}:blue:logo\${i}/brightness 2>/dev/null
                echo 0 > \${D}:green:logo\${i}/brightness 2>/dev/null
            else
                echo 0 > \${D}:red:logo\${i}/brightness 2>/dev/null
                echo 0 > \${D}:blue:logo\${i}/brightness 2>/dev/null
                echo 0 > \${D}:green:logo\${i}/brightness 2>/dev/null
            fi
            idx=\$(( idx + 1 ))
        done
        for f in \$ALL_RED; do echo 0 > "\$f/brightness" 2>/dev/null; done
        for f in \$ALL_BLUE; do echo 255 > "\$f/brightness" 2>/dev/null; done
        sleep \$delay

        # Off
        for i in \$LED_IDXS; do echo 0 > \${D}:blue:logo\${i}/brightness 2>/dev/null; done
        for f in \$ALL_BLUE; do echo 0 > "\$f/brightness" 2>/dev/null; done
        sleep 0.04
    done
done
EOF
    chmod 755 /tmp/rgb_loop.sh
    start-stop-daemon --start -b -m -p "$PIDFILE" -x /bin/sh -- /tmp/rgb_loop.sh "$delay"
}

run_strobe() {
    stop_effect
    delay=${1:-0.05}
    save_state strobe "$delay"
    cat << EOF > /tmp/rgb_loop.sh
#!/bin/sh
D="$D"
CHIP="$CHIP"
LED_IDXS="$LED_IDXS"
ALL_RED="$ALL_RED"
ALL_GREEN="$ALL_GREEN"
ALL_BLUE="$ALL_BLUE"
delay=\$1
[ -n "\$CHIP" ] && echo 255 > \${CHIP}/gcc 2>/dev/null
while true; do
    for i in \$LED_IDXS; do
        echo 255 > \${D}:red:logo\${i}/brightness 2>/dev/null
        echo 255 > \${D}:green:logo\${i}/brightness 2>/dev/null
        echo 255 > \${D}:blue:logo\${i}/brightness 2>/dev/null
    done
    for f in \$ALL_RED; do echo 255 > "\$f/brightness" 2>/dev/null; done
    for f in \$ALL_GREEN; do echo 255 > "\$f/brightness" 2>/dev/null; done
    for f in \$ALL_BLUE; do echo 255 > "\$f/brightness" 2>/dev/null; done
    sleep \$delay

    for i in \$LED_IDXS; do
        echo 0 > \${D}:red:logo\${i}/brightness 2>/dev/null
        echo 0 > \${D}:green:logo\${i}/brightness 2>/dev/null
        echo 0 > \${D}:blue:logo\${i}/brightness 2>/dev/null
    done
    for f in \$ALL_RED; do echo 0 > "\$f/brightness" 2>/dev/null; done
    for f in \$ALL_GREEN; do echo 0 > "\$f/brightness" 2>/dev/null; done
    for f in \$ALL_BLUE; do echo 0 > "\$f/brightness" 2>/dev/null; done
    sleep \$delay
done
EOF
    chmod 755 /tmp/rgb_loop.sh
    start-stop-daemon --start -b -m -p "$PIDFILE" -x /bin/sh -- /tmp/rgb_loop.sh "$delay"
}

run_notify() {
    PREV=$(get_state)
    stop_effect
    [ -n "$CHIP" ] && echo 255 > ${CHIP}/gcc 2>/dev/null
    apply_rgb 0 255 0
    for k in 1 2 3 4 5; do
        [ -n "$CHIP" ] && echo 255 > ${CHIP}/gcc 2>/dev/null
        usleep 120000
        [ -n "$CHIP" ] && echo 0 > ${CHIP}/gcc 2>/dev/null
        usleep 80000
    done
    apply_rgb 0 0 0

    # RESTORE PREVIOUS STATE AUTOMATICALLY
    if [ -n "$PREV" ] && [ "$PREV" != "stop" ]; then
        set -- $PREV
        prev_cmd="$1"
        shift
        case "$prev_cmd" in
            color|static) set_static "$@" ;;
            rainbow) run_rainbow "$@" ;;
            breathe) run_breathe "$@" ;;
            spin) run_spin "$@" ;;
            spin_color) run_spin_color "$@" ;;
            police) run_police "$@" ;;
            strobe) run_strobe "$@" ;;
        esac
    fi
}

case "$1" in
    stop) stop_effect; save_state stop ;;
    color|static) set_static "$2" "$3" "$4" ;;
    rainbow) run_rainbow "$2" ;;
    breathe) run_breathe "$2" "$3" "$4" "$5" ;;
    spin) run_spin "$2" ;;
    spin_color) run_spin_color "$2" "$3" "$4" "$5" ;;
    police) run_police "$2" ;;
    strobe) run_strobe "$2" ;;
    notify) run_notify ;;
    restore)
        PREV=$(get_state)
        if [ -n "$PREV" ] && [ "$PREV" != "stop" ]; then
            set -- $PREV
            prev_cmd="$1"
            shift
            case "$prev_cmd" in
                color|static) set_static "$@" ;;
                rainbow) run_rainbow "$@" ;;
                breathe) run_breathe "$@" ;;
                spin) run_spin "$@" ;;
                spin_color) run_spin_color "$@" ;;
                police) run_police "$@" ;;
                strobe) run_strobe "$@" ;;
            esac
        fi
        ;;
    *) echo "Usage: $0 {stop|static r g b|rainbow [speed]|breathe r g b [speed]|spin [speed]|spin_color r g b [speed]|police [speed]|strobe [speed]|notify|restore}" ;;
esac
