"""MCP server configuration contract and host threat boundary (Phase 5A).

This module defines the *typed* configuration for a local stdio MCP server and
the effect classes that decide whether a discovered tool may run. It deliberately
carries no I/O beyond reading an optional JSON file; the client/manager live in
`client.py` / `manager.py`.

Host execution controls defined here are mandatory and are NOT a finance-domain
allowlist. A user may connect any MCP server and select any tool for any finance
workflow; the controls only govern how a process is launched and called.

Security rules encoded here (never relaxed by a server):
  * an executable + separate argument array — never a shell command string;
  * only an explicit env allowlist/values reach the child, never the whole
    Eclipse process environment, vault, model credentials or callback token;
  * a relative working directory resolves against the repository root, so it
    cannot be redirected by the launch cwd;
  * discovery is not activation — `enabled` defaults to False and only an
    explicit per-tool selection may register a tool;
  * startup/catalog/call/output/concurrency budgets are bounded.

Secret VALUES are held in memory only. They are never logged, persisted, emitted
in an event, or returned in a tool result; `redact_secrets` scrubs them from any
diagnostic text that leaves the manager.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from ..eclipse_memory.config import repo_root

log = logging.getLogger("harness.mcp.config")

# Effect classes. Only `read` is activatable in this slice; the others are
# declared so a later approval gate (5G) can bind consent to them.
EffectClass = Literal["read", "write", "external_action", "unknown"]

# Configuration file resolution:
#   1. HARNESS_MCP_CONFIG (absolute or relative path);
#   2. <repo root>/mcp-servers.json.
# A missing file is not an error: MCP is simply not configured.
CONFIG_ENV_VAR = "HARNESS_MCP_CONFIG"
CONFIG_FILENAME = "mcp-servers.json"

# Bounds (host controls). Values outside are clamped, never trusted.
STARTUP_TIMEOUT_FLOOR_MS = 100
STARTUP_TIMEOUT_CEILING_MS = 120_000
CALL_TIMEOUT_FLOOR_MS = 100
CALL_TIMEOUT_CEILING_MS = 120_000
OUTPUT_LIMIT_FLOOR_BYTES = 1_000
OUTPUT_LIMIT_CEILING_BYTES = 1_000_000
MAX_TOOLS_CEILING = 500

DEFAULT_STARTUP_TIMEOUT_MS = 10_000
DEFAULT_CATALOG_TIMEOUT_MS = 15_000
DEFAULT_CALL_TIMEOUT_MS = 20_000
DEFAULT_OUTPUT_LIMIT_BYTES = 100_000
DEFAULT_MAX_CONCURRENCY = 4
DEFAULT_MAX_TOOLS = 200

# Description/schema sizes are bounded so an MCP catalog cannot flood the model
# context or the database. A tool exceeding these is skipped with a diagnostic.
MAX_TOOL_DESCRIPTION_CHARS = 4_000
MAX_TOOL_SCHEMA_CHARS = 40_000


def _clamp(value: int | None, floor: int, ceiling: int, default: int) -> int:
    if value is None:
        return default
    try:
        return max(floor, min(int(value), ceiling))
    except (TypeError, ValueError):
        return default


class MCPServerConfig(BaseModel):
    """One local stdio MCP server, as explicitly configured by the operator.

    There is no implicit default: an absent `enabled` is False and an absent
    `selected_tools` selects nothing. A discovered tool is inert until named.
    """

    id: str = Field(min_length=1, max_length=64)
    # A stable, human-meaningful label; defaults to `id`.
    name: Optional[str] = None
    # Executable + argument array as SEPARATE values. Never a shell string.
    command: str = Field(min_length=1)
    args: list[str] = Field(default_factory=list)
    # Explicit env values for THIS server only (e.g. a scoped API base URL).
    env: dict[str, str] = Field(default_factory=dict)
    # Host env var NAMES to copy through to the child (values resolved at spawn).
    env_allowlist: list[str] = Field(default_factory=list)
    # Optional working directory; a relative value resolves against repo_root().
    cwd: Optional[str] = None
    enabled: bool = False
    # Explicit include list. Discovery never activates; only this selects.
    selected_tools: list[str] = Field(default_factory=list)
    # Optional declared effect per original tool name. Overrides annotations when
    # present; an undeclared tool with no read-only annotation is `unknown`.
    tool_effects: dict[str, EffectClass] = Field(default_factory=dict)
    # Budgets / bounds.
    startup_timeout_ms: int = DEFAULT_STARTUP_TIMEOUT_MS
    catalog_timeout_ms: int = DEFAULT_CATALOG_TIMEOUT_MS
    call_timeout_ms: int = DEFAULT_CALL_TIMEOUT_MS
    output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    max_tools: int = DEFAULT_MAX_TOOLS
    # Protocol/catalog version metadata when the operator pins one.
    protocol_version: Optional[str] = None
    # Free-form, non-secret operator notes (never used for authorization).
    description: Optional[str] = None

    # Accept BOTH snake_case (the config file / Python callers) and camelCase
    # (the TS front door sends camelCase). Extra fields are rejected so a typo
    # cannot silently configure nothing.
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )

    @field_validator("args")
    @classmethod
    def _no_nul_args(cls, value: list[str]) -> list[str]:
        for arg in value:
            if "\x00" in arg:
                raise ValueError("argument contains a NUL byte")
        return value

    @field_validator("command")
    @classmethod
    def _no_shell_meta(cls, value: str) -> str:
        # This is a defensive check, not the security boundary: the boundary is
        # that we never use a shell and pass an argv list (see client.py). A NUL
        # byte is refused here so it can never reach the spawn.
        if "\x00" in value:
            raise ValueError("command contains a NUL byte")
        return value

    def limits(self) -> dict[str, int]:
        return {
            "startupTimeoutMs": _clamp(self.startup_timeout_ms, STARTUP_TIMEOUT_FLOOR_MS, STARTUP_TIMEOUT_CEILING_MS, DEFAULT_STARTUP_TIMEOUT_MS),
            "catalogTimeoutMs": _clamp(self.catalog_timeout_ms, STARTUP_TIMEOUT_FLOOR_MS, STARTUP_TIMEOUT_CEILING_MS, DEFAULT_CATALOG_TIMEOUT_MS),
            "callTimeoutMs": _clamp(self.call_timeout_ms, CALL_TIMEOUT_FLOOR_MS, CALL_TIMEOUT_CEILING_MS, DEFAULT_CALL_TIMEOUT_MS),
            "outputLimitBytes": _clamp(self.output_limit_bytes, OUTPUT_LIMIT_FLOOR_BYTES, OUTPUT_LIMIT_CEILING_BYTES, DEFAULT_OUTPUT_LIMIT_BYTES),
            "maxConcurrency": max(1, min(int(self.max_concurrency or DEFAULT_MAX_CONCURRENCY), 16)),
            "maxTools": max(1, min(int(self.max_tools or DEFAULT_MAX_TOOLS), MAX_TOOLS_CEILING)),
        }

    def resolve_cwd(self) -> Optional[str]:
        """Resolve the working directory.

        Rule: a relative path is anchored to the repository root (the app that
        owns the databases), NOT the process cwd, so a server launched from a
        different directory cannot change its meaning. An absolute path is used
        as-is. A resolved path that does not exist is treated as unconfigured.
        """
        if not self.cwd:
            return None
        candidate = self.cwd
        if not os.path.isabs(candidate):
            candidate = os.path.join(repo_root(), candidate)
        candidate = os.path.abspath(candidate)
        return candidate if os.path.isdir(candidate) else None

    def resolve_environment(self) -> dict[str, str]:
        """The explicit env for the child: allowlisted host vars + declared values.

        Only names in `env_allowlist` are copied from the host; the process
        environment, settings vault, model credentials and callback token are
        never forwarded wholesale.
        """
        resolved: dict[str, str] = {}
        for name in self.env_allowlist:
            if not name or "\x00" in name:
                continue
            value = os.environ.get(name)
            if value is not None:
                resolved[name] = value
        resolved.update({k: v for k, v in self.env.items() if k})
        return resolved

    def secret_values(self) -> list[str]:
        """Values that must never appear in a log/event/result (for redaction)."""
        return [v for v in self.env.values() if v]

    def public_dict(self) -> dict[str, Any]:
        """A secret-free, camelCase view safe to return over the API/UI.

        `env` VALUES are omitted; only the configured KEYS are listed, so an
        operator can see what is scoped without the secret leaving the runtime.
        The wire shape is camelCase to match the TS front door.
        """
        return {
            "id": self.id,
            "name": self.name,
            "command": self.command,
            "args": list(self.args),
            "env": {k: None for k in self.env},
            "envKeys": sorted(self.env.keys()),
            "envAllowlist": list(self.env_allowlist),
            "secretCount": len(self.secret_values()),
            "cwd": self.cwd,
            "enabled": self.enabled,
            "selectedTools": list(self.selected_tools),
            "toolEffects": dict(self.tool_effects),
            "protocolVersion": self.protocol_version,
            "description": self.description,
            "limits": self.limits(),
        }


class MCPConfigError(ValueError):
    """A configuration file could not be parsed or contained no valid servers."""


def config_path(explicit: Optional[str] = None) -> str:
    override = explicit or os.environ.get(CONFIG_ENV_VAR)
    if override:
        return os.path.abspath(override)
    return os.path.join(repo_root(), CONFIG_FILENAME)


def load_mcp_configs(explicit: Optional[str] = None) -> tuple[list[MCPServerConfig], list[dict[str, str]]]:
    """Load configured servers. Never raises on a missing file.

    Returns `(servers, diagnostics)`. A malformed entry is reported as a
    diagnostic and skipped, so one bad server cannot crash runtime startup.
    """
    path = config_path(explicit)
    diagnostics: list[dict[str, str]] = []
    if not os.path.isfile(path):
        return [], diagnostics
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        diagnostics.append({"server": "*", "code": "config_unreadable", "message": str(exc)})
        return [], diagnostics

    if isinstance(raw, dict):
        raw_servers = raw.get("servers")
    else:
        raw_servers = raw
    if not isinstance(raw_servers, list):
        diagnostics.append({"server": "*", "code": "config_invalid", "message": "expected a list of servers"})
        return [], diagnostics

    servers: list[MCPServerConfig] = []
    seen: set[str] = set()
    for entry in raw_servers:
        try:
            server = MCPServerConfig(**entry)
        except Exception as exc:  # noqa: BLE001 - a bad entry must not abort loading
            diagnostics.append(
                {"server": str((entry or {}).get("id") if isinstance(entry, dict) else "?"), "code": "invalid_server", "message": str(exc)}
            )
            continue
        if server.id in seen:
            diagnostics.append({"server": server.id, "code": "duplicate_server", "message": "duplicate server id ignored"})
            continue
        seen.add(server.id)
        servers.append(server)
    return servers, diagnostics


def redact_secrets(text: str, secrets: list[str]) -> str:
    """Scrub configured secret values from diagnostic text.

    A no-op for empty/short values (a 1-character secret would corrupt the text
    it is meant to protect). This is defense in depth; the primary rule is
    "never put a secret in a message in the first place".
    """
    out = str(text)
    for secret in secrets:
        if secret and len(secret) >= 4 and secret in out:
            out = out.replace(secret, "***")
    return out


def write_mcp_configs(
    servers: list[MCPServerConfig], explicit: Optional[str] = None
) -> str:
    """Persist the full server list to the config file atomically.

    Written with a temp file + replace so a crash mid-write cannot leave a
    truncated config. The config file may contain scoped env VALUES (secrets),
    so it must never be committed; it lives at the repo root alongside the other
    gitignored operational stores (see `.gitignore`).
    """
    path = config_path(explicit)
    payload = {"servers": [s.model_dump() for s in servers]}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    return path


def upsert_mcp_config(
    server: MCPServerConfig,
    explicit: Optional[str] = None,
    env_keys: Optional[list[str]] = None,
) -> list[MCPServerConfig]:
    """Insert or replace one server by id, preserving the others.

    Env values are write-only: the UI never receives them, so it cannot resend
    them. `env_keys`, when supplied, is the authoritative set of key names that
    should exist for this server; each key keeps its incoming value if provided,
    otherwise its previously-stored value. Keys absent from `env_keys` are
    removed. When `env_keys` is None, existing keys not mentioned in the incoming
    `env` are preserved (a merge), so a card-level enable/disable cannot drop a
    secret.
    """
    servers, _ = load_mcp_configs(explicit)
    existing_env: dict[str, str] = {}
    for existing in servers:
        if existing.id == server.id:
            existing_env = dict(existing.env)
            break

    if env_keys is not None:
        merged: dict[str, str] = {}
        for key in env_keys:
            if key in server.env:
                merged[key] = server.env[key]
            elif key in existing_env:
                merged[key] = existing_env[key]
        server = server.model_copy(update={"env": merged})
    else:
        merged = {**existing_env, **server.env}
        server = server.model_copy(update={"env": merged})

    replaced = False
    updated: list[MCPServerConfig] = []
    for existing in servers:
        if existing.id == server.id:
            updated.append(server)
            replaced = True
        else:
            updated.append(existing)
    if not replaced:
        updated.append(server)
    write_mcp_configs(updated, explicit)
    return updated


def remove_mcp_config(server_id: str, explicit: Optional[str] = None) -> bool:
    """Remove a server by id. Returns whether anything was removed."""
    servers, _ = load_mcp_configs(explicit)
    remaining = [s for s in servers if s.id != server_id]
    if len(remaining) == len(servers):
        return False
    write_mcp_configs(remaining, explicit)
    return True

__all__ = [
    "EffectClass",
    "MCPServerConfig",
    "MCPConfigError",
    "config_path",
    "load_mcp_configs",
    "write_mcp_configs",
    "upsert_mcp_config",
    "remove_mcp_config",
    "redact_secrets",
    "MAX_TOOL_DESCRIPTION_CHARS",
    "MAX_TOOL_SCHEMA_CHARS",
]
