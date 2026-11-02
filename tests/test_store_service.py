import asyncio
import time

import pytest

from stationbot.errors import Forbidden, InvalidInput
from stationbot.store import Store


async def test_username_invite_requires_owner_approval_and_pins_id(store):
    await store.invite(1, "@friend", "operator")
    assert await store.claim(2, "Friend") is True
    assert await store.role(2) is None
    with pytest.raises(Forbidden):
        await store.approve(2, 2)
    await store.approve(1, 2)
    assert await store.role(2) == "operator"
    assert await store.claim(3, "friend") is False
    assert await store.role(3) is None
    await store.revoke(1, 2)
    assert await store.role(2) is None


async def test_viewer_cannot_record(service):
    await service.store.write("INSERT INTO members VALUES (?,?)", (2, "viewer"))
    with pytest.raises(Forbidden):
        await service.run(2, "mini", "record", ["1"], "req")
    assert not service.fakes[0].requests


async def test_duplicate_update_cannot_repeat_mutation(service):
    await service.run(1, "mini", "volume", ["10"], "same-update")
    await asyncio.sleep(0.11)
    with pytest.raises(InvalidInput, match="уже обработана"):
        await service.run(1, "mini", "volume", ["10"], "same-update")
    assert sum(r.method == "POST" for r in service.fakes[0].requests) == 1


async def test_crash_recovery_preserves_uncertainty(tmp_path):
    path = tmp_path / "recovery.db"
    s = Store(path, 1)
    await s.open()
    assert await s.begin_action("req", 1, "mini", "volume")
    key = await s.timer(1, 1, "mini", 1)
    await s.write("UPDATE timers SET status='dispatching' WHERE id=?", (key,))
    await s.close()
    s = Store(path, 1)
    await s.open()
    try:
        assert (await s.rows("SELECT status FROM actions"))[0]["status"] == "unknown"
        assert (await s.rows("SELECT status FROM timers"))[0]["status"] == "unknown"
        assert await s.begin_action("req", 1, "mini", "volume") is False
        assert await s.due_timers() == []
    finally:
        await s.close()


async def test_timers_claimed_once_and_isolated_by_user(store):
    await store.timer(1, 1, "mini", 1)
    await store.timer(2, 2, "station", 1)
    await store.write("UPDATE timers SET due=?", (time.time() - 1,))
    batches = await asyncio.gather(store.due_timers(), store.due_timers())
    assert sorted(len(batch) for batch in batches) == [0, 2]


async def test_revocation_cancels_pending_timers(store):
    await store.write("INSERT INTO members VALUES (?,?)", (2, "operator"))
    await store.timer(2, 2, "mini", 10)
    await store.revoke(1, 2)
    assert (await store.rows("SELECT status FROM timers"))[0]["status"] == "cancelled"


async def test_invitation_cannot_be_approved_twice_concurrently(store):
    await store.invite(1, "friend", "viewer")
    await store.claim(2, "friend")
    await store.claim(3, "friend")
    outcomes = await asyncio.gather(store.approve(1, 2), store.approve(1, 3), return_exceptions=True)
    assert sum(isinstance(o, InvalidInput) for o in outcomes) == 1
    assert len(await store.rows("SELECT * FROM members")) == 1


async def test_revocation_while_queued_prevents_station_write(service):
    await service.store.write("INSERT INTO members VALUES (2,'operator')")
    lock = service.clients["mini"].operation_lock
    await lock.acquire()
    queued = asyncio.create_task(service.run(2, "mini", "volume", ["10"], "queued"))
    # Wait until the durable intent is written and the task is queued on the station lock.
    for _ in range(100):
        if await service.store.rows("SELECT * FROM actions WHERE request_id='queued'"):
            break
        await asyncio.sleep(0.001)
    await service.store.revoke(1, 2)
    lock.release()
    with pytest.raises(Forbidden):
        await queued
    assert service.fakes[0].requests == []


async def test_one_busy_station_does_not_block_another(service):
    await service.store.write("INSERT INTO members VALUES (2,'operator')")
    lock = service.clients["mini"].operation_lock
    await lock.acquire()
    queued = asyncio.create_task(service.run(1, "mini", "volume", ["10"], "busy"))
    try:
        result = await asyncio.wait_for(service.run(2, "station", "volume_get", [], "independent"), 2)
        assert result["percent"] == 20
    finally:
        lock.release()
        await queued
