"""Bounded local conversion and synthesis; the station is driven only through LUNA."""
from __future__ import annotations

import array
import asyncio
import io
import math
import shutil
import struct
import sys
import wave

from .errors import InvalidInput, Unavailable

MAX_INPUT = 20 * 1024 * 1024
MAX_WAV = 60 * 1024 * 1024
THEMES = {"yandex": (660, 880), "windows": (523, 659, 784), "cyberpunk": (220, 440, 330),
          "portal": (880, 660, 440), "mario": (659, 659, 523, 659, 784)}


def apply_volume(data: bytes, percent: int) -> bytes:
    """Scale a PCM16 WAV before a backend which bypasses logical volume."""
    if type(percent) is not int or not 0 <= percent <= 100:
        raise InvalidInput("Некорректное значение громкости станции")
    try:
        with wave.open(io.BytesIO(data), 'rb') as source:
            params = source.getparams()
            if params.sampwidth != 2 or params.comptype != 'NONE':
                raise ValueError('PCM16 required')
            pcm = source.readframes(params.nframes)
            if len(pcm) != params.nframes * params.nchannels * 2:
                raise ValueError('incomplete PCM')
        samples = array.array('h')
        samples.frombytes(pcm)
        if sys.byteorder != 'little':
            samples.byteswap()
        for i, sample in enumerate(samples):
            samples[i] = int(sample * percent / 100)
        if sys.byteorder != 'little':
            samples.byteswap()
        output = io.BytesIO()
        with wave.open(output, 'wb') as result:
            result.setparams(params)
            result.writeframes(samples.tobytes())
        return output.getvalue()
    except (wave.Error, EOFError, ValueError) as error:
        raise InvalidInput('Невозможно безопасно применить громкость к WAV') from error


async def process(argv: list[str], data: bytes, *, limit: int, timeout: float) -> bytes:
    if not shutil.which(argv[0]):
        raise Unavailable(f"На хосте не установлен {argv[0]}")
    child = await asyncio.create_subprocess_exec(*argv, stdin=asyncio.subprocess.PIPE,
                                                 stdout=asyncio.subprocess.PIPE,
                                                 stderr=asyncio.subprocess.DEVNULL)

    async def communicate() -> bytes:
        assert child.stdin and child.stdout

        async def feed() -> None:
            try:
                child.stdin.write(data)
                await child.stdin.drain()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                child.stdin.close()

        task = asyncio.create_task(feed())
        try:
            output = bytearray()
            while chunk := await child.stdout.read(65536):
                if len(output) + len(chunk) > limit:
                    raise InvalidInput("Результат превышает допустимый размер")
                output.extend(chunk)
            await task
            if await child.wait() != 0:
                raise InvalidInput("Не удалось обработать файл или текст")
            return bytes(output)
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
    try:
        return await asyncio.wait_for(communicate(), timeout)
    finally:
        if child.returncode is None:
            child.kill()
            await child.wait()


def normalize_wav(data: bytes) -> bytes:
    # ffmpeg writes an unknown RIFF/data length to a pipe. Rebuild a finite container.
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise InvalidInput("Конвертер не вернул WAV")
    offset, pcm = 12, None
    while offset + 8 <= len(data):
        size = int.from_bytes(data[offset + 4:offset + 8], "little")
        if data[offset:offset + 4] == b"data":
            pcm = data[offset + 8:offset + 8 + size]
            break
        offset += 8 + size + (size & 1)
    if not pcm or len(pcm) % 2:
        raise InvalidInput("Пустой или неполный звук")
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setparams((1, 2, 48000, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)
    return output.getvalue()


async def convert(data: bytes) -> bytes:
    if not data or len(data) > MAX_INPUT:
        raise InvalidInput("Аудиофайл должен быть не больше 20 МиБ")
    result = await process(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                            "-protocol_whitelist", "pipe", "-i", "pipe:0", "-map", "0:a:0",
                            "-vn", "-t", "600", "-ac", "1", "-ar", "48000", "-c:a", "pcm_s16le",
                            "-f", "wav", "pipe:1"], data, limit=MAX_WAV, timeout=90)
    return normalize_wav(result)


async def tts(text: str) -> bytes:
    if not text.strip() or len(text) > 1500 or "\x00" in text:
        raise InvalidInput("Текст: 1–1500 символов")
    result = await process(["espeak-ng", "--stdout", "-v", "ru", "--stdin"],
                           text.encode(), limit=MAX_INPUT, timeout=30)
    return await convert(result)


def effect(name: str, seconds: int = 3) -> bytes:
    if name not in {*THEMES, "siren", "ban", "ringtone", "alarm"} or not 1 <= seconds <= 30:
        raise InvalidInput("Неизвестная тема/эффект или длительность вне 1–30 секунд")
    notes = THEMES.get(name, (440, 660) if name == "ringtone" else (880, 440))
    rate = 48000
    pcm = bytearray()
    for i in range(seconds * rate):
        t = i / rate
        frequency = (700 + 400 * math.sin(t * 8)) if name == "siren" else notes[int(t * 5) % len(notes)]
        envelope = min(1, (t % .2) * 30) * min(1, (.2 - t % .2) * 30)
        pcm.extend(struct.pack("<h", int(4500 * envelope * math.sin(2 * math.pi * frequency * t))))
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setparams((1, 2, rate, 0, "NONE", "not compressed"))
        wav.writeframes(pcm)
    return output.getvalue()
