"""Phase 21 — the notebook run route is a HOST boundary.

The route, not the request body, names the import widening and the persistent
namespace. These tests call the coroutine directly with the runtime mocked, so
they pin the boundary without spawning a real sandbox.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from harness.routers import notebook as notebook_mod
from harness.routers.notebook import _RunBody, run_notebook_cell, restart_notebook_kernel


def _run(coro):
    return asyncio.run(coro)


def _run_result(*, status: str = "ok", text: str = "Worked out by Eclipse.") -> tuple[str, dict]:
    return text, {
        "status": status,
        "outputs": {"value": 2} if status == "ok" else {},
        "artifacts": [],
        "figure": None,
        "provenance": {"kind": "computed", "label": "computed", "detail": "a notebook cell"},
        "sourceDigest": "abc123",
        "durationMs": 7,
        "code": None if status == "ok" else "INPUT_INVALID",
    }


def test_route_fixes_imports_and_persistence(monkeypatch, tmp_path):
    seen: dict = {}

    async def fake_analysis(args, ctx, **kwargs):
        seen["args"] = args
        seen["ctx"] = ctx
        seen["kwargs"] = kwargs
        return _run_result()

    monkeypatch.setattr(notebook_mod, "analysis_run", fake_analysis)
    monkeypatch.setattr(notebook_mod, "_output_dir", lambda *_: tmp_path / "out")

    body = _RunBody(chatId="chat_1", source="result = {'value': 2}", inputs={"chart": {"kind": "line"}})
    data = _run(run_notebook_cell("cell_1", body, True))

    assert seen["kwargs"]["extra_imports"] == ("io", "matplotlib")
    assert seen["kwargs"]["persist_namespace"] is True
    assert seen["args"]["inputs"] == {"chart": {"kind": "line"}}
    assert seen["args"]["purpose"] == "a notebook cell the user ran"
    assert seen["ctx"].session_id == "chat_1"
    assert data["status"] == "ok"
    assert data["outputs"] == {"value": 2}
    assert data["sourceDigest"] == "abc123"


def test_route_reports_a_refusal_as_an_error(monkeypatch, tmp_path):
    async def fake_analysis(args, ctx, **kwargs):
        return _run_result(status="refused", text="That used something I'm not allowed to use.")

    monkeypatch.setattr(notebook_mod, "analysis_run", fake_analysis)
    monkeypatch.setattr(notebook_mod, "_output_dir", lambda *_: tmp_path / "out")

    body = _RunBody(chatId="chat_2", source="import os")
    data = _run(run_notebook_cell("cell_2", body, True))
    assert data["status"] == "refused"
    assert "not allowed" in data["error"]


def test_an_invalid_cell_id_is_refused(monkeypatch):
    body = _RunBody(chatId="chat_3", source="result = 1")
    with pytest.raises(HTTPException):
        _run(run_notebook_cell("../bad", body, True))


def test_the_body_cannot_widen_the_import_allowlist():
    with pytest.raises(ValidationError):
        _RunBody(
            chatId="chat_4",
            source="result = 1",
            extraImports=["os"],
        )


def test_restart_uses_the_conversation_key(monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(notebook_mod, "reset_kernel_for_context", lambda ctx: seen.append(ctx.session_id))
    data = _run(restart_notebook_kernel(notebook_mod._RestartBody(chatId="chat_5"), True))
    assert data == {"status": "OK", "restarted": True}
    assert seen == ["chat_5"]
