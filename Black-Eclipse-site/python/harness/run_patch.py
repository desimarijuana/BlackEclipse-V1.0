"""One serialization rule for a `HarnessRun` patch.

Both writers — `AgentMemoryStore.update_run` (plain) and
`run_lease.fenced_update_run` (lease-fenced) — build their SQL here. They must
never diverge: when the fenced writer kept its own allowlist and bound dict
fields raw, SQLite raised `ProgrammingError`, the exception was swallowed, and
every terminal write was silently dropped (runs stayed `running` until the stall
watchdog relabelled them RUN_STALLED).
"""

from __future__ import annotations

import json
from typing import Any, Mapping

#: Columns a run patch may write.
RUN_PATCH_FIELDS = frozenset({
    "status", "output", "error", "modelSteps", "toolCalls", "toolErrors",
    "promptTokens", "completionTokens", "totalTokens",
    "provider", "model", "startedAt", "finishedAt", "research", "memory",
    "context", "codeVerification", "vision", "documents", "images", "video",
    "sessionId", "profileId", "projectId",
    "autonomy", "workspaceId", "surface",
})

#: Columns stored as JSON text. A dict bound to a SQLite parameter raises, so
#: every writer must encode these exactly once, here.
RUN_JSON_FIELDS = frozenset({
    "error", "research", "memory", "context", "codeVerification", "vision",
    "documents", "images", "video", "surface",
})


def run_patch_sql(patch: Mapping[str, Any]) -> tuple[list[str], list[Any]]:
    """Translate a run patch into `SET` fragments and bound parameters.

    Pure, so the two writers share one serialization rule.
    """
    sets: list[str] = []
    params: list[Any] = []
    for key, value in patch.items():
        if key not in RUN_PATCH_FIELDS:
            continue
        sets.append(f"{key} = ?")
        if key in RUN_JSON_FIELDS and value is not None:
            params.append(json.dumps(value))
        else:
            params.append(value)
    return sets, params


__all__ = ["RUN_JSON_FIELDS", "RUN_PATCH_FIELDS", "run_patch_sql"]
