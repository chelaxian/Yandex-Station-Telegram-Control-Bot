"""HTTP adapter for the pinned LUNA contract. No shell, sysfs or model aliases."""
from __future__ import annotations

import asyncio
import io
import os
import re
import uuid
import wave
from dataclasses import dataclass
from typing import Any

import httpx

from .config import StationConfig
from .errors import InvalidInput, TransportError, Unavailable

CONTRACT_COMMIT = "0f2393e4d613472c79755b358abc3047a9466963"
MAX_JSON = 1024 * 1024
MAX_RECORDING = 12 * 1024 * 1024


@dataclass(frozen=True)
class Device:
    model: str
    architecture: str
    features: frozenset[str]
    ring_count: int
    logo_count: int

    @classmethod
    def parse(cls, raw: Any) -> Device:
        try:
            if not isinstance(raw, dict) or not isinstance(raw["features"], list):
                raise ValueError
            if not all(isinstance(s, str) for s in raw["features"]):
                raise ValueError
            model, architecture = raw["model"], raw["architecture"]
            if not isinstance(model, str) or not isinstance(architecture, str):
                raise ValueError
            topology = raw.get("led", {})
            ring, logo = int(topology.get("ring_count", 0)), int(topology.get("logo_count", 0))
            if not 0 <= ring <= 256 or not 0 <= logo <= 256:
                raise ValueError
            return cls(model, architecture, frozenset(raw["features"]), ring, logo)
        except (KeyError, TypeError, ValueError, AttributeError) as e:
            raise TransportError("Ответ /device не соответствует контракту LUNA") from e

    def require(self, feature: str) -> None:
        if feature not in self.features:
            raise Unavailable(f"Станция не объявляет возможность {feature}")


class Luna:
    def __init__(self, config: StationConfig, *, transport: httpx.AsyncBaseTransport | None = None):
        self.config = config
        token = os.environ.get(config.token_env, "") if config.token_env else ""
        if config.token_env and not token:
            raise InvalidInput("Не задан токен аутентифицирующего proxy")
        self.http = httpx.AsyncClient(
            base_url=config.url.rstrip("/") + "/",
            timeout=httpx.Timeout(10, connect=3),
            limits=httpx.Limits(max_connections=4, max_keepalive_connections=2),
            follow_redirects=False,
            trust_env=False,
            transport=transport,
            headers={"Authorization": f"Bearer {token}"} if token else {},
        )
        self.operation_lock = asyncio.Lock()

    async def close(self) -> None:
        await self.http.aclose()

    async def request(self, method: str, path: str, *, request_timeout: float = 10,
                      limit: int = MAX_JSON, **kwargs: Any) -> httpx.Response:
        # Retrying recording, playback or mutating requests can repeat a physical action.
        attempts = 2 if method == "GET" and path in {"device", "clock", "sensors", "volume", "plugins", "media", "microphone/devices"} else 1
        for attempt in range(attempts):
            try:
                async with self.http.stream(method, path, timeout=request_timeout, **kwargs) as response:
                    length = response.headers.get("content-length")
                    if length is not None and (not length.isdigit() or int(length) > limit):
                        raise TransportError("Ответ LUNA превышает допустимый размер")
                    parts = bytearray()
                    async for chunk in response.aiter_bytes():
                        if len(parts) + len(chunk) > limit:
                            raise TransportError("Ответ LUNA превышает допустимый размер")
                        parts.extend(chunk)
                    if response.status_code >= 500 and attempt + 1 < attempts:
                        await asyncio.sleep(0.15)
                        continue
                    if response.status_code >= 400:
                        # Raw upstream bodies may contain filesystem paths or private metadata.
                        raise Unavailable(f"LUNA отклонила операцию (HTTP {response.status_code})")
                    if response.status_code not in {200, 201, 202, 204}:
                        raise TransportError("Неожиданный статус LUNA; перенаправления запрещены")
                    return httpx.Response(response.status_code, headers=response.headers,
                                          content=bytes(parts), request=response.request)
            except (httpx.TimeoutException, httpx.NetworkError, httpx.ProtocolError) as e:
                if attempt + 1 == attempts:
                    raise TransportError("Нет ответа LUNA; проверьте runtime и защищённый туннель") from e
                await asyncio.sleep(0.15)
        raise TransportError("Нет ответа LUNA")

    async def json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self.request(method, path, **kwargs)
        if response.status_code == 204 or not response.content:
            return None
        try:
            return response.json()
        except ValueError as e:
            raise TransportError("LUNA вернула некорректный JSON") from e

    async def device(self) -> Device:
        device = Device.parse(await self.json("GET", "device"))
        if device.model != self.config.expected_model:
            raise Unavailable("Модель LUNA не совпадает с expected_model; управление заблокировано")
        return device

    async def volume(self, percent: int | None = None) -> dict:
        d = await self.device()
        d.require("audio.volume.alsa")
        if percent is None:
            result = await self.json("GET", "volume")
        else:
            if type(percent) is not int or not 0 <= percent <= 100:
                raise InvalidInput("Громкость: целое число 0–100")
            result = await self.json("POST", "volume", json={"percent": percent})
        if not isinstance(result, dict) or type(result.get("percent")) is not int:
            raise TransportError("Некорректный ответ громкости")
        return result

    async def led(self, zone: str, color: str | None) -> Any:
        if zone not in {"ring", "logo"}:
            raise InvalidInput("Зона: ring или logo")
        d = await self.device()
        d.require("led.ring.rgb" if zone == "ring" else "led.logo")
        if (d.ring_count if zone == "ring" else d.logo_count) == 0:
            raise Unavailable("Эта LED-зона отсутствует")
        if color is None:
            return await self.json("POST", f"led/off/{zone}")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", color):
            raise InvalidInput("Цвет в формате #RRGGBB")
        return await self.json("POST", f"led/{zone}", json={"colors": [color]})

    async def clock(self, value: str | None = None) -> Any:
        await self.device()
        status = await self.json("GET", "clock")
        if not isinstance(status, dict) or status.get("available") is not True:
            raise Unavailable("У этой станции нет доступных часов")
        if value is None:
            return status
        if value == "off":
            return await self.json("POST", "clock/off")
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise InvalidInput("Время в формате ЧЧ:ММ, либо off")
        return await self.json("POST", "clock", json={"time": value, "brightness": 100})

    async def screen(self, text: str, brightness: int = 100) -> Any:
        from .display import segment_frame
        if type(brightness) is not int or not 0 <= brightness <= 255:
            raise InvalidInput("Яркость: 0–255")
        status = await self.clock()
        if status.get("text_available") is True:
            if not 1 <= len(text) <= 64:
                raise InvalidInput("Текст экрана: 1–64 символа")
            return await self.json("POST", "clock/text", json={"text": text, "brightness": brightness})
        frame = segment_frame(text, brightness, status.get("segments", []))
        return await self.json("POST", "clock", json={"segments": frame})

    async def sensors(self) -> Any:
        await self.device()
        result = await self.json("GET", "sensors")
        if not isinstance(result, list):
            raise TransportError("Некорректный список датчиков")
        return result

    async def microphone_devices(self) -> Any:
        (await self.device()).require("microphone.capture")
        result = await self.json("GET", "microphone/devices")
        if not isinstance(result, list):
            raise TransportError("Некорректный список микрофонов")
        return result

    async def record(self, seconds: int, device: str | None = None) -> bytes:
        if type(seconds) is not int or not 1 <= seconds <= 30:
            raise InvalidInput("Длительность записи: 1–30 секунд")
        devices = await self.microphone_devices()
        ids = {item.get("id") for item in devices if isinstance(item, dict)}
        if not ids or (device is not None and device not in ids):
            raise Unavailable("Микрофон отсутствует в актуальном списке LUNA")
        payload: dict[str, Any] = {"seconds": seconds}
        if device is not None:
            payload["device"] = device
        r = await self.request("POST", "microphone/record", json=payload,
                               request_timeout=seconds + 15, limit=MAX_RECORDING)
        try:
            with wave.open(io.BytesIO(r.content), "rb") as wav:
                if wav.getnframes() < 1 or wav.getnchannels() not in {1, 2}:
                    raise ValueError
                if wav.getnframes() / wav.getframerate() > seconds + 2:
                    raise ValueError
                expected = wav.getnframes() * wav.getnchannels() * wav.getsampwidth()
                if len(wav.readframes(wav.getnframes())) != expected:
                    raise ValueError
        except (wave.Error, EOFError, ValueError, ZeroDivisionError) as e:
            raise TransportError("LUNA вернула некорректный WAV") from e
        return r.content

    async def audio_test(self) -> Any:
        d = await self.device()
        if not d.features.intersection({"audio.play.aplay", "audio.play.mediad"}):
            raise Unavailable("LUNA не объявляет аудиовыход")
        return await self.json("POST", "audio/test", request_timeout=20)

    async def play(self, wav: bytes, key: str) -> dict:
        device = await self.device()
        device.require("audio.jobs.v1")
        if not 44 <= len(wav) <= 64 * 1024 * 1024:
            raise InvalidInput("Аудио: WAV до 64 МиБ")
        if device.model == "yandexplum":
            from .audio import apply_volume
            volume = await self.volume()
            if volume["percent"] == 0:
                raise Unavailable("Громкость станции 0% — воспроизведение отключено")
            playback_volume = volume["percent"]
            wav = await asyncio.to_thread(apply_volume, wav, playback_volume)
        result = await self.json("POST", "audio/jobs", content=wav,
                               headers={"Content-Type": "audio/wav", "Idempotency-Key": key},
                               request_timeout=60)
        job = self.audio_job(result)
        if device.model == "yandexplum":
            job["station_volume_percent"] = volume["percent"]
            job["playback_volume_percent"] = playback_volume
        return job

    @staticmethod
    def audio_job(value: Any) -> dict:
        try:
            uuid.UUID(value["id"])
            if value["state"] not in {"queued", "playing", "succeeded", "failed", "cancelled", "interrupted"}:
                raise ValueError
            if value["cleanup"] not in {"pending", "complete", "failed"}:
                raise ValueError
            return value
        except (ValueError, KeyError, TypeError, AttributeError) as e:
            raise TransportError("Некорректный результат аудиозадания") from e

    async def audio_status(self, job: str) -> dict:
        try:
            uuid.UUID(job)
        except ValueError as e:
            raise InvalidInput("Некорректный ID аудиозадания") from e
        return self.audio_job(await self.json("GET", f"audio/jobs/{job}"))

    async def audio_jobs(self) -> list[dict]:
        (await self.device()).require("audio.jobs.v1")
        result = await self.json("GET", "audio/jobs")
        if not isinstance(result, list):
            raise TransportError("Некорректный журнал воспроизведения")
        return [self.audio_job(item) for item in result]

    async def stop_audio(self) -> list[dict]:
        jobs = await self.audio_jobs()
        return [await self.json("POST", f"audio/jobs/{j['id']}/cancel")
                for j in jobs if j.get("state") in {"queued", "playing"}]

    async def owner(self, method: str, path: str, **kwargs: Any) -> Any:
        if not self.config.allow_owner_tools:
            raise Unavailable("Инструменты владельца выключены в настройках станции")
        (await self.device()).require("owner.tools.v1")
        return await self.json(method, f"owner/{path}", **kwargs)

    async def shell(self, command: str) -> Any:
        if not command or len(command) > 4096:
            raise InvalidInput("Команда терминала: 1–4096 символов")
        return await self.owner("POST", "execute", json={"command": command, "timeout": 15},
                                request_timeout=20)

    async def plugins(self) -> list[dict]:
        await self.device()
        result = await self.json("GET", "plugins")
        if not isinstance(result, list):
            raise TransportError("Некорректный список пакетов")
        return result

    async def invoke(self, plugin: str) -> dict:
        if not self.config.allow_packages:
            raise Unavailable("Запуск пакетов отключён владельцем в конфигурации")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", plugin):
            raise InvalidInput("Некорректное имя пакета")
        packages = await self.plugins()
        entry = next((p for p in packages if p.get("manifest", {}).get("id") == plugin), None)
        if not entry or entry.get("enabled") is not True or entry.get("compatible") is not True:
            raise Unavailable("Пакет отсутствует, выключен или несовместим")
        await self.json("POST", f"plugins/{plugin}/invoke", json={"args": []})
        return {"status": "accepted", "plugin": plugin}

    async def media(self, action: str | None = None) -> Any:
        await self.device()
        if action is None:
            return await self.json("GET", "media")
        if action not in {"pause", "resume", "next", "previous"}:
            raise InvalidInput("Команда плеера: pause, resume, next, previous")
        # 202 is deliberately returned as pending; not reported as completed playback.
        return {"status": "accepted", "operation": await self.json(
            "POST", "media/command", json={"action": action})}
