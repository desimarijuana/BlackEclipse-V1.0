"""Migration test — filesystem and shell tools route through the Security Gateway.

Verifies that the composed effect authorizer enforces the Security Floor and emits
audit records, while still delegating ordinary approvals to the existing chain.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

os.environ.setdefault(
    "AGENT_MEMORY_DB_PATH",
    os.path.join(tempfile.mkdtemp(prefix="be-sec-int-"), "agent-memory.db"),
)

from harness.security.bootstrap import get_gateway, set_gateway
from harness.security.gateway import SecurityGateway
from harness.security.integration import classify_tool, make_security_authorizer
from harness.security.models import PolicyProfile


class _Tool:
    def __init__(self, name):
        self.name = name


class _Ctx:
    def __init__(self, agent_id="code-agent", workspace=None):
        self.agent_id = agent_id
        self.workspace = workspace
        self.workspace_id = workspace


def _run(coro):
    return asyncio.run(coro)


def test_classify_tool():
    assert classify_tool("write_file", {"path": "a.py"})[0] == "filesystem.write"
    assert classify_tool("delete_file", {"path": "a.py"})[0] == "filesystem.delete"
    action, resource, _ = classify_tool("command_run", {"command": "python -m pytest"})
    assert action == "code.execute" and resource == "python"
    assert classify_tool("read_file", {"path": "a.py"}) is None  # reads not migrated here


def test_authorizer_hard_denies_sensitive_path(tmp_path):
    from harness.persistence import AgentMemoryStore

    store = AgentMemoryStore(os.path.join(tempfile.mkdtemp(), "am.db"))
    gw = SecurityGateway(store=store, profile=PolicyProfile.DEVELOPER)
    set_gateway(gw)

    async def inner(tool, args, ctx=None):
        return True  # the inner chain would have allowed it

    authorizer = make_security_authorizer(inner, run_id="run1", workspace_id="ws", gateway=gw)
    allowed = _run(authorizer(_Tool("write_file"), {"path": "/home/u/.ssh/id_rsa"}, _Ctx()))
    assert allowed is False
    # The refusal was audited.
    events = gw.audit.list(category="floor", limit=10)
    assert any(e["decision"] == "deny" for e in events)
    set_gateway(None)


def test_authorizer_delegates_ordinary_write_to_inner(tmp_path):
    from harness.persistence import AgentMemoryStore

    store = AgentMemoryStore(os.path.join(tempfile.mkdtemp(), "am.db"))
    gw = SecurityGateway(store=store, profile=PolicyProfile.DEVELOPER)
    set_gateway(gw)
    calls = {"n": 0}

    async def inner(tool, args, ctx=None):
        calls["n"] += 1
        return True

    authorizer = make_security_authorizer(inner, run_id="run2", workspace_id="ws", gateway=gw)
    allowed = _run(authorizer(_Tool("write_file"), {"path": "src/app.py"}, _Ctx()))
    assert allowed is True
    assert calls["n"] == 1
    # An allow decision was audited.
    events = gw.audit.list(category="authorization", limit=10)
    assert any(e["decision"] == "allow" for e in events)
    set_gateway(None)


def test_authorizer_without_gateway_uses_inner():
    set_gateway(None)

    async def inner(tool, args, ctx=None):
        return True

    authorizer = make_security_authorizer(inner, run_id="r", workspace_id="ws", gateway=None)
    assert _run(authorizer(_Tool("write_file"), {"path": "a.py"}, _Ctx())) is True


def test_build_effect_authorizer_wraps_with_security():
    from harness.persistence import AgentMemoryStore
    from harness.code.authorizers import build_effect_authorizer

    store = AgentMemoryStore(os.path.join(tempfile.mkdtemp(), "am.db"))
    gw = SecurityGateway(store=store, profile=PolicyProfile.DEVELOPER)
    set_gateway(gw)
    authorizer = build_effect_authorizer(None, "run-x", None, "ws")
    assert getattr(authorizer, "__security_authorizer__", False) is True
    # A sensitive-path write is refused even with no approval store.
    allowed = _run(authorizer(_Tool("write_file"), {"path": "/root/.aws/credentials"}, _Ctx()))
    assert allowed is False
    set_gateway(None)
