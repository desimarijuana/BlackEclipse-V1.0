"""W6 — durable per-run event sequences: no collisions, repair, rollback flag."""

from __future__ import annotations

import os
import tempfile
import threading

import pytest

from harness.events import RunEmitter
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def store():
    directory = tempfile.mkdtemp(prefix="be-event-seq-")
    s = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    yield s
    s.close()


def test_two_emitters_for_one_run_never_collide(store):
    store.create_run("run_evt", "a", {"query": "x"})
    emitters = [RunEmitter("run_evt", store) for _ in range(2)]
    lock = threading.Lock()
    emitted: list[dict] = []

    def worker(index: int) -> None:
        for step in range(20):
            event = emitters[index].emit_sync(
                "model.delta", {"step": step, "emitter": index},
            )
            with lock:
                emitted.append(event)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(emitted) == 40
    assert len({e["id"] for e in emitted}) == 40
    persisted = store.list_events("run_evt")
    assert len(persisted) == 40
    assert len({e["seq"] for e in persisted}) == 40
    assert [e["seq"] for e in persisted] == list(range(1, 41))


def test_legacy_duplicate_seqs_are_repaired_before_the_unique_index(store):
    from harness.event_sequence import EventSequence, UNIQUE_INDEX

    store.create_run("run_dup", "a", {"query": "x"})
    db = store._db
    for index in range(3):
        db.execute(
            "INSERT INTO HarnessEvent (id, runId, type, seq, at, data) VALUES (?, ?, ?, ?, ?, ?)",
            (f"evt_dup_{index}", "run_dup", "run.started", 1, f"2026-11-12T00:00:0{index}Z", "{}"),
        )
    db.commit()

    sequence = EventSequence(store)
    event = sequence.append("run_dup", "run.completed", {"ok": True})
    assert event["seq"] == 4

    rows = store.list_events("run_dup")
    assert [r["seq"] for r in rows] == [1, 2, 3, 4]
    # Every original row survives; only the duplicate seqs were renumbered.
    assert {r["id"] for r in rows} == {
        "evt_dup_0", "evt_dup_1", "evt_dup_2", event["id"],
    }
    indexes = {
        r["name"] for r in db.execute("PRAGMA index_list(HarnessEvent)").fetchall()
    }
    assert UNIQUE_INDEX in indexes


def test_event_sequence_flag_off_restores_the_local_counter(store, monkeypatch):
    monkeypatch.setenv("HARNESS_EVENT_SEQ", "off")
    store.create_run("run_off", "a", {"query": "x"})
    emitter = RunEmitter("run_off", store)
    first = emitter.emit_sync("run.started", {})
    second = emitter.emit_sync("run.completed", {})
    assert (first["seq"], second["seq"]) == (1, 2)
    assert first["id"] == "evt_run_off_1"


def test_transient_events_use_a_separate_id_space(store):
    store.create_run("run_t", "a", {"query": "x"})
    emitter = RunEmitter("run_t", store)
    emitter.emit_transient("model.delta", {"text": "x"})
    durable = emitter.emit_sync("run.started", {})
    assert durable["seq"] == 1
    # The transient event is not persisted and cannot collide.
    assert [e["type"] for e in store.list_events("run_t")] == ["run.started"]
