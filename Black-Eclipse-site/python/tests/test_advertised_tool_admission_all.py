"""The generalized advertised-but-dead guard.

`test_advertised_tool_admission.py` pins a curated family list. This test
GENERALIZES it: it enumerates EVERY advertised non-read tool across all agent
allowlists plus the chat code profile, composes the REAL authorizer chain with a
permissive store and a bound workspace, and asserts each is admitted by SOME
layer — except the deliberately-deferred cluster/infra/cloud mutations below.

This is the enforcement that would have caught `portfolio_create` (and, when first
run, caught `code_rename_symbol` routing, `image_generate`, and
`learning_progress_update` — all now fixed).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from types import SimpleNamespace

import pytest

from harness.agents import CHAT_CODE_TOOLS, CODE_AGENT, CODE_NAVIGATOR, ECLIPSE_AGENT
from harness.tools import ToolRegistry

# Advertised non-read tools that are DELIBERATELY unreachable: cluster / infra /
# cloud mutations have no admission branch or approval kind yet (audit §6, R3-07).
# They stay registered-but-refused ON PURPOSE until an infra approval kind lands.
PINNED_INFRA: frozenset[str] = frozenset({
    "k8s_apply", "k8s_delete", "k8s_scale", "k8s_exec",
    "helm_install", "helm_uninstall",
    "terraform_apply", "terraform_destroy",
    "deploy_run", "deploy_rollback", "deploy_delete",
})


class _PermissiveStore:
    """Grants/claims everything, so only a MISSING admission branch yields False."""

    def __init__(self) -> None:
        self.grants = self

    def matches(self, *a: object) -> dict:
        return {"id": "grant_1"}

    def consume_kind(self, **k: object) -> dict:
        return {"id": "appr_1"}

    def consume(self, *a: object, **k: object) -> dict:
        return {"id": "appr_1"}

    def find_active_kind(self, **k: object) -> dict:
        return {"id": "appr_1"}

    def request_kind(self, **k: object) -> dict:
        return {"id": "appr_req"}

    def wait_for_decision(self, *a: object, **k: object) -> dict:
        return {"status": "approved"}


@pytest.fixture(scope="module")
def service_registry() -> ToolRegistry:
    from harness.persistence import AgentMemoryStore
    from harness.service import AgenticService

    directory = tempfile.mkdtemp(prefix="be-admit-all-")
    store = AgentMemoryStore(os.path.join(directory, "agent-memory.db"))
    try:
        yield AgenticService(store=store).registry
    finally:
        store.close()


@pytest.fixture(autouse=True)
def _no_gateway(monkeypatch: pytest.MonkeyPatch) -> None:
    from harness.security import bootstrap as sec

    monkeypatch.setattr(sec, "get_gateway", lambda: None)


def _advertised_non_read(registry: ToolRegistry) -> set[str]:
    names: set[str] = set()
    for agent in (ECLIPSE_AGENT, CODE_AGENT, CODE_NAVIGATOR):
        names |= set(getattr(agent, "tools", ()) or ())
    names |= set(CHAT_CODE_TOOLS)
    out: set[str] = set()
    for name in names:
        tool = registry.get(name)
        if tool is not None and tool.permission != "read":
            out.add(name)
    return out


def _args_for(registry: ToolRegistry) -> dict:
    """A superset of the args the name/approval-layer authorizers might read."""
    from harness.mcp.install_ops import list_catalog

    catalog = list_catalog()
    integration_id = catalog[0]["id"] if catalog else "x"
    return {
        "name": "X", "skill_id": "user.x", "instructions": "y",
        "source": "https://github.com/acme/tools",
        "integrationId": integration_id, "integration_id": integration_id,
        "command": "ls", "path": "a", "portfolio_id": "p", "prompt": "a cat",
        "status": "done", "node_id": "n",
    }


def test_every_advertised_non_read_tool_is_admitted_or_pinned(service_registry: ToolRegistry) -> None:
    from harness.code.authorizers import build_effect_authorizer

    store = _PermissiveStore()
    ctx = SimpleNamespace(
        approvals=store, run_id="r", pause_for_approval=False, emitter=None,
        effect_authorized_digest=None, workspace=SimpleNamespace(id="ws1"),
    )
    auth = build_effect_authorizer(approvals=store, run_id="r", emitter=None, workspace_id="ws1")
    args = _args_for(service_registry)

    dead: set[str] = set()
    for name in sorted(_advertised_non_read(service_registry)):
        if name in PINNED_INFRA:
            continue
        tool = service_registry.get(name)
        if not asyncio.run(auth(tool, dict(args), ctx)):
            dead.add(name)
    assert not dead, (
        "advertised to an agent but NO authorizer layer admits them (they are "
        f"advertised-but-dead): {sorted(dead)}"
    )


def test_the_pinned_infra_set_is_still_exactly_unreachable(service_registry: ToolRegistry) -> None:
    # Keep the pin honest: if an infra admission branch lands later, this fails and
    # the pin must be removed.
    from harness.code.authorizers import build_effect_authorizer

    store = _PermissiveStore()
    ctx = SimpleNamespace(
        approvals=store, run_id="r", pause_for_approval=False, emitter=None,
        effect_authorized_digest=None, workspace=SimpleNamespace(id="ws1"),
    )
    auth = build_effect_authorizer(approvals=store, run_id="r", emitter=None, workspace_id="ws1")
    args = _args_for(service_registry)
    reachable = {
        name for name in PINNED_INFRA
        if service_registry.get(name) is not None
        and asyncio.run(auth(service_registry.get(name), dict(args), ctx))
    }
    assert reachable == set(), (
        f"these now have an admission branch — remove them from PINNED_INFRA: {sorted(reachable)}"
    )
