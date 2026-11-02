from __future__ import annotations

import ipaddress
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10; same TOML contract as the standard library.
    import tomli as tomllib

from .errors import InvalidInput


@dataclass(frozen=True)
class StationConfig:
    id: str
    label: str
    url: str = field(repr=False)
    expected_model: str
    token_env: str = ""
    allow_packages: bool = False
    allow_owner_tools: bool = False
    camera_input: str = field(default="", repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.allow_packages, bool) or not isinstance(self.allow_owner_tools, bool):
            raise InvalidInput("allow_packages должен быть TOML boolean")
        if not re.fullmatch(r"[a-z0-9_-]{1,24}", self.id):
            raise InvalidInput("station.id: нужны 1–24 латинских символа, цифры, _ или -")
        u = urlsplit(self.url)
        if u.scheme not in {"http", "https"} or not u.hostname or u.username or u.password:
            raise InvalidInput("Некорректный URL станции: реквизиты в URL запрещены")
        if u.query or u.fragment or u.path.rstrip("/") != "/api":
            raise InvalidInput("URL станции должен заканчиваться на /api")
        try:
            loopback = ipaddress.ip_address(u.hostname).is_loopback
        except ValueError:
            loopback = u.hostname == "localhost"
        if not loopback and (u.scheme != "https" or not self.token_env):
            raise InvalidInput("Удалённая Luna требует HTTPS proxy и token_env; иначе SSH tunnel")
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", self.expected_model):
            raise InvalidInput("Укажите canonical expected_model из GET /api/device")
        if not self.label or len(self.label) > 64 or any(ord(c) < 32 for c in self.label):
            raise InvalidInput("label: 1–64 символа")


@dataclass(frozen=True)
class Config:
    owner_id: int
    stations: tuple[StationConfig, ...]
    state_dir: Path
    token_env: str = "TELEGRAM_BOT_TOKEN"
    rate_seconds: float = 1.0
    audit_days: int = 30
    telegram_proxy_env: str = ""
    legacy_history_dir: Path | None = field(default=None, repr=False)
    timezone: str = "UTC"

    def __post_init__(self) -> None:
        if self.owner_id <= 0 or not self.stations:
            raise InvalidInput("Нужны owner_id > 0 и хотя бы одна станция")
        if len({s.id for s in self.stations}) != len(self.stations):
            raise InvalidInput("Повторяющиеся station.id")
        if not 0.1 <= self.rate_seconds <= 60 or not 1 <= self.audit_days <= 365:
            raise InvalidInput("Некорректные rate_seconds или audit_days")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as e:
            raise InvalidInput("Неизвестный часовой пояс timezone") from e

    @classmethod
    def load(cls, path: Path) -> Config:
        try:
            raw = tomllib.loads(path.read_text(encoding="utf-8"))
            settings = raw["bot"]
            return cls(
                owner_id=int(settings["owner_id"]),
                stations=tuple(StationConfig(**s) for s in raw["stations"]),
                state_dir=(path.parent / settings.get("state_dir", "state")).resolve(),
                token_env=settings.get("token_env", "TELEGRAM_BOT_TOKEN"),
                rate_seconds=float(settings.get("rate_seconds", 1)),
                audit_days=int(settings.get("audit_days", 30)),
                telegram_proxy_env=settings.get("telegram_proxy_env", ""),
                legacy_history_dir=(path.parent / settings["legacy_history_dir"]).resolve() if settings.get("legacy_history_dir") else None,
                timezone=settings.get("timezone", "UTC"),
            )
        except (KeyError, TypeError, ValueError, OSError) as e:
            raise InvalidInput("Не удалось прочитать конфигурацию; проверьте config.example.toml") from e

    def token(self) -> str:
        token = os.environ.get(self.token_env, "")
        if not re.fullmatch(r"\d{5,15}:[A-Za-z0-9_-]{20,}", token):
            raise InvalidInput("Задайте токен бота в переменной окружения token_env")
        return token

    def telegram_proxy(self) -> str | None:
        if not self.telegram_proxy_env:
            return None
        proxy = os.environ.get(self.telegram_proxy_env, "")
        u = urlsplit(proxy)
        if u.scheme not in {"http", "socks5"} or not u.hostname:
            raise InvalidInput("Не задан корректный Telegram proxy в telegram_proxy_env")
        return proxy
