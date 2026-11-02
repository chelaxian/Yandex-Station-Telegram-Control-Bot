from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any

from . import audio
from .assets import Assets, filename
from .errors import InvalidInput, Unavailable
from .luna import Luna

GUIDES = {
    "soundboard": "/sounds — список\n/play имя.wav — воспроизвести\nОтправьте MP3/WAV с подписью /sound_add name.wav\n/sound_delete name.wav — удалить\n/stop — остановить",
    "tts": "/tts текст — произнести на выбранной станции\nГолосовое сообщение в чат также воспроизводится на станции.",
    "theme": "/theme yandex|windows|cyberpunk|portal|mario\n/theme off\nПредпрослушивание: /theme_test",
    "siren": "/siren 1–30 — сирена указанное число секунд\n/stop — остановить\n/ban — звуковой эффект",
    "backup": "/backup — ZIP настроек/звуков/скриптов\nОтправьте этот ZIP с подписью /restore\n/firmware — список образов; загрузка .img/.bin с подписью /firmware имя.bin\nОбраз сохраняется с SHA-256, как в 2.7; запись разделов не выполняется.",
    "terminal": "/shell команда — терминал станции (владелец)\n/upload_script name.sh — подпись к файлу\n/scripts — список\n/run_script name.sh — выполнить\n/script_delete name.sh — удалить",
    "camera": "/photo — фото камеры хоста\n/video 1–15 — короткое видео\n/guard on|off — детекция изменений изображения\nКамера выбирается владельцем в camera_input; камера на мини-ПК и камера колонки — разные устройства.",
    "call": "/call — начать интерком\n/answer — принять\n/hangup — завершить\nПри активном интеркоме звук комнаты отправляется фрагментами в чат, голосовые и /tts звучат на станции. Лимит 30 минут, как в 2.7. Это не Telegram VoIP.",
    "ask": "/ask текст — вопрос помощнику\n/dialogs — сохранённые диалоги этого бота\n/legacy_history — диалоги прежнего бота",
    "timer": "/timer секунды — таймер со звуком и уведомлением\n/alarm ЧЧ:ММ — ближайший будильник (часовой пояс хоста)\n/timers\n/cancel_timer ID",
    "system": "/system — CPU/RAM/uptime/RSSI\n/network — связь и задержка\n/cleanup — временные файлы бота\n/suggest текст — записать предложение",
}


class Features:
    def __init__(self, state, store):
        self.assets = Assets(state)
        self.store = store

    async def execute(self, client: Luna, action: str, args: list[str], payload: bytes | None = None) -> Any:
        key = uuid.uuid4().hex
        if action == "play_upload":
            if payload is None:
                raise InvalidInput("Нужно аудиовложение")
            return await client.play(await audio.convert(payload), key)
        if action == "sound_add":
            if payload is None or len(args) != 1:
                raise InvalidInput("Подпись к MP3/WAV: /sound_add name.wav")
            data = await audio.convert(payload)
            return await asyncio.to_thread(self.assets.put, "sounds", filename(args[0]), data)
        if action in {"sounds", "scripts", "firmware"} and payload is None:
            return await asyncio.to_thread(self.assets.inventory, {"sounds": "sounds", "scripts": "scripts", "firmware": "firmware"}[action])
        if action == "play":
            if len(args) != 1:
                raise InvalidInput("/play имя.wav")
            data = await asyncio.to_thread(self.assets.get, "sounds", args[0])
            if data[:4] != b"RIFF":
                data = await audio.convert(data)
            return await client.play(data, key)
        if action in {"sound_delete", "script_delete"}:
            if len(args) != 1:
                raise InvalidInput("Укажите имя файла")
            if action == "script_delete" and client.config.allow_owner_tools:
                entries = await client.owner("GET", "files")
                if any(i.get("kind") == "scripts" and i.get("name") == args[0] for i in entries):
                    await client.owner("DELETE", f"files/scripts/{filename(args[0])}")
            await asyncio.to_thread(self.assets.delete, "sounds" if action == "sound_delete" else "scripts", args[0])
            return "Файл удалён"
        if action == "tts":
            return await client.play(await audio.tts(" ".join(args)), key)
        if action in {"siren", "ban", "theme_test"}:
            if action == "theme_test":
                try:
                    name = json.loads(await asyncio.to_thread(self.assets.get, "settings", "theme.json"))["theme"]
                except (InvalidInput, KeyError, ValueError):
                    name = "yandex"
                if name == "off":
                    return "Звуковая тема выключена"
            else:
                name = action
            if action == "siren" and args and (len(args) != 1 or not args[0].isdigit()):
                raise InvalidInput("/siren 1–30")
            seconds = int(args[0]) if action == "siren" and args else 3
            return await client.play(await asyncio.to_thread(audio.effect, name, seconds), key)
        if action == "theme":
            if len(args) != 1 or args[0] not in {*audio.THEMES, "off"}:
                raise InvalidInput("/theme yandex|windows|cyberpunk|portal|mario|off")
            await asyncio.to_thread(self.assets.put, "settings", "theme.json", json.dumps({"theme": args[0]}).encode(), replace=True)
            return "Тема сохранена; /theme_test — прослушать"
        if action == "stop":
            return {"cancellation_requested": await client.stop_audio()}
        if action == "audio_jobs":
            return await client.audio_jobs()
        if action == "backup":
            for table, columns in [("dialogs", "station,question,answer,created"), ("suggestions", "user_id,text,created")]:
                rows = await self.store.rows(f"SELECT {columns} FROM {table} ORDER BY created DESC LIMIT 5000")
                await asyncio.to_thread(self.assets.put, "dialogs" if table == "dialogs" else "settings", table + ".json", json.dumps(rows, ensure_ascii=False).encode(), replace=True)
            return await asyncio.to_thread(self.assets.backup)
        if action == "restore":
            if payload is None:
                raise InvalidInput("Отправьте ZIP с подписью /restore")
            count = await asyncio.to_thread(self.assets.restore, payload)
            for table, kind, columns in [("dialogs", "dialogs", ("station", "question", "answer", "created")), ("suggestions", "settings", ("user_id", "text", "created"))]:
                try:
                    rows = json.loads(await asyncio.to_thread(self.assets.get, kind, table + ".json"))
                except InvalidInput:
                    continue
                if not isinstance(rows, list) or len(rows) > 5000:
                    raise InvalidInput("Некорректная история в архиве; прежние файлы сохранены для отката")
                for row in rows:
                    if not isinstance(row, dict) or set(row) != set(columns):
                        raise InvalidInput("Некорректная запись истории в архиве")
                    values = tuple(row[c] for c in columns)
                    names = ",".join(columns)
                    marks = ",".join("?" for _ in columns)
                    conditions = " AND ".join(f"{c}=?" for c in columns)
                    await self.store.write(f"INSERT INTO {table} ({names}) SELECT {marks} WHERE NOT EXISTS (SELECT 1 FROM {table} WHERE {conditions})", values + values)
            return f"Восстановлено файлов: {count}; прежние данные сохранены для отката"
        if action == "restore_legacy":
            if payload is None:
                raise InvalidInput("Отправьте ZIP 2.7 с подписью /restore_legacy")
            converted = await asyncio.to_thread(self.assets.import_legacy, payload)
            return await self.execute(client, "restore", [], converted)
        if action in {"firmware", "upload_script"}:
            if payload is None or len(args) != 1:
                raise InvalidInput("Отправьте файл с подписью /firmware имя.bin или /upload_script имя.sh")
            name = filename(args[0])
            kind = "firmware" if action == "firmware" else "scripts"
            if not name.endswith((".bin", ".img") if kind == "firmware" else (".sh",)):
                raise InvalidInput("Образ: .img/.bin; скрипт: .sh")
            if kind == "scripts":
                if len(payload) > 1024 * 1024 or b"\0" in payload:
                    raise InvalidInput("Скрипт: текстовый .sh до 1 МиБ")
                try:
                    payload.decode("utf-8")
                except UnicodeError as e:
                    raise InvalidInput("Скрипт должен быть в UTF-8") from e
            # Stage to the explicit LUNA owner directory first. Failure must not report upload success.
            result = await client.owner("POST", f"files/{kind}/{name}", content=payload, request_timeout=60)
            await asyncio.to_thread(self.assets.put, kind, name, payload)
            return result
        if action == "shell":
            return await client.shell(" ".join(args))
        if action == "run_script":
            if len(args) != 1:
                raise InvalidInput("/run_script name.sh")
            # Execution path is supplied by the typed owner contract, never a vendor path guess.
            source = (await asyncio.to_thread(self.assets.get, "scripts", filename(args[0]))).decode("utf-8")
            return await client.owner("POST", "scripts/run", json={"name": filename(args[0]), "source": source}, request_timeout=35)
        if action in {"system", "fastfetch"}:
            if not client.config.allow_owner_tools:
                return {"sensors": await client.sensors()}
            return await client.owner("GET", "system")
        if action == "network":
            import time
            start = time.monotonic()
            device = await client.device()
            return {"model": device.model, "luna_rtt_ms": round((time.monotonic() - start) * 1000), "reachable": True}
        if action == "discover":
            from .discovery import discover
            if len(args) != 1:
                raise InvalidInput("/discover IPv4-подсеть/24")
            return {"adb_candidates": await discover(args[0]), "verified_models": False,
                    "next": "Подключите LUNA через защищённый туннель; модель проверяется через /device"}
        if action == "cleanup":
            return await asyncio.to_thread(self.assets.cleanup)
        if action in {"photo", "video"}:
            source = client.config.camera_input
            if not source:
                raise Unavailable("Не настроена камера: задайте camera_input для этой станции")
            argv = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-i", source]
            if action == "photo":
                return await audio.process([*argv, "-frames:v", "1", "-vf", "scale=640:-2", "-f", "image2pipe", "-c:v", "mjpeg", "pipe:1"], b"", limit=4*1024*1024, timeout=20)
            if len(args) > 1 or (args and (not args[0].isdigit() or not 1 <= int(args[0]) <= 15)):
                raise InvalidInput("/video 1–15")
            return await audio.process([*argv, "-t", args[0] if args else "5", "-an", "-vf", "scale=640:-2", "-c:v", "libx264", "-preset", "ultrafast", "-movflags", "frag_keyframe+empty_moov", "-f", "mp4", "pipe:1"], b"", limit=20*1024*1024, timeout=35)
        if action == "custom":
            if not args:
                return await asyncio.to_thread(self.assets.inventory, "scripts")
            if len(args) != 1:
                raise InvalidInput("/custom name.sh — пользовательская функция-скрипт")
            return await self.execute(client, "run_script", args)
        if action == "custom_add":
            if len(args) < 2 or not filename(args[0]).endswith(".sh"):
                raise InvalidInput("/custom_add имя.sh команда")
            return await asyncio.to_thread(self.assets.put, "scripts", args[0], ("#!/bin/sh\n" + " ".join(args[1:]) + "\n").encode())
        return NotImplemented
