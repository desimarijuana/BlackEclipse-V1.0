"""The run-level video job collector (Phase 7): bounded, de-duplicated, and
strict — only real queued-job records survive into the chat blob."""

from __future__ import annotations

from harness.video.collector import MAX_RECORDS, VideoJobCollector


def test_empty_collector_produces_no_blob():
    assert VideoJobCollector().to_blob() is None


def test_collects_a_queued_render_record():
    collector = VideoJobCollector()
    collector.add({
        "jobId": "job_1", "projectId": "vprj_a", "projectName": "Recap",
        "kind": "render", "mode": "final",
    })
    blob = collector.to_blob()
    assert blob["type"] == "video" and blob["count"] == 1
    record = blob["jobs"][0]
    assert record["jobId"] == "job_1"
    assert record["kind"] == "render" and record["mode"] == "final"
    assert blob["schemaVersion"] == 1


def test_drops_malformed_records_and_unknown_kinds():
    collector = VideoJobCollector()
    for bad in (
        None, "nope", {}, {"jobId": "j"}, {"jobId": "j", "projectId": "p"},
        {"jobId": "j", "projectId": "p", "kind": "delete_everything"},
    ):
        collector.add(bad)
    assert collector.to_blob() is None


def test_same_job_reported_twice_keeps_one_latest_entry():
    collector = VideoJobCollector()
    collector.add({"jobId": "job_1", "projectId": "vprj_a", "kind": "render", "mode": "draft"})
    collector.add({"jobId": "job_1", "projectId": "vprj_a", "kind": "render", "mode": "final"})
    blob = collector.to_blob()
    assert blob["count"] == 1 and blob["jobs"][0]["mode"] == "final"


def test_the_blob_is_bounded():
    collector = VideoJobCollector()
    for index in range(MAX_RECORDS + 4):
        collector.add({"jobId": f"job_{index}", "projectId": "vprj_a", "kind": "preview"})
    blob = collector.to_blob()
    assert blob["count"] == MAX_RECORDS
    # Oldest dropped, newest kept.
    assert blob["jobs"][-1]["jobId"] == f"job_{MAX_RECORDS + 3}"


def test_repair_records_keep_their_parent_link():
    collector = VideoJobCollector()
    collector.add({
        "jobId": "job_2", "projectId": "vprj_a", "kind": "repair",
        "mode": "draft", "ofJobId": "job_1",
    })
    assert collector.to_blob()["jobs"][0]["ofJobId"] == "job_1"


def test_the_run_blob_persists_and_round_trips(tmp_path):
    from harness.persistence import AgentMemoryStore

    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    try:
        store.create_run("run_1", "eclipse-agent", {"query": "make a video"})
        blob = VideoJobCollector()
        blob.add({"jobId": "job_1", "projectId": "vprj_a", "kind": "render", "mode": "final"})
        store.update_run("run_1", video=blob.to_blob())
        run = store.get_run("run_1")
        assert run is not None
        assert run["video"]["count"] == 1
        assert run["video"]["jobs"][0]["jobId"] == "job_1"
        # Unrelated blobs are untouched (additive column).
        assert run.get("images") is None
    finally:
        store.close()
