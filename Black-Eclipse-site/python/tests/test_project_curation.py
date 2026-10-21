"""Tests for the curated project view."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.projects import ProjectStore
from harness.projects.curate import KIND_PRIORITY, curate_project


@pytest.fixture()
def store(tmp_path) -> ProjectStore:
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return ProjectStore(ams)


def test_an_empty_project_says_it_is_empty(store):
    project = store.create("NQ momentum", symbols=["NQ"])
    digest = curate_project(store, project.id)
    assert digest is not None
    assert digest.member_count == 0
    assert "nothing has been put in it yet" in digest.headline
    assert any("no strategy has been attached yet" in g for g in digest.gaps)
    assert any("no result has been attached yet" in g for g in digest.gaps)


def test_a_project_that_does_not_exist_has_no_digest(store):
    assert curate_project(store, "proj_nope") is None


def test_a_result_outranks_a_strategy_which_outranks_a_dataset(store):
    project = store.create("p")
    store.attach(project.id, "dataset", "ds_1")
    store.attach(project.id, "strategy", "ema_cross")
    store.attach(project.id, "experiment", "exp_1")
    digest = curate_project(store, project.id)
    assert [m.kind for m in digest.members] == ["experiment", "strategy", "dataset"]
    assert KIND_PRIORITY["experiment"] > KIND_PRIORITY["strategy"] > KIND_PRIORITY["dataset"]


def test_every_member_carries_the_reason_it_was_ranked(store):
    project = store.create("p")
    store.attach(project.id, "experiment", "exp_1")
    store.attach(project.id, "note", "run:1", label="the NQ cross lost money")
    digest = curate_project(store, project.id)
    reasons = {m.kind: m.reason for m in digest.members}
    assert reasons["experiment"] == "a tested result"
    assert reasons["note"] == "a run record"
    assert all(m.reason for m in digest.members)


def test_the_headline_counts_what_the_project_holds(store):
    project = store.create("NQ momentum", symbols=["NQ", "ES"])
    store.attach(project.id, "strategy", "ema_cross")
    store.attach(project.id, "experiment", "exp_1")
    store.attach(project.id, "experiment", "exp_2")
    digest = curate_project(store, project.id)
    assert "NQ, ES" in digest.headline
    assert "1 strategy" in digest.headline
    assert "2 results" in digest.headline


def test_a_filled_project_has_no_gaps(store):
    project = store.create("p")
    store.attach(project.id, "strategy", "ema_cross")
    store.attach(project.id, "experiment", "exp_1")
    digest = curate_project(store, project.id)
    assert digest.gaps == []


def test_a_run_record_shows_its_excerpt_as_its_label(store):
    project = store.create("p")
    store.attach(project.id, "note", "run:1",
                 label="", meta={"excerpt": "The NQ cross loses money in high vol."})
    digest = curate_project(store, project.id)
    member = digest.members[0]
    assert member.label.startswith("The NQ cross loses money")


def test_the_digest_markdown_carries_the_gaps(store):
    project = store.create("p", symbols=["NQ"])
    store.attach(project.id, "strategy", "ema_cross")
    digest = curate_project(store, project.id)
    markdown = digest.to_markdown()
    assert "## Project: p" in markdown
    assert "strategy: `ema_cross`" in markdown
    assert "Still missing:" in markdown
    assert "no result has been attached yet" in markdown


def test_the_digest_is_a_dict_a_client_can_read(store):
    project = store.create("p")
    store.attach(project.id, "strategy", "ema_cross")
    payload = curate_project(store, project.id).to_dict()
    assert payload["projectId"] == project.id
    assert payload["memberCount"] == 1
    assert payload["counts"]["strategy"] == 1
    assert payload["members"][0]["kind"] == "strategy"


def test_the_newest_member_breaks_a_tie(store):
    project = store.create("p")
    store.attach(project.id, "strategy", "older")
    store.attach(project.id, "strategy", "newer")
    digest = curate_project(store, project.id)
    assert digest.members[0].ref == "newer"
