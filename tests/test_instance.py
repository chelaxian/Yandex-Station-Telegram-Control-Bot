import pytest

from stationbot.errors import InvalidInput
from stationbot.instance import InstanceLock


def test_single_instance_lock_releases_without_pid_cleanup(tmp_path):
    path = tmp_path / "instance.lock"
    lock = InstanceLock(path)
    try:
        with pytest.raises(InvalidInput):
            InstanceLock(path)
    finally:
        lock.close()
    second = InstanceLock(path)
    second.close()
