"""Skill store — now a compatibility shim over Eclipse-Memory.

Phase 3 originally kept skill lifecycle state in `agent-memory.db`. Eclipse-
Memory is the dedicated control database, so the skill tables now live in
`eclipse-memory.db` and there is exactly **one** persistence implementation:
`harness.eclipse_memory.store.EclipseMemoryStore`.

This module re-exports that class as `SkillStore` so every existing import and
call site keeps working unchanged. `SkillStore(path)` still opens an explicitly
given file (used by the test suite for isolation); `SkillStore()` resolves the
configured `eclipse-memory.db`.
"""

from __future__ import annotations

from ..eclipse_memory.store import EclipseMemoryStore

# Backwards-compatible alias. Skill operations are a subset of the
# EclipseMemoryStore API, so this is a true alias — not a second registry.
SkillStore = EclipseMemoryStore

# `SCHEMA` was the old inline DDL string. The canonical schema now lives in
# `harness.eclipse_memory.schema`; keep the name importable for compatibility.
from ..eclipse_memory.schema import MIGRATIONS  # noqa: E402

SCHEMA = "\n".join(statement for _version, statements in MIGRATIONS for statement in statements)

__all__ = ["SkillStore", "SCHEMA"]
