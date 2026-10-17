"""Canvas tests — typed operations, revision-guarded saves and the AI
orchestrator (with a fake model, never a network call)."""

from __future__ import annotations

import pytest

from harness.artifacts import ArtifactService, ArtifactStore, LocalArtifactStorage
from harness.canvas.model import (
    CanvasConflict,
    CanvasEditRequest,
    CanvasError,
    CanvasKind,
    CanvasMode,
    CanvasOp,
    CanvasUnavailable,
    CreateCanvasInput,
    EditOperation,
    RestoreCanvasInput,
    SaveCanvasInput,
    Selection,
)
from harness.canvas.ops import OpError, apply_operations
from harness.canvas.service import CanvasService
from harness.persistence import AgentMemoryStore


@pytest.fixture()
def canvas(tmp_path):
    store = AgentMemoryStore(str(tmp_path / "agent-memory.db"))
    astore = ArtifactStore(store)
    artifacts = ArtifactService(astore, LocalArtifactStorage(tmp_path / "files"))
    yield CanvasService(artifacts), artifacts
    store.close()


DOC = "# Report\n\nIntro paragraph.\n\n## Risks\n\nSome risk text.\n\n## Next\n\nEnd.\n"


# ── operations ────────────────────────────────────────────────────────────────


def test_append_operation():
    result = apply_operations("# A\n", [EditOperation(op=CanvasOp.APPEND, content="tail\n")])
    assert result == "# A\n\ntail\n"


def test_replace_section_replaces_heading_body_and_stops_at_next_heading():
    op = EditOperation(op=CanvasOp.REPLACE_SECTION, heading="Risks", content="## Risks\n\nAll clear.")
    assert apply_operations(DOC, [op]) == "# Report\n\nIntro paragraph.\n\n## Risks\n\nAll clear.\n\n## Next\n\nEnd.\n"


def test_insert_after_section_keeps_following_section():
    op = EditOperation(op=CanvasOp.INSERT_AFTER_SECTION, heading="Risks", content="- new bullet")
    result = apply_operations(DOC, [op])
    assert "- new bullet" in result
    assert result.index("- new bullet") < result.index("## Next")


def test_replace_text_range_guards_expected_text():
    start = DOC.index("Intro paragraph.")
    ok = EditOperation(op=CanvasOp.REPLACE_TEXT_RANGE, start=start, end=start + 16, content="Overview.")
    assert "Overview." in apply_operations(DOC, [ok])
    bad = EditOperation(op=CanvasOp.REPLACE_TEXT_RANGE, start=start, end=start + 16,
                        content="x", expected_text="not what is there")
    with pytest.raises(OpError):
        apply_operations(DOC, [bad])


def test_code_patch_requires_unique_match():
    content = "def f():\n    return 1\n"
    good = EditOperation(op=CanvasOp.APPLY_CODE_PATCH, search="return 1", replace="return 2")
    assert "return 2" in apply_operations(content, [good], kind="code")
    ambiguous = EditOperation(op=CanvasOp.APPLY_CODE_PATCH, search="e", replace="x")
    with pytest.raises(OpError):
        apply_operations(content, [ambiguous], kind="code")


def test_replace_document_must_be_alone():
    ops = [
        EditOperation(op=CanvasOp.REPLACE_DOCUMENT, content="new"),
        EditOperation(op=CanvasOp.APPEND, content="more"),
    ]
    with pytest.raises(OpError):
        apply_operations(DOC, ops)


# ── service lifecycle ─────────────────────────────────────────────────────────


def test_create_save_conflict_restore(canvas):
    service, _artifacts = canvas
    snap = service.create(CreateCanvasInput(name="Equity Note", kind=CanvasKind.DOCUMENT, content=DOC))
    assert snap.name == "Equity Note.md"
    assert snap.kind is CanvasKind.DOCUMENT
    assert snap.version == 1
    assert snap.content == DOC

    saved = service.save(
        snap.artifact_id,
        SaveCanvasInput(base_version=1, content=DOC + "\nappended\n", change_note="manual"),
    )
    assert saved.version == 2
    assert "appended" in saved.content

    # A save based on the stale revision is refused, never applied.
    with pytest.raises(CanvasConflict) as exc:
        service.save(snap.artifact_id, SaveCanvasInput(base_version=1, content="overwrite"))
    assert exc.value.current_version == 2

    restored = service.restore(snap.artifact_id, RestoreCanvasInput(base_version=2, version=1))
    assert restored.version == 3
    assert restored.content == DOC


def test_save_with_operations_is_applied_server_side(canvas):
    service, _artifacts = canvas
    snap = service.create(CreateCanvasInput(name="Ops", kind=CanvasKind.DOCUMENT, content=DOC))
    saved = service.save(
        snap.artifact_id,
        SaveCanvasInput(
            base_version=1,
            operations=[EditOperation(op=CanvasOp.APPEND, content="Added by op.")],
        ),
    )
    assert "Added by op." in saved.content


def test_save_requires_content_or_operations(canvas):
    service, _artifacts = canvas
    snap = service.create(CreateCanvasInput(name="Empty", kind=CanvasKind.DOCUMENT, content="hi"))
    with pytest.raises(CanvasError):
        service.save(snap.artifact_id, SaveCanvasInput(base_version=1))


def test_list_filters_canvas_artifacts(canvas):
    service, artifacts = canvas
    service.create(CreateCanvasInput(name="Doc A", kind=CanvasKind.DOCUMENT, content="# A"))
    service.create(CreateCanvasInput(name="Lib B", kind=CanvasKind.CODE, language="python", content="print(1)"))
    artifacts.register_bytes(b"not canvas", name="plain.txt", owner_id="local")
    items = service.list(owner_id="local")
    assert {item.name for item in items} == {"Doc A.md", "Lib B.py"}
    only_code = service.list(owner_id="local", kind=CanvasKind.CODE)
    assert [item.name for item in only_code] == ["Lib B.py"]


def test_non_canvas_artifact_is_not_a_canvas_document(canvas):
    service, artifacts = canvas
    plain = artifacts.register_bytes(b"hello", name="plain.txt", owner_id="local")
    from harness.canvas.model import CanvasNotFound

    with pytest.raises(CanvasNotFound):
        service.snapshot(plain.id, owner_id="local")


# ── AI orchestrator ───────────────────────────────────────────────────────────


class _Resp:
    def __init__(self, content: str) -> None:
        self.content = content


class _Model:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    async def ainvoke(self, _messages):
        return _Resp(self._payload)


class _Runtime:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def resolve_for_run(self, settings, *, task=None):
        class _Res:
            settings = type("S", (), {"provider": "openai", "model": "gpt-4o"})()
            adapter = object()
            model = None
        return _Res()

    def build(self, settings, *, builder=None, adapter=None):
        return _Model(self._payload)

    async def invoke(self, *, invoke_fn, primary_model, resolution, task=None, raise_original=True, **kw):
        return await invoke_fn(primary_model)


def _patch_model(monkeypatch, payload: str):
    from harness import model_runtime

    monkeypatch.setattr(model_runtime, "get_runtime", lambda: _Runtime(payload))
    monkeypatch.setattr("harness.models.build_chat_model", lambda settings: _Model(payload))


SETTINGS = {"provider": "openai", "model": "gpt-4o", "apiKey": "test-key"}


@pytest.mark.asyncio
async def test_orchestrator_proposes_validated_edit(canvas, monkeypatch):
    service, _artifacts = canvas
    snap = service.create(CreateCanvasInput(name="Note", kind=CanvasKind.DOCUMENT, content=DOC))
    payload = (
        '{"answer": "Added a risk note.", "summary": "append a risk note", '
        '"operations": [{"op": "append", "content": "Risk: liquidity.", "explanation": "new risk"}], '
        '"notes": []}'
    )
    _patch_model(monkeypatch, payload)
    from harness.canvas.edits import CanvasEditOrchestrator

    proposal = await CanvasEditOrchestrator(service).propose(
        snap.artifact_id,
        CanvasEditRequest(base_version=1, instruction="add a risk note", mode=CanvasMode.EDIT,
                          model_settings=SETTINGS),
        owner_id="local",
    )
    assert proposal.operations and proposal.operations[0].op is CanvasOp.APPEND
    assert proposal.result_content and "Risk: liquidity." in proposal.result_content
    # Nothing was persisted by a proposal.
    assert service.snapshot(snap.artifact_id, owner_id="local").version == 1


@pytest.mark.asyncio
async def test_orchestrator_ask_never_edits(canvas, monkeypatch):
    service, _artifacts = canvas
    snap = service.create(CreateCanvasInput(name="Note", kind=CanvasKind.DOCUMENT, content=DOC))
    payload = '{"answer": "There are two sections.", "summary": "", "operations": [{"op": "append", "content": "x"}], "notes": []}'
    _patch_model(monkeypatch, payload)
    from harness.canvas.edits import CanvasEditOrchestrator

    proposal = await CanvasEditOrchestrator(service).propose(
        snap.artifact_id,
        CanvasEditRequest(base_version=1, instruction="what sections exist?",
                          mode=CanvasMode.ASK, model_settings=SETTINGS),
        owner_id="local",
    )
    assert proposal.operations == []
    assert proposal.result_content is None
    assert proposal.notes


@pytest.mark.asyncio
async def test_orchestrator_requires_model_and_current_revision(canvas, monkeypatch):
    service, _artifacts = canvas
    snap = service.create(CreateCanvasInput(name="Note", kind=CanvasKind.DOCUMENT, content=DOC))
    from harness.canvas.edits import CanvasEditOrchestrator

    orchestrator = CanvasEditOrchestrator(service)
    with pytest.raises(CanvasUnavailable):
        await orchestrator.propose(
            snap.artifact_id,
            CanvasEditRequest(base_version=1, instruction="edit", model_settings=None),
            owner_id="local",
        )

    _patch_model(monkeypatch, '{"answer": "", "summary": "", "operations": [], "notes": []}')
    with pytest.raises(CanvasConflict):
        await orchestrator.propose(
            snap.artifact_id,
            CanvasEditRequest(base_version=99, instruction="edit", model_settings=SETTINGS),
            owner_id="local",
        )


@pytest.mark.asyncio
async def test_orchestrator_rejects_invalid_operation(canvas, monkeypatch):
    service, _artifacts = canvas
    snap = service.create(CreateCanvasInput(name="Note", kind=CanvasKind.DOCUMENT, content=DOC))
    payload = '{"answer": "", "summary": "", "operations": [{"op": "replace_section", "heading": "Nope", "content": "x"}], "notes": []}'
    _patch_model(monkeypatch, payload)
    from harness.canvas.edits import CanvasEditOrchestrator

    with pytest.raises(CanvasError):
        await CanvasEditOrchestrator(service).propose(
            snap.artifact_id,
            CanvasEditRequest(base_version=1, instruction="edit", mode=CanvasMode.EDIT,
                              model_settings=SETTINGS),
            owner_id="local",
        )
