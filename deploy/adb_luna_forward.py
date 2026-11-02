"""Supervise one existing ADB device's LUNA forward; never change device configuration."""
import argparse
import logging
import subprocess
import time


def run(args, timeout=6):
    return subprocess.run(["/usr/bin/adb", *args], capture_output=True, text=True, timeout=timeout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--serial", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("port must be 1024..65535")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    ready = False
    while True:
        try:
            state = run(["-s", args.serial, "get-state"])
            if state.returncode or state.stdout.strip() != "device":
                run(["connect", args.serial])
                state = run(["-s", args.serial, "get-state"])
                if state.returncode or state.stdout.strip() != "device":
                    raise RuntimeError("ADB device unavailable")
            forwards = run(["forward", "--list"])
            if forwards.returncode:
                raise RuntimeError("ADB forward listing failed")
            expected = [args.serial, f"tcp:{args.port}", "tcp:8100"]
            entries = [line.split() for line in forwards.stdout.splitlines()]
            if expected not in entries:
                if any(len(e) > 1 and e[1] == expected[1] for e in entries):
                    raise RuntimeError("Forward port already belongs to another device")
                result = run(["-s", args.serial, "forward", "--no-rebind", *expected[1:]])
                if result.returncode:
                    raise RuntimeError("ADB forward creation failed")
            if not ready:
                logging.info("LUNA forward ready")
            ready = True
        except (RuntimeError, subprocess.TimeoutExpired):
            if ready:
                logging.warning("LUNA forward unavailable; reconnecting")
            ready = False
        time.sleep(3)


if __name__ == "__main__":
    main()
