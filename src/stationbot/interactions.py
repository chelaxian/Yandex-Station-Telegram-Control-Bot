"""Opt-in, bounded intercom and host-camera monitoring. No background recording on startup."""
from __future__ import annotations

import asyncio
import colorsys
import logging
import time
import uuid
from dataclasses import dataclass

from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message

from . import audio
from .errors import BotError, InvalidInput, Unavailable
from .presentation import card, safe

logger = logging.getLogger(__name__)
ACCEPT = {"прими", "ответь", "возьми трубку", "слушаю", "алло", "да"}
DECLINE = {"отклони", "отбой", "сбрось", "не сейчас"}


async def notify(message, station, text):
    title = "📞 Интерком" if "интерком" in text.lower() else "🎧 Воспроизведение" if "воспроизвед" in text.lower() or "звука" in text.lower() else "📣 Уведомление"
    await message.answer(card(title, [safe(text, 2000)]), parse_mode="HTML", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="home")],
        [InlineKeyboardButton(text="📞 Интерком", callback_data=f"guide:{station}:call")],
    ]))


@dataclass
class Session:
    user: int
    chat: int
    task: asyncio.Task | None = None
    active: bool = False
    end_requested: bool = False


class Interactions:
    def __init__(self, service):
        self.service = service
        self.calls: dict[str, Session] = {}
        self.guards: dict[str, Session] = {}
        self.lights: dict[str, Session] = {}
        self.themes: dict[str, Session] = {}
        self.audio_watchers: set[asyncio.Task] = set()

    async def close(self) -> None:
        tasks = [s.task for s in [*self.calls.values(), *self.guards.values(), *self.lights.values(), *self.themes.values()] if s.task] + list(self.audio_watchers)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.calls.clear()
        self.guards.clear()
        self.lights.clear()
        self.themes.clear()

    async def configure_theme(self, user: int, station: str) -> None:
        await self.service.store.require(user, "operator")
        client = self.service.clients[station]
        old = self.themes.get(station)
        if old and old.task:
            old.task.cancel()
            await asyncio.gather(old.task, return_exceptions=True)
            self.themes.pop(station, None)
        settings = await self.service.features.theme_settings(client)
        if settings["theme"] == "off":
            return
        (await client.device()).require("owner.speech.phase.v1")
        settings["user"] = user
        import json
        await asyncio.to_thread(self.service.features.assets.put, "settings", f"theme-{station}.json", json.dumps(settings).encode(), replace=True)
        session = Session(user, user)
        self.themes[station] = session
        session.task = asyncio.create_task(self._theme(station, session), name=f"theme-{station}")

    async def restore_themes(self) -> None:
        for station, client in self.service.clients.items():
            settings = await self.service.features.theme_settings(client)
            user = settings.get("user")
            if type(user) is int and settings["theme"] != "off":
                try:
                    await self.configure_theme(user, station)
                except BotError as e:
                    logger.warning("theme_not_restored type=%s", type(e).__name__)

    async def _theme(self, station: str, session: Session) -> None:
        client, previous, failures = self.service.clients[station], None, 0
        try:
            while True:
                await self.service.store.require(session.user, "operator")
                try:
                    event = await client.owner("GET", "phase", request_timeout=3)
                    phase = event.get("phase")
                    settings = await self.service.features.theme_settings(client)
                    if phase in {"listening", "speaking"} and phase != previous and previous is not None and event.get("initial_snapshot") is False:
                        kind = "ask" if phase == "listening" else "reply"
                        if settings[kind] and station not in self.calls:
                            async with client.operation_lock:
                                await self.service.store.require(session.user, "operator")
                                if not any(j["state"] in {"queued", "playing"} for j in await client.audio_jobs()):
                                    await self.service.features.theme_sound(client, kind)
                    if phase not in {"unknown", "recognition", None}:
                        previous = phase
                    failures = 0
                except BotError:
                    failures += 1
                    if failures >= 3:
                        raise
                await asyncio.sleep(.25)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("theme_stopped type=%s", type(e).__name__)
        finally:
            self.themes.pop(station, None)

    def watch_audio(self, message: Message, station: str, job: str) -> None:
        task = asyncio.create_task(self._watch_audio(message, station, job), name=f"audio-{job}")
        self.audio_watchers.add(task)
        task.add_done_callback(self.audio_watchers.discard)

    async def _watch_audio(self, message: Message, station: str, job: str) -> None:
        client = self.service.clients[station]
        try:
            for _ in range(620):
                await asyncio.sleep(1)
                result = await client.audio_status(job)
                if result["state"] not in {"queued", "playing"}:
                    labels = {"succeeded": "Воспроизведение завершено", "cancelled": "Воспроизведение остановлено", "failed": "Ошибка воспроизведения", "interrupted": "Воспроизведение прервано перезапуском LUNA"}
                    await notify(message, station, labels[result["state"]] + ("; временный файл удалён" if result["cleanup"] == "complete" else "; очистка файла не подтверждена"))
                    return
            await notify(message, station, "Результат воспроизведения не подтверждён; /audio_jobs")
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("audio_result_unknown type=%s", type(e).__name__)
            try:
                await notify(message, station, "Связь потеряна: результат звука неизвестен. /audio_jobs")
            except Exception:
                pass

    async def command(self, message: Message, user: int, station: str, command: str, args: list[str]) -> None:
        await self.service.store.require(user, "operator")
        client = self.service.clients[station]
        if command == "led_effect":
            if len(args) != 1 or args[0] not in {"rainbow", "pulse", "police", "off"}:
                raise InvalidInput("/led_effect rainbow|pulse|police|off — до 10 минут")
            old = self.lights.get(station)
            if old and old.task:
                if old.user != user:
                    await self.service.store.require(user, "owner")
                old.task.cancel()
                await asyncio.gather(old.task, return_exceptions=True)
            if args[0] != "off":
                session = Session(user, message.chat.id)
                self.lights[station] = session
                session.task = asyncio.create_task(self._light(station, session, args[0]), name=f"led-{station}")
            else:
                await client.led("ring", None)
            await notify(message, station, "Эффект подсветки обновлён")
        elif command == "call":
            if station in self.calls:
                raise InvalidInput("На этой станции уже есть интерком")
            device = await client.device()
            device.require("audio.jobs.v1")
            device.require("microphone.capture")
            await client.play(await asyncio.to_thread(audio.effect, "ringtone", 3), uuid.uuid4().hex)
            session = Session(user, message.chat.id)
            self.calls[station] = session
            session.task = asyncio.create_task(self._intercom(message, station, session), name=f"intercom-{station}")
            await notify(message, station, "📞 Интерком: ожидание ответа 60 секунд. /answer или «Алиса, ответь». /hangup — завершить. Запись начнётся после приёма.")
        elif command in {"answer", "hangup"}:
            session = self.calls.get(station)
            if not session:
                raise InvalidInput("На станции нет интеркома")
            if session.user != user:
                await self.service.store.require(user, "owner")
            if command == "answer":
                session.active = True
                await notify(message, station, "Интерком принят; запись комнаты активна. /hangup — завершить")
            elif session.task:
                session.task.cancel()
                await asyncio.gather(session.task, return_exceptions=True)
                self.calls.pop(station, None)
                await client.stop_audio()
                await notify(message, station, "Интерком завершён")
        elif command == "guard":
            if args not in [["on"], ["off"]]:
                raise InvalidInput("/guard on|off")
            if args == ["off"]:
                session = self.guards.get(station)
                if session and session.task:
                    if session.user != user:
                        await self.service.store.require(user, "owner")
                    session.task.cancel()
                    await asyncio.gather(session.task, return_exceptions=True)
                    self.guards.pop(station, None)
                await notify(message, station, "Охрана выключена")
                return
            if not client.config.camera_input:
                raise Unavailable("Не настроена camera_input — камера хоста")
            if station in self.guards:
                raise InvalidInput("Охрана уже включена")
            session = Session(user, message.chat.id)
            self.guards[station] = session
            session.task = asyncio.create_task(self._guard(message, station, session), name=f"camera-{station}")
            await notify(message, station, "Охрана включена: анализ камеры хоста, снимок при изменениях. /guard off. После перезапуска остаётся выключенной.")

    async def _intercom(self, message: Message, station: str, session: Session) -> None:
        client = self.service.clients[station]
        voice_task = None
        try:
            deadline = time.monotonic() + 60
            while not session.active and time.monotonic() < deadline:
                await self.service.store.require(session.user, "operator")
                try:
                    event = await client.json("GET", "alice/command", params={"timeout_ms": 1000}, request_timeout=3)
                    text = event.get("transcript", "").lower().strip().removeprefix("алиса").strip(" ,.!?")
                    if text in DECLINE:
                        await notify(message, station, "На станции отклонили интерком")
                        return
                    if text in ACCEPT:
                        session.active = True
                except BotError:
                    await asyncio.sleep(.5)
            if not session.active:
                await notify(message, station, "Нет ответа: интерком завершён")
                return
            await client.stop_audio()
            voice_task = asyncio.create_task(self._voice_hangup(client, session), name=f"voice-hangup-{station}")
            await notify(message, station, "🎙 Интерком активен: фрагменты по 5 секунд; голосовые и /tts — на станцию. /hangup")
            deadline = time.monotonic() + 1800
            while time.monotonic() < deadline and not session.end_requested:
                await self.service.store.require(session.user, "operator")
                # Let explicit actions enter between chunks; do not hold a global device lock.
                async with client.operation_lock:
                    await self.service.store.require(session.user, "operator")
                    # Avoid sending the caller their own played voice as room feedback.
                    playing = any(j["state"] in {"queued", "playing"} for j in await client.audio_jobs())
                    wav = None if playing else await client.record(5)
                if wav is None:
                    await asyncio.sleep(.5)
                    continue
                await message.answer_audio(BufferedInputFile(wav, filename="intercom.wav"), caption="Интерком · " + client.config.label)
                del wav
                await asyncio.sleep(.5)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("intercom_stopped type=%s", type(e).__name__)
            await notify(message, station, "Интерком остановлен: связь или доступ недоступны")
        finally:
            if voice_task:
                voice_task.cancel()
                await asyncio.gather(voice_task, return_exceptions=True)
            self.calls.pop(station, None)
            try:
                await client.stop_audio()
            except BotError:
                pass

    async def _voice_hangup(self, client, session: Session) -> None:
        while not session.end_requested:
            await self.service.store.require(session.user, "operator")
            try:
                event = await client.json("GET", "alice/command", params={"timeout_ms": 1000}, request_timeout=3)
                text = event.get("transcript", "").lower().strip().removeprefix("алиса").strip(" ,.!?")
                if text in DECLINE:
                    session.end_requested = True
            except BotError:
                await asyncio.sleep(.5)

    async def _light(self, station: str, session: Session, name: str) -> None:
        client = self.service.clients[station]
        started = time.monotonic()
        try:
            while (elapsed := time.monotonic() - started) < 600:
                await self.service.store.require(session.user, "operator")
                if name == "rainbow":
                    rgb = colorsys.hsv_to_rgb((elapsed / 6) % 1, 1, .25)
                elif name == "police":
                    rgb = (.25, 0, 0) if int(elapsed * 2) % 2 else (0, 0, .25)
                else:
                    import math
                    rgb = (0, 0, .04 + .2 * (1 + math.sin(elapsed * 3)) / 2)
                async with client.operation_lock:
                    await client.led("ring", "#" + "".join(f"{int(v * 255):02x}" for v in rgb))
                await asyncio.sleep(.5)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("led_effect_stopped type=%s", type(e).__name__)
        finally:
            self.lights.pop(station, None)
            try:
                await client.led("ring", None)
            except BotError:
                pass

    async def _guard(self, message: Message, station: str, session: Session) -> None:
        client = self.service.clients[station]
        previous, last_alert, streak = None, 0.0, 0
        try:
            while True:
                await self.service.store.require(session.user, "operator")
                raw = await audio.process(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", client.config.camera_input,
                                           "-frames:v", "1", "-vf", "scale=64:48,format=gray", "-f", "rawvideo", "pipe:1"], b"", limit=3072, timeout=15)
                if len(raw) != 3072:
                    raise Unavailable("Камера вернула неполный кадр")
                changed = previous is not None and sum(abs(a-b) for a, b in zip(raw, previous, strict=True)) / len(raw) > 12
                streak = streak + 1 if changed else 0
                previous = raw
                if streak >= 2 and time.monotonic() - last_alert > 30:
                    await self.service.store.require(session.user, "operator")
                    frame = await self.service.features.execute(client, "photo", [])
                    await message.answer_photo(BufferedInputFile(frame, filename="motion.jpg"), caption="⚠️ Изменение изображения камеры хоста · " + client.config.label)
                    last_alert = time.monotonic()
                await asyncio.sleep(2)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("guard_stopped type=%s", type(e).__name__)
            await notify(message, station, "Охрана остановлена: камера, связь или доступ недоступны")
        finally:
            self.guards.pop(station, None)
