"""Experimental local LUNA-compatible gateway for the Android-based Yandex Station Max.

The Max cannot run the LUNA binary, so this process (stdlib only, run on the PC/server) exposes the small
slice of the LUNA HTTP contract that was confirmed on a real Max: device identity, music volume and WAV
playback jobs. Everything goes over the owner's existing root SSH connection. Nothing is installed on the
speaker; each action stages a private temporary directory under /data/local/tmp and removes it afterwards.
LED, display, microphone and intercom are intentionally NOT advertised (not qualified on Max).
"""
from __future__ import annotations

import argparse
import base64
import importlib.resources
import io
import json
import math
import queue
import re
import struct
import subprocess
import sys
import threading
import time
import uuid
import wave
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .max_ssh_probe import MaxSshTarget, probe_max_ssh
from .provision import ProvisionError

MODEL = "yandexstation_max"
FEATURES = ["arch.aarch64", "audio.jobs.v1", "audio.play.android", "audio.volume.android", "network"]
MAX_WAV = 64 * 1024 * 1024
MAX_SECONDS = 600
MAX_QUEUE = 8
KEEP_JOBS = 50

# Copy only the Android runtime variables from adbd: a bare root SSH session lacks them and ART aborts.
_ENV = (
    "p=$(pidof adbd | cut -d' ' -f1); [ -r \"/proc/$p/environ\" ] || exit 1; "
    "tr '\\000' '\\n' < \"/proc/$p/environ\" > \"$d/env\" || exit 1; "
    "while IFS= read -r l; do case \"$l\" in "
    "ANDROID_*=*|BOOTCLASSPATH=*|SYSTEMSERVERCLASSPATH=*|EXTERNAL_STORAGE=*|ASEC_MOUNTPOINT=*|"
    "LOOP_MOUNTPOINT=*|DOWNLOAD_CACHE=*|STANDALONE_SYSTEMSERVER_JARS=*|LD_LIBRARY_PATH=*) "
    "export \"$l\";; esac; done < \"$d/env\""
)
_VOLUME_RE = re.compile(r"volume is (\d+) in range \[(\d+)\.\.(\d+)\]")


class GatewayError(Exception):
    """A user-presentable failure; never carries raw device output."""


def volume_script(set_index: int | None = None) -> str:
    if set_index is not None and (type(set_index) is not int or not 0 <= set_index <= 100):
        raise GatewayError("Громкость: целое число 0–100")
    steps = [
        "umask 077", "d=$(mktemp -d /data/local/tmp/max-vol.XXXXXXXX) || exit 1",
        "trap 'rm -rf \"$d\"' EXIT", _ENV,
    ]
    if set_index is not None:
        steps.append(f"media volume --stream 3 --set {set_index} 2>&1")
    steps.append("media volume --stream 3 --get 2>&1")
    return "; ".join(steps)


def parse_volume(output: str) -> int:
    matches = _VOLUME_RE.findall(output)
    if not matches:
        raise GatewayError("Колонка вернула неизвестный ответ громкости")
    value, low, high = (int(x) for x in matches[-1])
    if high <= low or not low <= value <= high:
        raise GatewayError("Колонка вернула некорректный диапазон громкости")
    return round((value - low) * 100 / (high - low))


def play_directory(job_id: str) -> str:
    uuid.UUID(job_id)
    return f"/data/local/tmp/max-play-{job_id}"


def play_script(directory: str, jar_b64: str) -> str:
    if not re.fullmatch(r"/data/local/tmp/max-play-[0-9a-f-]{36}", directory):
        raise GatewayError("Некорректный каталог воспроизведения")
    steps = [
        "umask 077", f"d={directory}", "mkdir \"$d\" || exit 1", "trap 'rm -rf \"$d\"' EXIT",
        f"printf '%s' '{jar_b64}' | base64 -d > \"$d/play.jar\" || exit 1",
        "cat > \"$d/a.wav\" || exit 1", _ENV,
        "CLASSPATH=\"$d/play.jar\" app_process /system/bin MaxPlay \"$d/a.wav\" \"$d/stop\"",
    ]
    return "; ".join(steps)


def stop_script(directory: str) -> str:
    uuid.UUID(directory.rsplit("max-play-", 1)[-1])
    return f"[ -d {directory} ] && touch {directory}/stop"


def cleanup_script(directory: str) -> str:
    uuid.UUID(directory.rsplit("max-play-", 1)[-1])
    return f"rm -rf {directory}; [ ! -e {directory} ] && echo MAX_CLEAN_OK"


def validate_wav(data: bytes) -> float:
    """Return the duration in seconds for PCM16 mono/stereo WAV the on-device player accepts."""
    if not 44 <= len(data) <= MAX_WAV:
        raise GatewayError("Аудио: WAV до 64 МиБ")
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            ok = (wav.getsampwidth() == 2 and wav.getcomptype() == "NONE"
                  and wav.getnchannels() in {1, 2} and 8000 <= wav.getframerate() <= 48000
                  and wav.getnframes() > 0)
            duration = wav.getnframes() / wav.getframerate() if ok else 0.0
    except (wave.Error, EOFError, ZeroDivisionError) as error:
        raise GatewayError("Некорректный WAV") from error
    if not ok or duration > MAX_SECONDS:
        raise GatewayError("Нужен PCM16 WAV, моно или стерео, 8–48 кГц, до 10 минут")
    return duration


def test_tone() -> bytes:
    rate, frames = 48000, 24000
    pcm = b"".join(
        struct.pack("<h", int(8000 * min(1.0, i / 2400, (frames - 1 - i) / 2400)
                              * math.sin(2 * math.pi * 660 * i / rate)))
        for i in range(frames))
    out = io.BytesIO()
    with wave.open(out, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return out.getvalue()


@dataclass
class Job:
    id: str
    duration: float
    wav: bytes = field(repr=False)
    state: str = "queued"
    cleanup: str = "pending"
    error: str = ""
    cancel: threading.Event = field(default_factory=threading.Event)

    def public(self) -> dict:
        data = {"id": self.id, "state": self.state, "cleanup": self.cleanup}
        if self.error:
            data["error"] = self.error
        return data


class MaxStation:
    def __init__(self, target: MaxSshTarget, ssh: str = "ssh"):
        self.target = target
        self.ssh = ssh
        self.jar_b64 = base64.b64encode(
            importlib.resources.files("stationbot").joinpath("max-play.jar").read_bytes()).decode("ascii")
        self.volume_lock = threading.Lock()
        self.jobs: dict[str, Job] = {}
        self.keys: dict[str, str] = {}
        self.lock = threading.Lock()
        self.pending: queue.Queue[Job] = queue.Queue()
        threading.Thread(target=self._worker, name="max-player", daemon=True).start()

    # ---- SSH -------------------------------------------------------------------------------
    def argv(self, command: str) -> list[str]:
        t = self.target
        return [self.ssh, *(["-F", t.ssh_config] if t.ssh_config else []),
                "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes", "-o", "ConnectTimeout=8",
                "-o", "ServerAliveInterval=5", "-o", "ServerAliveCountMax=3",
                "-p", str(t.port), "--", f"{t.user}@{t.host}", command]

    def run(self, command: str, data: bytes | None = None, timeout: float = 20):
        try:
            return subprocess.run(self.argv(command), input=data, capture_output=True,
                                  timeout=timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise GatewayError("SSH недоступен или время ожидания истекло") from error

    # ---- volume ----------------------------------------------------------------------------
    def volume(self, percent: int | None = None) -> int:
        with self.volume_lock:
            result = self.run(volume_script(percent), timeout=30)
            if result.returncode != 0:
                raise GatewayError("Не удалось обратиться к громкости колонки")
            return parse_volume(result.stdout.decode("utf-8", "replace"))

    # ---- playback jobs ---------------------------------------------------------------------
    def submit(self, wav: bytes, key: str | None) -> Job:
        duration = validate_wav(wav)
        with self.lock:
            if key and key in self.keys and self.keys[key] in self.jobs:
                return self.jobs[self.keys[key]]
            if self.pending.qsize() >= MAX_QUEUE:
                raise GatewayError("Слишком много заданий в очереди")
            job = Job(str(uuid.uuid4()), duration, wav)
            self.jobs[job.id] = job
            if key:
                self.keys[key] = job.id
            for old in [j for j in self.jobs.values() if j.state not in {"queued", "playing"}][:-KEEP_JOBS]:
                self.jobs.pop(old.id, None)
            self.pending.put(job)
            return job

    def cancel(self, job_id: str) -> Job | None:
        job = self.jobs.get(job_id)
        if job and job.state in {"queued", "playing"}:
            job.cancel.set()
        return job

    def _worker(self) -> None:
        while True:
            job = self.pending.get()
            try:
                self._play(job)
            except Exception:  # noqa: BLE001 - the worker must survive any single job
                job.state, job.error = "failed", "Внутренняя ошибка воспроизведения"
            finally:
                job.wav = b""
                self._cleanup(job)

    def _play(self, job: Job) -> None:
        if job.cancel.is_set():
            job.state = "cancelled"
            return
        job.state = "playing"
        directory = play_directory(job.id)
        proc = subprocess.Popen(self.argv(play_script(directory, self.jar_b64)), stdin=subprocess.PIPE,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        deadline = time.monotonic() + job.duration + 40
        payload: bytes | None = job.wav
        cancel_sent = 0.0
        killed_at = 0.0
        out = err = b""
        while True:
            try:
                out, err = proc.communicate(payload, timeout=1)
                break
            except subprocess.TimeoutExpired:
                payload = None
            except (BrokenPipeError, OSError):
                out, err = b"", b""
                proc.kill()
                proc.wait()
                break
            now = time.monotonic()
            if job.cancel.is_set():
                if not cancel_sent or (now - cancel_sent > 1.5 and not killed_at):
                    cancel_sent = now
                    try:
                        self.run(stop_script(directory), timeout=10)
                    except GatewayError:
                        pass
                if now - cancel_sent > 6 and not killed_at:
                    killed_at = now
                    proc.kill()
            if now > deadline and not killed_at:
                killed_at = now
                proc.kill()
            if killed_at and now - killed_at > 5:
                out, err = proc.communicate()
                break
        text = out.decode("utf-8", "replace")
        errors = err.decode("utf-8", "replace")
        if "MAX_PLAY_CANCELLED" in text or job.cancel.is_set():
            job.state = "cancelled"
        elif "MAX_PLAY_RESULT" in text and proc.returncode == 0:
            job.state = "succeeded"
        else:
            job.state = "failed"
            line = next((x for x in (text + errors).splitlines() if x.startswith("MAX_PLAY_ERROR")), "")
            job.error = (line or "Воспроизведение не завершилось успешно")[:200]

    def _cleanup(self, job: Job) -> None:
        directory = play_directory(job.id)
        try:
            result = self.run(cleanup_script(directory), timeout=20)
            ok = result.returncode == 0 and b"MAX_CLEAN_OK" in result.stdout
        except GatewayError:
            ok = False
        job.cleanup = "complete" if ok else "failed"


# ---- HTTP ----------------------------------------------------------------------------------
_JOB = re.compile(r"/api/audio/jobs/([0-9a-fA-F-]{36})(/cancel)?")


def make_handler(station: MaxStation, port: int):
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    class Handler(BaseHTTPRequestHandler):
        server_version = "MaxGateway"
        protocol_version = "HTTP/1.1"

        def log_message(self, *_args):  # request lines can carry job ids only; keep stdout quiet
            pass

        def reply(self, status: int, body=None):
            data = b"" if body is None else json.dumps(body).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def guard(self) -> bool:
            if self.headers.get("Host", "") not in allowed_hosts:
                self.reply(403, {"error": "forbidden"})
                return False
            return True

        def handle_one(self, method: str):
            if not self.guard():
                return
            try:
                self.route(method)
            except GatewayError as error:
                self.reply(400, {"error": str(error)})
            except Exception:  # noqa: BLE001
                self.reply(500, {"error": "internal"})

        def body(self, limit: int) -> bytes:
            length = self.headers.get("Content-Length", "")
            if not length.isdigit() or int(length) > limit:
                raise GatewayError("Некорректный размер тела запроса")
            return self.rfile.read(int(length))

        def route(self, method: str):
            path = self.path.split("?", 1)[0]
            if method == "GET" and path == "/api/device":
                return self.reply(200, {"model": MODEL, "architecture": "aarch64", "features": FEATURES,
                                        "source": "max-gateway (experimental)",
                                        "led": {"ring_count": 0, "has_logo": False, "logo_count": 0},
                                        "room": None})
            if path == "/api/volume":
                if method == "GET":
                    return self.reply(200, {"percent": station.volume()})
                try:
                    percent = json.loads(self.body(1024))["percent"]
                except (ValueError, KeyError, TypeError) as error:
                    raise GatewayError("Ожидается JSON {\"percent\": 0..100}") from error
                if type(percent) is not int or not 0 <= percent <= 100:
                    raise GatewayError("Громкость: целое число 0–100")
                return self.reply(200, {"percent": station.volume(percent)})
            if path == "/api/audio/jobs" and method == "POST":
                job = station.submit(self.body(MAX_WAV), self.headers.get("Idempotency-Key"))
                return self.reply(202, job.public())
            if path == "/api/audio/jobs" and method == "GET":
                return self.reply(200, [j.public() for j in list(station.jobs.values())])
            if path == "/api/audio/test" and method == "POST":
                return self.reply(202, station.submit(test_tone(), None).public())
            match = _JOB.fullmatch(path)
            if match:
                job_id = str(uuid.UUID(match.group(1)))
                if method == "GET" and not match.group(2):
                    job = station.jobs.get(job_id)
                elif method == "POST" and match.group(2):
                    job = station.cancel(job_id)
                else:
                    return self.reply(405, {"error": "method"})
                return self.reply(200, job.public()) if job else self.reply(404, {"error": "not found"})
            return self.reply(404, {"error": "not found"})

        def do_GET(self):
            self.handle_one("GET")

        def do_POST(self):
            self.handle_one("POST")

    return Handler


def serve(target: MaxSshTarget, listen_port: int, ssh: str = "ssh") -> None:
    probe_max_ssh(target, ssh)  # fail closed: root SSH and Max framebuffer geometry must match
    station = MaxStation(target, ssh)
    server = ThreadingHTTPServer(("127.0.0.1", listen_port), make_handler(station, listen_port))
    print(f"Max gateway готов: http://127.0.0.1:{listen_port}/api  (model={MODEL}). Остановка: Ctrl+C.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")
    parser = argparse.ArgumentParser(description="Экспериментальный LUNA-совместимый шлюз для Станции Макс")
    parser.add_argument("--host", required=True, help="IP-адрес колонки")
    parser.add_argument("--user", required=True, help="пользователь существующего root SSH")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--ssh-config")
    parser.add_argument("--listen-port", type=int, default=18300)
    args = parser.parse_args()
    if not 1024 <= args.listen_port <= 65535:
        parser.error("--listen-port: 1024–65535")
    try:
        serve(MaxSshTarget(args.host, args.user, args.port, args.ssh_config), args.listen_port)
    except ProvisionError as error:
        print(str(error))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
