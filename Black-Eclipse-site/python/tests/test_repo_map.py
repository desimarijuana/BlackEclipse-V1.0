"""Round 3 / W4 (ADR-H287) - the model is TOLD the shape of the project.

The defect this file is the gate for: the harness had NO repo map at all. A
model that wanted to know what was in the project had to GUESS a path, spend a
tool call on it, and - on a miss - get a bare "that file isn't there". The CIUE
index and the context engine are genuinely good, but they were reachable only
if the model THOUGHT to call `code_get_relevant_context`. Excellent
machinery, invisible.

The rules this file asserts:

1. The map is DETERMINISTIC: the same tree produces the same map and the same
   digest, every time.
2. The map is BOUNDED: a file count, a symbols-per-file count and a byte
   budget. It is a summary, never a copy.
3. The map is HONEST about its engine, and the index's freshness is
   MEASURED - `is_fresh()` used to `return True` unconditionally, which is an
   unmeasured claim about a cache.
4. The map joins the PROMPT CACHE KEY: a changed map invalidates the cache and
   an unchanged map does not.
5. A map failure never breaks a run.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

import pytest

from harness.code.intel.repo_map import (  # noqa: E402
    MAX_MAP_CHARS,
    MAX_MAP_FILES,
    MAX_SYMBOLS_PER_FILE,
    build_repo_map,
    render_repo_map,
)
from harness.prompt_segments import build_prompt_plan  # noqa: E402


def _project(root: str) -> str:
    os.makedirs(os.path.join(root, "src", "app"), exist_ok=True)
    os.makedirs(os.path.join(root, "src", "lib"), exist_ok=True)
    with open(os.path.join(root, "src", "app", "main.py"), "w", encoding="utf-8") as h:
        h.write("class Main:\n    def run(self):\n        pass\n\ndef helper():\n    return 1\n")
    with open(os.path.join(root, "src", "lib", "util.ts"), "w", encoding="utf-8") as h:
        h.write("export function util() { return 1; }\n")
    with open(os.path.join(root, "README.md"), "w", encoding="utf-8") as h:
        h.write("hello\n")
    return root


# ── the rule: DETERMINISTIC ────────────────────────────────────────────────


def test_the_map_is_deterministic() -> None:
    root = _project(tempfile.mkdtemp(prefix="map-"))
    first = build_repo_map(root)
    second = build_repo_map(root)
    assert first.digest == second.digest
    assert first.digest != ""
    assert first.files == second.files
    assert first.outlines == second.outlines


def test_a_changed_tree_changes_the_digest() -> None:
    root = _project(tempfile.mkdtemp(prefix="map-"))
    before = build_repo_map(root)
    with open(os.path.join(root, "src", "app", "extra.py"), "w", encoding="utf-8") as h:
        h.write("def extra():\n    return 2\n")
    after = build_repo_map(root)
    assert after.digest != before.digest


# ── the rule: BOUNDED ──────────────────────────────────────────────────────


def test_the_map_is_bounded() -> None:
    root = tempfile.mkdtemp(prefix="map-")
    for index in range(400):
        with open(os.path.join(root, f"f{index}.py"), "w", encoding="utf-8") as h:
            h.write("def f():\n    return 1\n")
    m = build_repo_map(root, max_files=20)
    assert len(m.outlines) <= 20
    assert m.total_files >= 400
    assert m.truncated is True


def test_the_outline_is_bounded_per_file() -> None:
    root = tempfile.mkdtemp(prefix="map-")
    with open(os.path.join(root, "many.py"), "w", encoding="utf-8") as h:
        h.write("\n".join(f"def f{i}():\n    return {i}" for i in range(50)))
    m = build_repo_map(root, max_symbols=3)
    assert m.outlines
    for _path, symbols in m.outlines:
        assert len(symbols) <= 3


def test_the_render_is_bounded_and_labelled() -> None:
    root = _project(tempfile.mkdtemp(prefix="map-"))
    block = render_repo_map(build_repo_map(root))
    assert "Repository map" in block
    assert "DATA rather than instruction" in block
    assert "src/app" in block
    assert len(block) <= MAX_MAP_CHARS


def test_an_empty_project_renders_nothing() -> None:
    assert render_repo_map(build_repo_map(tempfile.mkdtemp(prefix="map-"))) == ""


def test_a_missing_root_is_not_an_error() -> None:
    m = build_repo_map(None)
    assert m.files == ()
    assert render_repo_map(m) == ""


# ── the rule: the map joins the CACHE KEY ──────────────────────────────────


def test_a_changed_map_invalidates_the_cache_key() -> None:
    a = build_prompt_plan(system_prompt="s", agent_id="a", repo_map="MAP-A", repo_map_version="aaa")
    b = build_prompt_plan(system_prompt="s", agent_id="a", repo_map="MAP-B", repo_map_version="bbb")
    c = build_prompt_plan(system_prompt="s", agent_id="a", repo_map="MAP-A", repo_map_version="aaa")
    assert a.cache_key != b.cache_key, "a changed map must invalidate the cache"
    assert a.cache_key == c.cache_key, "an unchanged map must NOT invalidate it"


def test_the_map_is_a_segment_in_the_plan() -> None:
    plan = build_prompt_plan(system_prompt="s", agent_id="a", repo_map="MAP", repo_map_version="abc")
    segment = plan.by_id("repo_map")
    assert segment is not None
    assert segment.content == "MAP"
    assert plan.to_dict()["repoMapVersion"] == "abc"


# ── the rule: the index's freshness is MEASURED ───────────────────────────


def test_is_fresh_is_not_a_hard_coded_true() -> None:
    """`is_fresh()` used to `return True` - an unmeasured claim about a cache."""
    import inspect

    from harness.code.intel.runtime import CodeIntelRuntime

    source = inspect.getsource(CodeIntelRuntime.is_fresh)
    body = source.split('"""')[-1]
    # The EVIDENCE: a background watcher that owns the index's freshness, and
    # an explicit "not fresh" for a workspace that has neither.
    assert "watcher" in body, "is_fresh does not look for the watcher that owns freshness"
    assert "state is None" in body, "is_fresh does not handle a workspace that was never indexed"


def test_the_engine_availability_is_published() -> None:
    """An optional layer that silently no-ops is a false capability."""
    from harness.code.intel.runtime import CodeIntelRuntime

    runtime = CodeIntelRuntime()
    status = runtime.status()
    assert "treeSitter" in status
    assert "available" in status["treeSitter"]
    assert "grammars" in status["treeSitter"]


# ── the rule: a map failure never breaks a run ────────────────────────────


def test_the_context_builder_never_raises() -> None:
    from harness.graph_context import _repo_map_context

    class _Emitter:
        def __init__(self) -> None:
            self.events: list[tuple[str, dict]] = []

        async def emit(self, event: str, data: dict) -> None:
            self.events.append((event, data))

    from harness.schemas import ModelSettings, RunInput, RunRequest

    request = RunRequest(
        runId="map-ctx",
        input=RunInput(query="find the main entry point"),
        modelSettings=ModelSettings(provider="ollama", model="llama3.1",
                                    base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    emitter = _Emitter()
    # No workspace at all.
    block, digest = asyncio.run(
        _repo_map_context(request, workspace=None, emitter=emitter)
    )
    assert block == ""
    assert digest is None


def test_the_context_builder_returns_the_map_and_its_digest() -> None:
    from harness.graph_context import _repo_map_context
    from harness.schemas import ModelSettings, RunInput, RunRequest
    from harness.code.workspace import ResolvedWorkspace, WorkspaceBinding

    class _Emitter:
        def __init__(self) -> None:
            self.events: list[tuple[str, dict]] = []

        async def emit(self, event: str, data: dict) -> None:
            self.events.append((event, data))

    root = _project(tempfile.mkdtemp(prefix="map-"))
    real = os.path.realpath(root)
    binding = WorkspaceBinding(id="ws_map", root=real, base_revision="unknown", strategy="checkout")
    workspace = ResolvedWorkspace(id="ws_map", root=real, base_revision="unknown",
                                  strategy="checkout", binding=binding)
    request = RunRequest(
        runId="map-ctx-2",
        input=RunInput(query="find the main entry point"),
        autonomy="edit_verify",
        modelSettings=ModelSettings(provider="ollama", model="llama3.1",
                                    base_url="http://localhost:11434/v1"),
        callbackBaseUrl="http://localhost:3000",
    )
    emitter = _Emitter()
    block, digest = asyncio.run(
        _repo_map_context(request, workspace=workspace, emitter=emitter)
    )
    assert "Repository map" in block
    assert digest and len(digest) == 16
    # The build is observable.
    assert any(event == "code.repo_map_built" for event, _ in emitter.events)
