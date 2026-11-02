from __future__ import annotations

import asyncio
import re
import time
import uuid
from pathlib import Path

import aiosqlite

from .errors import Forbidden, InvalidInput

ROLES = {"viewer": 1, "operator": 2, "owner": 3}


class Store:
    """Single-writer SQLite, durable intent and audit without message/audio contents."""

    def __init__(self, path: Path, owner_id: int):
        self.path, self.owner_id = path, owner_id
        self.db: aiosqlite.Connection | None = None
        self.lock = asyncio.Lock()

    async def open(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = await aiosqlite.connect(self.path, isolation_level=None)
        self.db.row_factory = aiosqlite.Row
        await self.db.execute("PRAGMA journal_mode=WAL")
        await self.db.execute("PRAGMA busy_timeout=5000")
        await self.db.execute("PRAGMA foreign_keys=ON")
        async with self.db.execute("PRAGMA user_version") as c:
            version = (await c.fetchone())[0]
        if version > 1:
            raise InvalidInput("База создана более новой версией бота")
        await self.db.executescript("""
            CREATE TABLE IF NOT EXISTS members (
                user_id INTEGER PRIMARY KEY, role TEXT NOT NULL CHECK(role IN ('viewer','operator')));
            CREATE TABLE IF NOT EXISTS invites (
                username TEXT PRIMARY KEY, role TEXT NOT NULL, expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS claims (
                user_id INTEGER PRIMARY KEY, username TEXT NOT NULL, role TEXT NOT NULL,
                created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS selection (user_id INTEGER PRIMARY KEY, station TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS suggestions (user_id INTEGER NOT NULL, text TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS dialogs (station TEXT NOT NULL, question TEXT NOT NULL, answer TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS actions (
                request_id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, station TEXT NOT NULL,
                action TEXT NOT NULL, status TEXT NOT NULL, created REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS timers (
                id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
                station TEXT NOT NULL, due REAL NOT NULL, status TEXT NOT NULL);
            PRAGMA user_version=1;
        """)
        # A process crash after a physical action must never replay that action.
        await self.db.execute("UPDATE actions SET status='unknown' WHERE status='running'")
        await self.db.execute("UPDATE timers SET status='unknown' WHERE status='dispatching'")

    async def close(self) -> None:
        if self.db:
            await self.db.close()

    async def rows(self, sql: str, args: tuple = ()) -> list[dict]:
        async with self.lock:
            return await self._rows(sql, args)

    async def _rows(self, sql: str, args: tuple = ()) -> list[dict]:
        assert self.db is not None
        async with self.db.execute(sql, args) as c:
            return [dict(r) for r in await c.fetchall()]

    async def write(self, sql: str, args: tuple = ()) -> int:
        assert self.db is not None
        async with self.lock, self.db.execute(sql, args) as cursor:
            return cursor.rowcount

    async def role(self, user_id: int) -> str | None:
        if user_id == self.owner_id:
            return "owner"
        rows = await self.rows("SELECT role FROM members WHERE user_id=?", (user_id,))
        return rows[0]["role"] if rows else None

    async def require(self, user_id: int, minimum: str) -> None:
        if ROLES.get(await self.role(user_id), 0) < ROLES[minimum]:
            raise Forbidden("Недостаточно прав")

    async def invite(self, owner: int, username: str, role: str) -> None:
        await self.require(owner, "owner")
        username = username.lower().lstrip("@")
        if not re.fullmatch(r"[a-z][a-z0-9_]{4,31}", username) or role not in {"viewer", "operator"}:
            raise InvalidInput("Формат: /grant @username viewer|operator")
        assert self.db is not None
        await self.write("INSERT OR REPLACE INTO invites VALUES (?,?,?)",
                              (username, role, time.time() + 86400))

    async def claim(self, user_id: int, username: str | None) -> bool:
        if not username:
            return False
        rows = await self.rows("SELECT role FROM invites WHERE username=? AND expires>?",
                               (username.lower(), time.time()))
        if not rows:
            return False
        assert self.db is not None
        await self.write("INSERT OR REPLACE INTO claims VALUES (?,?,?,?)",
                              (user_id, username.lower(), rows[0]["role"], time.time()))
        return True

    async def approve(self, owner: int, user_id: int) -> None:
        await self.require(owner, "owner")
        assert self.db is not None
        async with self.lock:
            await self.db.execute("BEGIN IMMEDIATE")
            try:
                rows = await self._rows("""SELECT c.* FROM claims c JOIN invites i
                    ON c.username=i.username AND c.role=i.role
                    WHERE c.user_id=? AND i.expires>?""", (user_id, time.time()))
                if not rows or user_id == self.owner_id:
                    raise InvalidInput("Нет актуальной заявки; повторите приглашение")
                row = rows[0]
                await self.db.execute("INSERT OR REPLACE INTO members VALUES (?,?)",
                                      (user_id, row["role"]))
                await self.db.execute("DELETE FROM invites WHERE username=?", (row["username"],))
                await self.db.execute("DELETE FROM claims WHERE username=?", (row["username"],))
                await self.db.commit()
            except BaseException:
                await self.db.rollback()
                raise

    async def revoke(self, owner: int, target: int) -> None:
        await self.require(owner, "owner")
        if target == self.owner_id:
            raise InvalidInput("Владелец задаётся в конфигурации")
        assert self.db is not None
        await self.write("DELETE FROM members WHERE user_id=?", (target,))
        await self.write("UPDATE timers SET status='cancelled' WHERE user_id=? AND status='pending'", (target,))

    async def select(self, user_id: int, station: str) -> None:
        assert self.db is not None
        await self.write("INSERT OR REPLACE INTO selection VALUES (?,?)", (user_id, station))

    async def selected(self, user_id: int, default: str) -> str:
        r = await self.rows("SELECT station FROM selection WHERE user_id=?", (user_id,))
        return r[0]["station"] if r else default

    async def begin_action(self, request: str, user: int, station: str, action: str) -> bool:
        assert self.db is not None
        count = await self.write("INSERT OR IGNORE INTO actions VALUES (?,?,?,?,?,?)",
                                  (request, user, station, action, "running", time.time()))
        return count == 1

    async def finish_action(self, request: str, status: str) -> None:
        assert self.db is not None
        await self.write("UPDATE actions SET status=? WHERE request_id=?", (status, request))

    async def timer(self, user: int, chat: int, station: str, seconds: int) -> str:
        if not 1 <= seconds <= 86400:
            raise InvalidInput("Таймер: от 1 до 86400 секунд")
        assert self.db is not None
        async with self.lock:
            rows = await self._rows("SELECT count(*) AS n FROM timers WHERE user_id=? AND status='pending'", (user,))
            if rows[0]["n"] >= 10:
                raise InvalidInput("Не более 10 активных таймеров на пользователя")
            key = uuid.uuid4().hex[:12]
            await self.db.execute("INSERT INTO timers VALUES (?,?,?,?,?,?)",
                                  (key, user, chat, station, time.time() + seconds, "pending"))
            return key

    async def due_timers(self) -> list[dict]:
        assert self.db is not None
        async with self.lock:
            await self.db.execute("BEGIN IMMEDIATE")
            try:
                rows = await self._rows("SELECT * FROM timers WHERE due<=? AND status='pending'", (time.time(),))
                await self.db.execute("UPDATE timers SET status='dispatching' WHERE due<=? AND status='pending'", (time.time(),))
                await self.db.commit()
                return rows
            except BaseException:
                await self.db.rollback()
                raise

    async def finish_timer(self, key: str, status: str) -> None:
        assert self.db is not None
        await self.write("UPDATE timers SET status=? WHERE id=?", (status, key))

    async def prune(self, days: int) -> None:
        assert self.db is not None
        cutoff = time.time() - days * 86400
        await self.write("DELETE FROM actions WHERE created<?", (cutoff,))
        await self.write("DELETE FROM timers WHERE due<? AND status!='pending'", (cutoff,))
        await self.write("DELETE FROM claims WHERE created<?", (time.time() - 86400,))
        await self.write("DELETE FROM invites WHERE expires<?", (time.time(),))
