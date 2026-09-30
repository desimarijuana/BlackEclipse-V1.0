"""On-disk MCP tool-schema cache for lazy startup (Phase 6, Milestone 2).

A `lazy` server registers its tools from this cache at boot and spawns only on
first call, so boot cost and network `npx` fetches are not paid for a server that
is never used. Entries are keyed by server id + a **fingerprint of the
connection-defining config** (command/args/url/transport/selected filters), so a
changed config never reuses a stale schema. `lazy` defaults off; a missing or
stale entry falls back to a normal eager connect.

The cache lives under `.black-eclipse/` (gitignored) at the repo root. It holds
only discovered tool metadata — never a secret.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from typing import Any, Optional

from ..eclipse_memory.config import repo_root

log = logging.getLogger("harness.mcp.schema_cache")

_CACHE_DIRNAME = ".black-eclipse"
_CACHE_FILENAME = "mcp_schema_cache.json"


def cache_path() -> str:
    override = os.environ.get("HARNESS_MCP_CACHE")
    if override:
        return os.path.abspath(override)
    return os.path.join(repo_root(), _CACHE_DIRNAME, _CACHE_FILENAME)


def config_fingerprint(config: Any) -> str:
    """Stable hash of the connection-defining parts of a server config."""
    selected = config.selected_tools
    if isinstance(selected, dict):
        include = sorted(str(x) for x in (selected.get("include") or []))
        exclude = sorted(str(x) for x in (selected.get("exclude") or []))
    else:
        include = sorted(str(x) for x in (selected or []))
        exclude = []
    payload = {
        "command": config.command,
        "args": list(config.args or []),
        "url": config.url,
        "transport": config.transport,
        "include": include,
        "exclude": exclude,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _load_all() -> dict[str, Any]:
    path = cache_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError) as exc:
        log.debug("could not read MCP schema cache: %s", exc)
        return {}


def _save_all(data: dict[str, Any]) -> None:
    path = cache_path()
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
    os.replace(tmp, path)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def get_entry(server_id: str, fingerprint: str) -> Optional[dict[str, Any]]:
    """A cached entry when the fingerprint matches, else None."""
    entry = _load_all().get(server_id)
    if not isinstance(entry, dict) or entry.get("fingerprint") != fingerprint:
        return None
    return entry


def is_stale(server_id: str, fingerprint: str) -> bool:
    """True when an entry EXISTS for this server but its fingerprint is stale.

    Lets a caller tell "no cache yet" apart from "the config changed since the
    cache was written", so a stale cache is reported as needing a connect rather
    than being treated as absent (and never silently served).
    """
    entry = _load_all().get(server_id)
    return isinstance(entry, dict) and entry.get("fingerprint") != fingerprint


def tools_from_entry(entry: dict[str, Any]) -> list[dict[str, Any]]:
    """Cached tool rows as `{name, description, inputSchema, annotations}`."""
    tools = entry.get("tools")
    return list(tools) if isinstance(tools, list) else []


def write_entry(server_id: str, fingerprint: str, tools: list[dict[str, Any]]) -> None:
    """Persist the discovered catalog after a successful live connect."""
    data = _load_all()
    data[server_id] = {
        "fingerprint": fingerprint,
        "tools": tools,
        "written_at": time.time(),
    }
    _save_all(data)


def clear_entry(server_id: str) -> None:
    data = _load_all()
    if server_id in data:
        del data[server_id]
        _save_all(data)


def catalog_to_cache_rows(descriptors: dict[str, Any]) -> list[dict[str, Any]]:
    """Serialize descriptor data into the cache's tool-row shape."""
    rows: list[dict[str, Any]] = []
    for descriptor in descriptors.values():
        rows.append({
            "name": descriptor.original_name,
            "description": descriptor.description,
            "inputSchema": descriptor.input_schema,
            "effect": descriptor.effect,
            "effectSource": descriptor.effect_source,
        })
    return rows


__all__ = [
    "cache_path",
    "config_fingerprint",
    "get_entry",
    "is_stale",
    "write_entry",
    "clear_entry",
    "tools_from_entry",
    "catalog_to_cache_rows",
]
