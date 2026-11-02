"""Memory nodes: read the app's memory into a graph, and write a durable note.

Both are thin adapters over the ONE Eclipse memory service
(`AgenticService.memory`): same policy, same dedupe/conflict handling, same
retention. `bootstrap.py` binds the runners at boot so tests substitute a fake.

`memory.remember` writes durable state, so it is an operator-run node: a test
run is refused in the executor rather than silently polluting the user's memory.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from .model import ExecutionMode, PortDef, PortType, SideEffect
from .registry import ConfigField, NodeDef, NodeExecContext

_ALL = tuple(ExecutionMode)

# Mirrors `eclipse_memory.store.MEMORY_TYPES`. Kept as a literal so this module
# imports no store; `test_graph_memory_nodes.py` asserts the two agree.
MEMORY_TYPES = (
    "episodic", "semantic", "procedural", "preference",
    "constraint", "correction", "observation", "summary",
)

RecallRunner = Callable[[NodeExecContext, dict[str, Any]], dict[str, Any]]
RememberRunner = Callable[[NodeExecContext, dict[str, Any]], dict[str, Any]]
_recall: Optional[RecallRunner] = None
_remember: Optional[RememberRunner] = None


def set_memory_recall_runner(runner: Optional[RecallRunner]) -> None:
    global _recall
    _recall = runner


def set_memory_remember_runner(runner: Optional[RememberRunner]) -> None:
    global _remember
    _remember = runner


def _types(raw: Any) -> list[str]:
    parts = raw if isinstance(raw, list) else str(raw or "").split(",")
    out: list[str] = []
    for part in parts:
        value = str(part).strip().lower()
        if not value:
            continue
        if value not in MEMORY_TYPES:
            raise ValueError(
                f"unknown memory type {value!r}; expected one of {', '.join(MEMORY_TYPES)}"
            )
        if value not in out:
            out.append(value)
    return out


def exec_memory_recall(context: NodeExecContext) -> dict[str, Any]:
    query = str(
        context.inputs.get("query") or context.config.get("query") or ""
    ).strip()
    if not query:
        raise ValueError("memory.recall needs a query (wire one or fill Query)")
    if _recall is None:
        raise ValueError("the memory service is not configured in this graph runtime")
    try:
        limit = int(context.config.get("limit", 8))
    except (TypeError, ValueError) as exc:
        raise ValueError("Limit must be a whole number") from exc
    args = {
        "query": query,
        "types": _types(context.config.get("types")),
        "limit": max(1, min(limit, 50)),
        "scope": str(context.config.get("scope") or "").strip() or None,
    }
    result = _recall(context, args)
    memories = result.get("memories") if isinstance(result, dict) else None
    if not isinstance(memories, list):
        raise ValueError("the memory service returned no memories list")
    context_text = str((result or {}).get("context") or "")
    context.emit(f"recalled {len(memories)} memory record(s)")
    return {"memories": memories, "context": context_text, "count": len(memories)}


def exec_memory_remember(context: NodeExecContext) -> dict[str, Any]:
    if context.test_run:
        # A test run must not leave durable state behind.
        raise ValueError(
            "memory.remember writes durable memory; run it as an operator run "
            "(a test run never writes memory)"
        )
    content = str(
        context.inputs.get("content") or context.config.get("content") or ""
    ).strip()
    if not content:
        raise ValueError("memory.remember needs content (wire one or fill Content)")
    if len(content) > 4_000:
        raise ValueError("memory content exceeds 4 000 characters")
    if _remember is None:
        raise ValueError("the memory service is not configured in this graph runtime")
    memory_type = str(context.config.get("memoryType") or "observation").strip().lower()
    if memory_type not in MEMORY_TYPES:
        raise ValueError(
            f"unknown memory type {memory_type!r}; expected one of {', '.join(MEMORY_TYPES)}"
        )
    try:
        importance = float(context.config.get("importance", 0.5))
    except (TypeError, ValueError) as exc:
        raise ValueError("Importance must be a number") from exc
    if not 0.0 <= importance <= 1.0:
        raise ValueError("Importance must be between 0 and 1")
    args = {
        "content": content,
        "memoryType": memory_type,
        "scope": str(context.config.get("scope") or "general").strip() or "general",
        "subject": str(context.config.get("subject") or "").strip() or None,
        "importance": importance,
    }
    result = _remember(context, args)
    memory = result.get("memory") if isinstance(result, dict) else None
    if not isinstance(memory, dict) or not memory.get("id"):
        raise ValueError("the memory service did not confirm a written record")
    context.emit(f"remembered {memory_type} {memory['id']}")
    return {"memory": memory, "written": True}


def build_memory_nodes() -> list[NodeDef]:
    return [
        NodeDef(
            type="memory.recall", version="1.0.0", label="Recall memory",
            category="data",
            inputs=(PortDef(id="query", name="Query", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="memories", name="Memories", type=PortType.ARRAY),
                PortDef(id="context", name="Context", type=PortType.STRING),
                PortDef(id="count", name="Count", type=PortType.NUMBER),
            ),
            config_fields=(
                ConfigField("query", "string", "", max_length=2_000),
                ConfigField("types", "string", "", max_length=300),
                ConfigField("limit", "integer", 8, minimum=1, maximum=50),
                ConfigField("scope", "string", "", max_length=40),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            timeout_ms=120_000,
            executor=exec_memory_recall,
            metadata={
                "docs": (
                    "Reads the ONE memory service (`retrieve`) with its policy, dedupe "
                    "and recall-deny rules. `context` is the same bounded prompt block "
                    "an agent would receive. A missing query fails by name."
                ),
            },
        ),
        NodeDef(
            type="memory.remember", version="1.0.0", label="Remember",
            category="data",
            inputs=(PortDef(id="content", name="Content", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="memory", name="Memory", type=PortType.OBJECT),
                PortDef(id="written", name="Written", type=PortType.BOOLEAN),
            ),
            config_fields=(
                ConfigField("content", "string", "", max_length=4_000),
                ConfigField("memoryType", "enum", "observation", enum=MEMORY_TYPES),
                ConfigField("scope", "string", "general", max_length=40),
                ConfigField("subject", "string", "", max_length=200),
                ConfigField("importance", "number", 0.5, minimum=0.0, maximum=1.0),
            ),
            capabilities=("memory.write",),
            side_effects=SideEffect.LOCAL_WRITE,
            allowed_modes=_ALL,
            timeout_ms=120_000,
            executor=exec_memory_remember,
            metadata={
                "docs": (
                    "Writes one durable memory through `write_memory` (dedupe, conflict "
                    "resolution and retention are the service's). Operator-run only: a "
                    "test run is refused so it cannot leave state behind."
                ),
            },
        ),
    ]


__all__ = [
    "MEMORY_TYPES",
    "build_memory_nodes",
    "exec_memory_recall",
    "exec_memory_remember",
    "set_memory_recall_runner",
    "set_memory_remember_runner",
]
