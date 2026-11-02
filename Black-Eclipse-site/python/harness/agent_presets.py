"""User-defined agent presets (Graph Studio Phase 1).

The three built-in presets stay in `agents.py`. This module adds an
operator-authored preset: a name, a system prompt, an explicit tool allowlist and
a step bound, stored on the runtime's own `agent-memory.db` and versioned
append-only.

A graph node pins `agent@version`. Editing a preset appends a new version; a
pinned run keeps executing the snapshot it was saved against. Tool names are
validated against the LIVE registry at write time, and a non-read tool requires
an explicit `allowEffectful` acknowledgement — a preset cannot silently widen
itself by naming an effectful tool.

This store never executes a turn. `bootstrap._agent_runner` resolves the pinned
snapshot into an `AgentConfig` and runs it through the existing agent plane.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any, Optional

from .persistence import now_iso

MAX_PROMPT = 20_000
MAX_DESCRIPTION = 500
MAX_TOOLS = 200
MAX_STEPS = 32

_SCHEMA = """
CREATE TABLE IF NOT EXISTS AgentPreset (
  id               TEXT PRIMARY KEY,
  name             TEXT NOT NULL,
  description      TEXT NOT NULL DEFAULT '',
  systemPrompt     TEXT NOT NULL,
  toolsJson        TEXT NOT NULL DEFAULT '[]',
  maxSteps         INTEGER NOT NULL DEFAULT 8,
  allowMcpTools    INTEGER NOT NULL DEFAULT 0,
  allowPluginTools INTEGER NOT NULL DEFAULT 0,
  allowEffectful   INTEGER NOT NULL DEFAULT 0,
  currentVersion   INTEGER NOT NULL DEFAULT 1,
  archived         INTEGER NOT NULL DEFAULT 0,
  createdAt        TEXT NOT NULL,
  updatedAt        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS AgentPresetVersion (
  presetId     TEXT NOT NULL,
  version      INTEGER NOT NULL,
  snapshotJson TEXT NOT NULL,
  contentHash  TEXT NOT NULL,
  createdAt    TEXT NOT NULL,
  PRIMARY KEY (presetId, version)
);
CREATE INDEX IF NOT EXISTS idx_agent_preset_updated
  ON AgentPreset(archived, updatedAt);
CREATE INDEX IF NOT EXISTS idx_agent_preset_version
  ON AgentPresetVersion(presetId, version);
"""


def _clean_text(value: Any, field: str, limit: int, *, required: bool = False) -> str:
    text = str(value or "").strip()
    if required and not text:
        raise ValueError(f"{field} is required")
    if len(text) > limit:
        raise ValueError(f"{field} must be at most {limit} characters")
    return text


def _clean_tools(value: Any, registry: Any) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError("tools must be an array of tool names")
    out: list[str] = []
    seen: set[str] = set()
    known = set(registry.names())
    for raw in value:
        name = str(raw or "").strip()
        if not name:
            continue
        if name not in known:
            raise ValueError(f"unknown tool {name!r}")
        if name in seen:
            continue
        seen.add(name)
        out.append(name)
    if len(out) > MAX_TOOLS:
        raise ValueError(f"a preset may name at most {MAX_TOOLS} tools")
    return out


def _effects(tools: list[str], registry: Any) -> list[str]:
    effects: set[str] = set()
    for name in tools:
        definition = registry.get(name)
        if definition is None:
            continue
        effects.add(str(definition.permission or "read"))
    return sorted(effects)


def _payload(raw: dict[str, Any], registry: Any) -> dict[str, Any]:
    tools = _clean_tools(raw.get("tools"), registry)
    allow_effectful = bool(raw.get("allowEffectful"))
    non_read = [
        name
        for name in tools
        if (getattr(registry.get(name), "permission", "read") or "read") != "read"
    ]
    if non_read and not allow_effectful:
        raise ValueError(
            "these tools have a write/external effect; tick 'Allow effectful tools' to "
            f"include them: {', '.join(non_read[:8])}"
        )
    try:
        max_steps = int(raw.get("maxSteps", 8))
    except (TypeError, ValueError) as exc:
        raise ValueError("maxSteps must be a number") from exc
    if not 1 <= max_steps <= MAX_STEPS:
        raise ValueError(f"maxSteps must be between 1 and {MAX_STEPS}")
    return {
        "name": _clean_text(raw.get("name"), "name", 80, required=True),
        "description": _clean_text(raw.get("description"), "description", MAX_DESCRIPTION),
        "systemPrompt": _clean_text(raw.get("systemPrompt"), "systemPrompt", MAX_PROMPT, required=True),
        "tools": tools,
        "maxSteps": max_steps,
        "allowMcpTools": bool(raw.get("allowMcpTools")),
        "allowPluginTools": bool(raw.get("allowPluginTools")),
        "allowEffectful": allow_effectful,
    }


def _hash(snapshot: dict[str, Any]) -> str:
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return "ap_" + hashlib.sha256(encoded).hexdigest()[:16]


def _row(row: Any, snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        **snapshot,
        "id": row["id"],
        "version": int(row["version"]),
        "contentHash": row["contentHash"],
        "createdAt": row["createdAt"],
        "archived": bool(row["archived"]),
        "currentVersion": int(row["currentVersion"]),
        "updatedAt": row["updatedAt"],
    }


class AgentPresetStore:
    def __init__(self, store: Any, registry: Any) -> None:
        self._store = store
        self._registry = registry
        self._ensure_schema()

    @property
    def _db(self):
        return self._store._db

    def _ensure_schema(self) -> None:
        self._db.executescript(_SCHEMA)
        self._db.commit()

    def _snapshot(self, preset_id: str, version: int) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM AgentPresetVersion WHERE presetId=? AND version=?",
            (preset_id, version),
        ).fetchone()
        if row is None:
            return None
        try:
            snapshot = json.loads(row["snapshotJson"])
        except (TypeError, ValueError):
            return None
        return snapshot if isinstance(snapshot, dict) else None

    def _write_version(self, preset_id: str, version: int, snapshot: dict[str, Any]) -> str:
        digest = _hash(snapshot)
        self._db.execute(
            """INSERT INTO AgentPresetVersion
               (presetId, version, snapshotJson, contentHash, createdAt)
               VALUES (?, ?, ?, ?, ?)""",
            (preset_id, version, json.dumps(snapshot), digest, now_iso()),
        )
        return digest

    def create(self, raw: dict[str, Any]) -> dict[str, Any]:
        snapshot = _payload(raw, self._registry)
        preset_id = f"agt_{uuid.uuid4().hex[:10]}"
        now = now_iso()
        self._db.execute(
            """INSERT INTO AgentPreset
               (id, name, description, systemPrompt, toolsJson, maxSteps,
                allowMcpTools, allowPluginTools, allowEffectful, currentVersion,
                archived, createdAt, updatedAt)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)""",
            (
                preset_id,
                snapshot["name"],
                snapshot["description"],
                snapshot["systemPrompt"],
                json.dumps(snapshot["tools"]),
                snapshot["maxSteps"],
                1 if snapshot["allowMcpTools"] else 0,
                1 if snapshot["allowPluginTools"] else 0,
                1 if snapshot["allowEffectful"] else 0,
                now,
                now,
            ),
        )
        digest = self._write_version(preset_id, 1, snapshot)
        self._db.commit()
        return self.get(preset_id) or {
            **snapshot, "id": preset_id, "version": 1, "contentHash": digest,
            "createdAt": now, "updatedAt": now, "archived": False, "currentVersion": 1,
        }

    def update(self, preset_id: str, raw: dict[str, Any]) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM AgentPreset WHERE id=? AND archived=0", (preset_id,)
        ).fetchone()
        if row is None:
            return None
        snapshot = _payload(raw, self._registry)
        version = int(row["currentVersion"]) + 1
        digest = self._write_version(preset_id, version, snapshot)
        self._db.execute(
            """UPDATE AgentPreset SET name=?, description=?, systemPrompt=?,
               toolsJson=?, maxSteps=?, allowMcpTools=?, allowPluginTools=?,
               allowEffectful=?, currentVersion=?, updatedAt=? WHERE id=?""",
            (
                snapshot["name"],
                snapshot["description"],
                snapshot["systemPrompt"],
                json.dumps(snapshot["tools"]),
                snapshot["maxSteps"],
                1 if snapshot["allowMcpTools"] else 0,
                1 if snapshot["allowPluginTools"] else 0,
                1 if snapshot["allowEffectful"] else 0,
                version,
                now_iso(),
                preset_id,
            ),
        )
        self._db.commit()
        return self.get(preset_id, version)

    def get(self, preset_id: str, version: Optional[int] = None) -> Optional[dict[str, Any]]:
        row = self._db.execute("SELECT * FROM AgentPreset WHERE id=?", (preset_id,)).fetchone()
        if row is None:
            return None
        target = int(version) if version else int(row["currentVersion"])
        snapshot = self._snapshot(preset_id, target)
        if snapshot is None:
            return None
        payload = _row(
            {
                "version": target,
                "contentHash": "",
                "createdAt": row["createdAt"],
                "archived": row["archived"],
                "currentVersion": row["currentVersion"],
                "updatedAt": row["updatedAt"],
                "id": row["id"],
            },
            snapshot,
        )
        version_row = self._db.execute(
            "SELECT contentHash FROM AgentPresetVersion WHERE presetId=? AND version=?",
            (preset_id, target),
        ).fetchone()
        payload["contentHash"] = version_row["contentHash"] if version_row else ""
        return payload

    def list(self, *, include_archived: bool = False) -> list[dict[str, Any]]:
        where = "" if include_archived else "WHERE archived=0"
        rows = self._db.execute(
            f"SELECT * FROM AgentPreset {where} ORDER BY updatedAt DESC"
        ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            snapshot = self._snapshot(row["id"], int(row["currentVersion"]))
            if snapshot is None:
                continue
            tools = list(snapshot.get("tools") or [])
            out.append({
                "id": row["id"],
                "name": snapshot.get("name") or row["name"],
                "description": snapshot.get("description") or "",
                "version": int(row["currentVersion"]),
                "maxSteps": int(snapshot.get("maxSteps") or 8),
                "toolCount": len(tools),
                "effects": _effects(tools, self._registry),
                "archived": bool(row["archived"]),
                "updatedAt": row["updatedAt"],
                "createdAt": row["createdAt"],
            })
        return out

    def versions(self, preset_id: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            """SELECT version, contentHash, createdAt FROM AgentPresetVersion
               WHERE presetId=? ORDER BY version DESC""",
            (preset_id,),
        ).fetchall()
        return [
            {
                "version": int(row["version"]),
                "contentHash": row["contentHash"],
                "createdAt": row["createdAt"],
            }
            for row in rows
        ]

    def archive(self, preset_id: str) -> bool:
        cursor = self._db.execute(
            "UPDATE AgentPreset SET archived=1, updatedAt=? WHERE id=? AND archived=0",
            (now_iso(), preset_id),
        )
        self._db.commit()
        return cursor.rowcount > 0

    def catalog(self) -> list[dict[str, Any]]:
        """Registered tools with their effect class, for the preset editor."""
        out: list[dict[str, Any]] = []
        for name in sorted(self._registry.names()):
            definition = self._registry.get(name)
            if definition is None:
                continue
            out.append({
                "name": name,
                "description": str(definition.description or "")[:240],
                "permission": str(definition.permission or "read"),
                "risk": str(definition.risk or "low"),
            })
        return out


_STORE: Optional[AgentPresetStore] = None


def set_preset_store(store: Optional[AgentPresetStore]) -> None:
    global _STORE
    _STORE = store


def get_preset_store() -> Optional[AgentPresetStore]:
    return _STORE


def agent_config_from_preset(
    preset: dict[str, Any], *, max_steps: Optional[int] = None,
) -> "AgentConfig":
    """Project a stored preset snapshot onto the run plane's `AgentConfig`.

    The ONE place a preset row becomes a runnable agent. Graph nodes
    (`bootstrap._agent_runner`) and ordinary runs (`graph.resolve_agent`, which
    is what a bot's scheduled `run_agent` uses) must agree, or a preset would
    work in one surface and fail in the other.
    """
    from .schemas import AgentConfig  # noqa: PLC0415 - schemas is a leaf module

    steps = int(max_steps or preset.get("maxSteps") or 8)
    return AgentConfig(
        id=str(preset["id"]),
        name=str(preset["name"]),
        systemPrompt=str(preset["systemPrompt"]),
        tools=list(preset.get("tools") or []),
        maxSteps=max(1, min(steps, MAX_STEPS)),
        allowMcpTools=bool(preset.get("allowMcpTools")),
        allowPluginTools=bool(preset.get("allowPluginTools")),
    )


__all__ = [
    "AgentPresetStore",
    "agent_config_from_preset",
    "get_preset_store",
    "set_preset_store",
]
