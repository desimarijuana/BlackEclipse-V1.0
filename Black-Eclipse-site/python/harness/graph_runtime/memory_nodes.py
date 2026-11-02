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
ListRunner = Callable[[NodeExecContext, dict[str, Any]], dict[str, Any]]
UpdateRunner = Callable[[NodeExecContext, dict[str, Any]], dict[str, Any]]
ForgetRunner = Callable[[NodeExecContext, dict[str, Any]], dict[str, Any]]
_recall: Optional[RecallRunner] = None
_remember: Optional[RememberRunner] = None
_list: Optional[ListRunner] = None
_update: Optional[UpdateRunner] = None
_forget: Optional[ForgetRunner] = None


def set_memory_recall_runner(runner: Optional[RecallRunner]) -> None:
    global _recall
    _recall = runner


def set_memory_remember_runner(runner: Optional[RememberRunner]) -> None:
    global _remember
    _remember = runner


def set_memory_list_runner(runner: Optional[ListRunner]) -> None:
    global _list
    _list = runner


def set_memory_update_runner(runner: Optional[UpdateRunner]) -> None:
    global _update
    _update = runner


def set_memory_forget_runner(runner: Optional[ForgetRunner]) -> None:
    global _forget
    _forget = runner


def resolve_scope(raw: Any, context: NodeExecContext) -> str:
    """Resolve a graph memory scope without silently polluting `general`.

    `workflow` and `run` require the runtime to actually know that id; a missing
    id fails by name. Any other non-empty value is used as a literal scope.
    """
    value = str(raw or "general").strip().lower()
    if value == "general":
        return "general"
    if value == "workflow":
        if not context.workflow_id:
            raise ValueError("memory scope 'workflow' needs a saved workflow id in this run")
        return f"workflow:{context.workflow_id}"[:40]
    if value == "run":
        return f"run:{context.run_id}"[:40]
    if not value or len(value) > 40 or not all(c.isalnum() or c in "._:-" for c in value):
        raise ValueError(f"invalid memory scope {raw!r}")
    return value


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


def _memory_text(row: dict[str, Any]) -> str:
    return str(row.get("content") or row.get("text") or "").strip()


def _memory_type(row: dict[str, Any]) -> str:
    return str(row.get("memoryType") or row.get("memory_type") or "memory")


def _memory_importance(row: dict[str, Any]) -> float:
    try:
        return float(row.get("importance", 0.5))
    except (TypeError, ValueError):
        return 0.5


def exec_memory_context(context: NodeExecContext) -> dict[str, Any]:
    query = str(
        context.inputs.get("query") or context.config.get("query") or ""
    ).strip()
    if not query:
        raise ValueError("memory.context needs a query (wire one or fill Query)")
    if _recall is None:
        raise ValueError("the memory service is not configured in this graph runtime")
    try:
        limit = int(context.config.get("limit", 8))
        budget_tokens = int(context.config.get("budgetTokens", 1_200))
    except (TypeError, ValueError) as exc:
        raise ValueError("Limit and budget must be whole numbers") from exc
    limit = max(1, min(limit, 50))
    budget_chars = max(128, min(budget_tokens, 8_000)) * 4
    result = _recall(context, {
        "query": query,
        "types": _types(context.config.get("types")),
        "limit": limit,
        "scope": resolve_scope(context.config.get("scope"), context),
    })
    memories = result.get("memories") if isinstance(result, dict) else None
    if not isinstance(memories, list):
        raise ValueError("the memory service returned no memories list")
    style = str(context.config.get("format") or "bullets").strip().lower()
    if style not in ("bullets", "prose", "compact"):
        raise ValueError(f"unknown memory format {style!r}")

    ordered = sorted(memories, key=_memory_importance, reverse=True)
    lines: list[str] = []
    used = 0
    dropped = 0
    for row in ordered:
        if not isinstance(row, dict):
            continue
        text = _memory_text(row)
        if not text:
            continue
        kind = _memory_type(row)
        if style == "compact":
            line = f"[{kind}] {text}"
        elif style == "prose":
            line = f"{kind.capitalize()}: {text}"
        else:
            line = f"- ({kind}) {text}"
        if used + len(line) + 1 > budget_chars:
            dropped += 1
            continue
        lines.append(line)
        used += len(line) + 1
    block = "\n".join(lines)
    context.emit(
        f"memory context · {len(lines)} record(s) · {used} chars"
        + (f" · {dropped} dropped" if dropped else "")
    )
    return {
        "context": block,
        "memories": ordered,
        "count": len(lines),
        "dropped": dropped,
        "meta": {
            "budgetTokens": budget_tokens,
            "budgetChars": budget_chars,
            "format": style,
            "scope": resolve_scope(context.config.get("scope"), context),
        },
    }


def exec_memory_list(context: NodeExecContext) -> dict[str, Any]:
    if _list is None:
        raise ValueError("the memory service is not configured in this graph runtime")
    try:
        limit = int(context.config.get("limit", 50))
    except (TypeError, ValueError) as exc:
        raise ValueError("Limit must be a whole number") from exc
    result = _list(context, {
        "memoryType": str(context.config.get("memoryType") or "").strip(),
        "scope": resolve_scope(context.config.get("scope"), context),
        "status": str(context.config.get("status") or "").strip(),
        "subject": str(context.config.get("subject") or "").strip(),
        "limit": max(1, min(limit, 200)),
        "includeInactive": bool(context.config.get("includeInactive", True)),
    })
    memories = result.get("memories") if isinstance(result, dict) else None
    if not isinstance(memories, list):
        raise ValueError("the memory service returned no memories list")
    scopes = sorted({str(row.get("scope") or "") for row in memories if isinstance(row, dict)})
    types = sorted({_memory_type(row) for row in memories if isinstance(row, dict)})
    context.emit(f"listed {len(memories)} memory record(s)")
    return {
        "memories": memories,
        "count": len(memories),
        "scopes": [scope for scope in scopes if scope],
        "types": [kind for kind in types if kind],
    }


def _memory_id(context: NodeExecContext) -> str:
    value = context.inputs.get("memoryId") or context.config.get("memoryId")
    text = str(value or "").strip()
    if not text:
        raise ValueError("this memory node needs a memory id")
    return text


def exec_memory_update(context: NodeExecContext) -> dict[str, Any]:
    if context.test_run:
        raise ValueError(
            "memory.update changes durable memory; run it as an operator run "
            "(a test run never writes memory)"
        )
    if _update is None:
        raise ValueError("the memory service is not configured in this graph runtime")
    content = context.inputs.get("content")
    if content is None:
        content = context.config.get("content")
    content_text = str(content).strip() if content is not None else ""
    subject = str(context.config.get("subject") or "").strip()
    importance = None
    if bool(context.config.get("updateImportance", False)):
        importance_raw = context.config.get("importance")
        try:
            importance = float(importance_raw)
        except (TypeError, ValueError) as exc:
            raise ValueError("Importance must be a number") from exc
        if not 0.0 <= importance <= 1.0:
            raise ValueError("Importance must be between 0 and 1")
    if not content_text and not subject and importance is None:
        raise ValueError("memory.update needs content, a subject or an importance")
    result = _update(context, {
        "memoryId": _memory_id(context),
        "content": content_text or None,
        "subject": subject or None,
        "importance": importance,
    })
    memory = result.get("memory") if isinstance(result, dict) else None
    if not isinstance(memory, dict):
        raise ValueError("the memory service did not confirm the update")
    context.emit(f"updated memory {memory.get('id')}")
    return {"memory": memory, "updated": True}


def exec_memory_forget(context: NodeExecContext) -> dict[str, Any]:
    if context.test_run:
        raise ValueError(
            "memory.forget archives durable memory; run it as an operator run "
            "(a test run never writes memory)"
        )
    if _forget is None:
        raise ValueError("the memory service is not configured in this graph runtime")
    result = _forget(context, {
        "memoryId": _memory_id(context),
        "reason": str(context.config.get("reason") or "").strip() or None,
    })
    memory = result.get("memory") if isinstance(result, dict) else None
    if not isinstance(memory, dict):
        raise ValueError("the memory service did not confirm the archive")
    context.emit(f"archived memory {memory.get('id')}")
    return {"memory": memory, "forgotten": True}


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
        NodeDef(
            type="memory.context", version="1.0.0", label="Memory context",
            category="data",
            inputs=(PortDef(id="query", name="Query", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="context", name="Context", type=PortType.STRING),
                PortDef(id="memories", name="Memories", type=PortType.ARRAY),
                PortDef(id="count", name="Count", type=PortType.NUMBER),
                PortDef(id="dropped", name="Dropped", type=PortType.NUMBER),
                PortDef(id="meta", name="Meta", type=PortType.OBJECT),
            ),
            config_fields=(
                ConfigField("query", "string", "", max_length=2_000),
                ConfigField("types", "string", "", max_length=300),
                ConfigField("limit", "integer", 8, minimum=1, maximum=50),
                ConfigField("budgetTokens", "integer", 1_200, minimum=128, maximum=8_000),
                ConfigField("format", "enum", "bullets", enum=("bullets", "prose", "compact")),
                ConfigField("scope", "string", "general", max_length=40),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            timeout_ms=120_000,
            executor=exec_memory_context,
            metadata={"docs": (
                "Deterministic, budgeted prompt block from the ONE memory service. "
                "Lowest-importance records are dropped first and the drop count is "
                "reported; no model call is made."
            )},
        ),
        NodeDef(
            type="memory.list", version="1.0.0", label="List memories",
            category="data",
            inputs=(),
            outputs=(
                PortDef(id="memories", name="Memories", type=PortType.ARRAY),
                PortDef(id="count", name="Count", type=PortType.NUMBER),
                PortDef(id="scopes", name="Scopes", type=PortType.ARRAY),
                PortDef(id="types", name="Types", type=PortType.ARRAY),
            ),
            config_fields=(
                ConfigField("memoryType", "string", "", max_length=40),
                ConfigField("scope", "string", "general", max_length=40),
                ConfigField("status", "string", "", max_length=40),
                ConfigField("subject", "string", "", max_length=200),
                ConfigField("limit", "integer", 50, minimum=1, maximum=200),
                ConfigField("includeInactive", "boolean", True),
            ),
            capabilities=("research.read",),
            side_effects=SideEffect.READ,
            allowed_modes=_ALL,
            timeout_ms=60_000,
            executor=exec_memory_list,
            metadata={"docs": "Deterministic browse by scope/type/status; no semantic query and no model call."},
        ),
        NodeDef(
            type="memory.update", version="1.0.0", label="Update memory",
            category="data",
            inputs=(
                PortDef(id="memoryId", name="Memory id", type=PortType.STRING, optional=True),
                PortDef(id="content", name="Content", type=PortType.STRING, optional=True),
            ),
            outputs=(
                PortDef(id="memory", name="Memory", type=PortType.OBJECT),
                PortDef(id="updated", name="Updated", type=PortType.BOOLEAN),
            ),
            config_fields=(
                ConfigField("memoryId", "string", "", max_length=200),
                ConfigField("content", "string", "", max_length=4_000),
                ConfigField("subject", "string", "", max_length=200),
                ConfigField("updateImportance", "boolean", False),
                ConfigField("importance", "number", 0.5, minimum=0.0, maximum=1.0),
            ),
            capabilities=("memory.write",),
            side_effects=SideEffect.LOCAL_WRITE,
            allowed_modes=_ALL,
            timeout_ms=60_000,
            executor=exec_memory_update,
            metadata={"docs": (
                "Corrects one memory through the service (content/subject/importance). "
                "Operator-run only; the store's audit/conflict policy still applies."
            )},
        ),
        NodeDef(
            type="memory.forget", version="1.0.0", label="Forget memory",
            category="data",
            inputs=(PortDef(id="memoryId", name="Memory id", type=PortType.STRING, optional=True),),
            outputs=(
                PortDef(id="memory", name="Memory", type=PortType.OBJECT),
                PortDef(id="forgotten", name="Forgotten", type=PortType.BOOLEAN),
            ),
            config_fields=(
                ConfigField("memoryId", "string", "", max_length=200),
                ConfigField("reason", "string", "", max_length=500),
            ),
            capabilities=("memory.write",),
            side_effects=SideEffect.LOCAL_WRITE,
            allowed_modes=_ALL,
            timeout_ms=60_000,
            executor=exec_memory_forget,
            metadata={"docs": (
                "Soft-forgets one memory (archived, never hard-deleted) through the "
                "service. Operator-run only."
            )},
        ),
    ]


__all__ = [
    "MEMORY_TYPES",
    "build_memory_nodes",
    "exec_memory_context",
    "exec_memory_forget",
    "exec_memory_list",
    "exec_memory_recall",
    "exec_memory_remember",
    "exec_memory_update",
    "resolve_scope",
    "set_memory_forget_runner",
    "set_memory_list_runner",
    "set_memory_recall_runner",
    "set_memory_remember_runner",
    "set_memory_update_runner",
]
