"""Tests for the Project store, the project tools and the project brief."""

from __future__ import annotations

import pytest

from harness.persistence import AgentMemoryStore
from harness.projects import MEMBER_KINDS, ProjectError, ProjectStore
from harness.projects.tools import (
    PROJECT_TOOLS,
    project_attach,
    project_create,
    project_detach,
    project_list,
    project_show,
)


@pytest.fixture()
def store(tmp_path) -> ProjectStore:
    ams = AgentMemoryStore(str(tmp_path / "am.db"))
    return ProjectStore(ams)


class _Ctx:
    """The slice of a ToolContext the project tools use."""

    def __init__(self, store: ProjectStore) -> None:
        self.project_store = store


# ── the store ────────────────────────────────────────────────────────────────

def test_a_project_is_created_with_its_instruments(store):
    project = store.create("NQ momentum", description="an intraday NQ study",
                           symbols=["NQ", "ES"], tags=["futures"])
    fetched = store.get(project.id)
    assert fetched is not None
    assert fetched.name == "NQ momentum"
    assert fetched.symbols == ["NQ", "ES"]
    assert fetched.tags == ["futures"]
    assert fetched.status == "active"


def test_a_project_needs_a_name(store):
    with pytest.raises(ProjectError):
        store.create("   ")


def test_projects_are_listed_most_recently_active_first(store):
    first = store.create("first")
    second = store.create("second")
    store.touch(second.id)
    ids = [p.id for p in store.list()]
    assert ids[0] == second.id
    assert first.id in ids


def test_attaching_a_member_records_where_to_look(store):
    project = store.create("p")
    member = store.attach(project.id, "strategy", "ema_cross v1.0.0",
                          label="the cross")
    assert member.kind == "strategy"
    assert member.ref == "ema_cross v1.0.0"
    members = store.members(project.id)
    assert [m.id for m in members] == [member.id]
    assert members[0].label == "the cross"


def test_attaching_to_a_project_that_does_not_exist_is_refused(store):
    with pytest.raises(ProjectError):
        store.attach("proj_nope", "strategy", "x")


def test_an_unknown_member_kind_is_refused(store):
    project = store.create("p")
    with pytest.raises(ProjectError):
        store.attach(project.id, "spaceship", "x")
    assert "strategy" in MEMBER_KINDS


def test_detaching_removes_only_that_member(store):
    project = store.create("p")
    a = store.attach(project.id, "strategy", "one")
    store.attach(project.id, "artifact", "two")
    assert store.detach(project.id, a.id) is True
    assert [m.ref for m in store.members(project.id)] == ["two"]
    assert store.detach(project.id, a.id) is False


def test_the_brief_lists_the_members_and_the_instruments(store):
    project = store.create("NQ momentum", symbols=["NQ"])
    store.attach(project.id, "strategy", "ema_cross")
    store.attach(project.id, "experiment", "exp_1")
    brief = store.brief(project.id)
    assert "NQ momentum" in brief
    assert "Instruments: NQ" in brief
    assert "strategy: `ema_cross`" in brief
    assert "experiment: `exp_1`" in brief


def test_the_brief_of_an_empty_project_says_so(store):
    project = store.create("empty")
    assert "Members: none yet." in store.brief(project.id)


def test_the_brief_of_a_project_that_does_not_exist_is_empty(store):
    assert store.brief("proj_nope") == ""


def test_deleting_a_project_takes_its_members(store):
    project = store.create("p")
    store.attach(project.id, "strategy", "x")
    assert store.delete(project.id) is True
    assert store.get(project.id) is None
    assert store.members(project.id) == []


def test_the_detail_groups_members_by_kind(store):
    project = store.create("p")
    store.attach(project.id, "strategy", "one")
    store.attach(project.id, "strategy", "two")
    store.attach(project.id, "artifact", "three")
    detail = store.detail(project.id)
    assert detail["memberCount"] == 3
    assert len(detail["membersByKind"]["strategy"]) == 2
    assert len(detail["membersByKind"]["artifact"]) == 1


# ── the tools ────────────────────────────────────────────────────────────────

async def test_the_tools_create_list_and_show_a_project(store):
    ctx = _Ctx(store)
    text, data = await project_create({"name": "NQ momentum", "symbols": ["NQ"]}, ctx)
    assert data["status"] == "OK"
    project_id = data["project"]["id"]

    _, listed = await project_list({}, ctx)
    assert listed["count"] == 1

    text, shown = await project_show({"projectId": project_id}, ctx)
    assert "NQ momentum" in text
    assert shown["project"]["id"] == project_id


async def test_showing_a_project_that_does_not_exist_is_a_named_refusal(store):
    _, data = await project_show({"projectId": "proj_nope"}, _Ctx(store))
    assert data["status"] == "ERROR"
    assert data["error"]["code"] == "PROJECT_NOT_FOUND"


async def test_the_attach_and_detach_tools_round_trip(store):
    ctx = _Ctx(store)
    _, created = await project_create({"name": "p"}, ctx)
    project_id = created["project"]["id"]

    _, attached = await project_attach(
        {"projectId": project_id, "kind": "strategy", "ref": "ema_cross"}, ctx)
    assert attached["status"] == "OK"
    member_id = attached["member"]["id"]

    _, detached = await project_detach(
        {"projectId": project_id, "memberId": member_id}, ctx)
    assert detached["status"] == "OK"
    assert store.members(project_id) == []


async def test_attaching_without_the_required_fields_is_a_named_refusal(store):
    _, data = await project_attach({"projectId": "proj_x"}, _Ctx(store))
    assert data["status"] == "ERROR"
    assert data["error"]["code"] == "PROJECT_ATTACH_INPUT_REQUIRED"


async def test_the_tools_report_an_unavailable_store_instead_of_faking(store):
    class _NoStore:
        project_store = None

    _, data = await project_list({}, _NoStore())
    assert data["status"] == "ERROR"
    assert "not configured" in data["error"]["message"]


# ── the run binding ──────────────────────────────────────────────────────────

def test_the_project_brief_block_names_an_unknown_project(store):
    from harness.graph import _project_brief_block

    block = _project_brief_block("proj_nope", store)
    assert "no such project exists" in block


def test_the_project_brief_block_carries_the_members(store):
    from harness.graph import _project_brief_block

    project = store.create("NQ momentum", symbols=["NQ"])
    store.attach(project.id, "strategy", "ema_cross")
    block = _project_brief_block(project.id, store)
    assert "NQ momentum" in block
    assert "strategy: `ema_cross`" in block


def test_no_project_means_no_block(store):
    from harness.graph import _project_brief_block

    assert _project_brief_block(None, store) == ""
    assert _project_brief_block("proj_x", None) == ""


def test_the_project_tools_are_registered_and_allowed():
    from harness.projects import PROJECT_TOOLS as EXPORTED

    assert EXPORTED == PROJECT_TOOLS
    assert "project_create" in PROJECT_TOOLS
    assert "project_show" in PROJECT_TOOLS


async def test_the_digest_tool_curates_a_project(store):
    from harness.projects.tools import project_digest

    ctx = _Ctx(store)
    _, created = await project_create({"name": "NQ momentum", "symbols": ["NQ"]}, ctx)
    project_id = created["project"]["id"]
    text, data = await project_digest({"projectId": project_id}, ctx)
    assert data["status"] == "OK"
    assert "NQ momentum" in text
    assert "Still missing:" in text


async def test_the_digest_tool_refuses_an_unknown_project(store):
    from harness.projects.tools import project_digest

    _, data = await project_digest({"projectId": "proj_nope"}, _Ctx(store))
    assert data["status"] == "ERROR"
    assert data["error"]["code"] == "PROJECT_NOT_FOUND"


async def test_the_next_tool_proposes_from_the_projects_evidence(store):
    from harness.projects.tools import project_next

    ctx = _Ctx(store)
    _, created = await project_create({"name": "NQ momentum"}, ctx)
    project_id = created["project"]["id"]
    text, data = await project_next({"projectId": project_id}, ctx)
    assert data["status"] == "OK"
    assert data["proposalCount"] >= 0
    assert "proposals" in data


async def test_the_next_tool_refuses_an_unknown_project(store):
    from harness.projects.tools import project_next

    _, data = await project_next({"projectId": "proj_nope"}, _Ctx(store))
    assert data["status"] == "ERROR"
    assert data["error"]["code"] == "PROJECT_NOT_FOUND"


def test_the_project_tools_are_in_the_chat_allowlist():
    from harness.agents import ECLIPSE_AGENT

    allowed = ECLIPSE_AGENT.tools
    assert allowed is not None
    for name in ("project_create", "project_list", "project_show",
                 "project_attach", "project_detach", "project_digest",
                 "project_next"):
        assert name in allowed, name


def test_the_project_layer_installs_the_store_and_the_tools(tmp_path):
    from harness.projects.bootstrap import install_project_layer
    from harness.tools import ToolRegistry

    class _Service:
        def __init__(self) -> None:
            self.registry = ToolRegistry()
            self.store = AgentMemoryStore(str(tmp_path / "am.db"))

    service = _Service()
    install_project_layer(service)
    assert getattr(service, "project_store", None) is not None
    assert "project_create" in service.registry.names()
    assert "project_show" in service.registry.names()


def test_the_project_routes_are_mounted_on_the_running_app():
    from harness.main import app

    mounted = set(app.openapi().get("paths", {}))
    for path in ("/projects", "/projects/{project_id}",
                 "/projects/{project_id}/members"):
        assert path in mounted, path
