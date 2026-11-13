"""Fail-closed contract for the experimental Max ADB + root SSH transport.

This module only verifies the two existing transports. It deliberately has no
file upload or remote command method: Max installation remains unqualified.
"""
from __future__ import annotations

from dataclasses import dataclass

from .max_ssh_probe import MaxSshTarget, probe_max_ssh
from .provision import Adb, ProvisionError, serial_address


@dataclass(frozen=True)
class MaxHybridTarget:
    serial: str
    ssh: MaxSshTarget

    def __post_init__(self):
        normalized = serial_address(self.serial)
        if normalized.removesuffix(":5555") != self.ssh.host:
            raise ProvisionError("ADB и SSH должны указывать на один и тот же IP колонки")

    @property
    def adb_serial(self) -> str:
        return serial_address(self.serial)


class MaxNonRootAdb:
    """Read-only UID check for Max's persistent shell-grade ADB transport."""

    def __init__(self, executable: str, target: MaxHybridTarget):
        self.client = Adb(executable, target.serial)

    def verify(self) -> None:
        self.client.connect()
        values = [line.strip("\0 \r\n\t") for line in self.client.shell("id -u; uname -m").splitlines()]
        values = [value for value in values if value]
        if values != ["2000", "aarch64"]:
            raise ProvisionError(
                "Ожидался постоянный non-root ADB (UID 2000, aarch64) Станции Макс; "
                "проверка остановлена без записи"
            )


def verify_max_hybrid(target: MaxHybridTarget, adb_executable: str) -> None:
    """Verify both existing transports without installing or changing the device."""
    MaxNonRootAdb(adb_executable, target).verify()
    probe_max_ssh(target.ssh)


def open_forward(target: MaxHybridTarget, adb_executable: str, port: int) -> None:
    """Open the exact ADB forward only after both identities pass."""
    verify_max_hybrid(target, adb_executable)
    client = Adb(adb_executable, target.serial)
    client.forward(port)
