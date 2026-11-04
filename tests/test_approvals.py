from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import BaseModel, ConfigDict

from vox.approvals import ApprovalStore, Status, Tier, Via, call_hash


class Args(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str
    count: int = 1


class Clock:
    now = 100.0
    wall = 1000.0

    def monotonic(self) -> float:
        return self.now

    def time(self) -> float:
        return self.wall


@pytest.fixture
def clock():
    return Clock()


@pytest.fixture
def store(clock):
    return ApprovalStore(monotonic=clock.monotonic, wall_time=clock.time)


def test_validated_calls_only_and_canonical_hash():
    a = Args(path="file", count=2)
    assert call_hash("delete", a) == call_hash("delete", Args(count=2, path="file"))
    assert call_hash("delete", a) != call_hash("move", a)
    with pytest.raises(TypeError):
        call_hash("delete", {"path": "file"})
    with pytest.raises(ValueError):
        call_hash("", a)
    with pytest.raises(ValueError):
        Args(path="file", tier=0)


def test_single_use_bound_to_name_args_and_tier(store):
    args = Args(path="file")
    approval = store.request("delete", args, Tier.CONFIRM)
    assert store.resolve(approval.id, approve=True, via=Via.CLICK)
    assert not store.consume(approval.id, "move", args, tier=Tier.CONFIRM)
    assert not store.consume(approval.id, "delete", Args(path="other"), tier=Tier.CONFIRM)
    assert not store.consume(approval.id, "delete", args, tier=Tier.CONFIRM_HARD)
    assert store.consume(approval.id, "delete", args, tier=Tier.CONFIRM)
    assert not store.consume(approval.id, "delete", args, tier=Tier.CONFIRM)
    assert store.get(approval.id).status == Status.CONSUMED


def test_t2_voice_cannot_approve_and_voice_requires_loopback_check(store):
    args = Args(path="file")
    hard = store.request("delete", args, Tier.CONFIRM_HARD)
    assert not store.resolve(hard.id, approve=True, via=Via.VOICE, loopback_clear=True)
    assert store.resolve(hard.id, approve=True, via=Via.HOTKEY)
    normal = store.request("delete", args, Tier.CONFIRM)
    assert not store.resolve(normal.id, approve=True, via=Via.VOICE)
    assert store.resolve(normal.id, approve=True, via=Via.VOICE, loopback_clear=True)


def test_invalid_untrusted_inputs_fail_closed(store):
    args = Args(path="file")
    request = store.request("delete", args, Tier.CONFIRM)
    assert not store.resolve(request.id, approve=True, via="click")
    assert not store.resolve(request.id, approve="yes", via=Via.CLICK)
    assert not store.resolve(request.id, approve=True, via=Via.VOICE, loopback_clear="yes")
    assert not store.consume(request.id, "delete", args, tier=1)
    assert store.get(request.id).status == Status.PENDING
    for tier in (Tier.SAFE, Tier.BLOCKED, 1):
        with pytest.raises(ValueError):
            store.request("delete", args, tier)


def test_deny_silence_expiry_and_wall_clock_jumps(store, clock):
    args = Args(path="file")
    denied = store.request("delete", args, Tier.CONFIRM)
    assert store.resolve(denied.id, approve=False, via=Via.VOICE)
    assert not store.resolve(denied.id, approve=True, via=Via.CLICK)
    assert not store.consume(denied.id, "delete", args, tier=Tier.CONFIRM)
    expired = store.request("delete", args, Tier.CONFIRM, ttl=2)
    clock.wall -= 10000
    clock.now += 2
    assert not store.resolve(expired.id, approve=True, via=Via.CLICK)
    assert store.get(expired.id).status == Status.EXPIRED
    approved = store.request("delete", args, Tier.CONFIRM, ttl=1)
    assert store.resolve(approved.id, approve=True, via=Via.CLICK)
    clock.now += 1
    assert not store.consume(approved.id, "delete", args, tier=Tier.CONFIRM)


@pytest.mark.parametrize("ttl", [0, -1, 16, float("inf"), float("nan")])
def test_ttl_is_bounded(store, ttl):
    with pytest.raises(ValueError):
        store.request("delete", Args(path="file"), Tier.CONFIRM, ttl=ttl)


def test_stop_revokes_pending_and_preapproved(store):
    args = Args(path="file")
    pending = store.request("delete", args, Tier.CONFIRM)
    approved = store.request("delete", args, Tier.CONFIRM)
    assert store.resolve(approved.id, approve=True, via=Via.CLICK)
    assert store.deny_all() == 2
    assert store.get(pending.id).via == "stop"
    assert not store.consume(approved.id, "delete", args, tier=Tier.CONFIRM)
    assert not store.resolve(pending.id, approve=True, via=Via.CLICK)


def test_concurrent_consumption_is_single_use(store):
    args = Args(path="file")
    request = store.request("delete", args, Tier.CONFIRM)
    assert store.resolve(request.id, approve=True, via=Via.CLICK)
    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(
            pool.map(
                lambda _: store.consume(request.id, "delete", args, tier=Tier.CONFIRM), range(64)
            )
        )
    assert sum(results) == 1


def test_store_capacity_preserves_live_approvals(clock):
    store = ApprovalStore(monotonic=clock.monotonic, wall_time=clock.time, capacity=1)
    args = Args(path="file")
    first = store.request("delete", args, Tier.CONFIRM)
    with pytest.raises(RuntimeError):
        store.request("delete", args, Tier.CONFIRM)
    assert store.resolve(first.id, approve=True, via=Via.CLICK)
    with pytest.raises(RuntimeError):
        store.request("delete", args, Tier.CONFIRM)
    assert store.consume(first.id, "delete", args, tier=Tier.CONFIRM)
    second = store.request("delete", args, Tier.CONFIRM)
    assert store.get(first.id) is None
    assert store.get(second.id).status == Status.PENDING
