from __future__ import annotations

import os
from pathlib import Path

from .errors import InvalidInput


class InstanceLock:
    """OS-released advisory lock; no stale PID files or unrelated process termination."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.file = path.open("a+b")
        self.file.seek(0)
        self.file.write(b"0")
        self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            self.file.close()
            raise InvalidInput("Этот state_dir уже используется другим процессом бота") from e

    def close(self) -> None:
        self.file.close()
