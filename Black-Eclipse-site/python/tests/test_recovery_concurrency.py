"""Concurrency invariants — the repair lease is exclusive under contention."""

from __future__ import annotations

import threading

from harness.eclipse_memory.store import EclipseMemoryStore
from harness.recovery.service import RecoveryService


def _svc(tmp_path) -> RecoveryService:
    return RecoveryService(EclipseMemoryStore(str(tmp_path / "eclipse-memory.db")))


def test_only_one_holder_acquires_the_repair_lease(tmp_path):
    svc = _svc(tmp_path)
    store = svc.store
    store.acquire_lease("shared-signature", "holder0", ttl_s=3600)  # pre-claim
    wins: list[str] = []
    lock = threading.Lock()

    def worker(n: int) -> None:
        if store.acquire_lease("shared-signature", f"holder{n}", ttl_s=3600):
            with lock:
                wins.append(f"holder{n}")

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(1, 16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert wins == []  # the pre-claim holder owns it; no other worker may proceed


def test_releasing_frees_the_lease_for_the_next_worker(tmp_path):
    svc = _svc(tmp_path)
    store = svc.store
    assert store.acquire_lease("sig", "a", ttl_s=3600) is True
    assert store.acquire_lease("sig", "b", ttl_s=3600) is False
    store.release_lease("sig", "a")
    assert store.acquire_lease("sig", "b", ttl_s=3600) is True