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

Secret VALUES in `env` are persisted ONLY in the local `mcp-servers.json`
(gitignored, owner-restricted where the OS supports it) because the secure
settings vault is a TypeScript/Prisma store this Python process cannot read, and
the Python SDK requires the value to spawn the child. They are never logged,
emitted in an event, or returned by the API (which exposes only key NAMES);
`redact_secrets` scrubs them from any diagnostic text that leaves the manager.
See the ADR (ADR-H40) for the vault-integration limitation and the planned fix.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, field_validator
from pydantic.alias_generators import to_camel

from ..eclipse_memory.config import repo_root

log = logging.getLogger("harness.mcp.config")

# Effect classes. Only `read` is activatable in this slice; the others are
# declared so a later approval gate (5G) can bind consent to them.
EffectClass = Literal["read", "write", "external_action", "unknown"]

# Transports. `stdio` launches a local subprocess; `http` connects to a remote
# Streamable-HTTP MCP endpoint; `sse` connects to a remote SSE endpoint. Both
# remote transports share the same vault-backed auth, SSRF pre-check and
# lifecycle.
MCPServerTransport = Literal["stdio", "http", "sse"]

# Coarse trust tier (Milestone 1). `full` is the default; anything else is
# treated as `untrusted` (fail-closed). An untrusted server requires a per-call
# approval for EVERY non-read call, regardless of `enabled_effects`, and its own
# annotations can never satisfy any gate.
TRUST_FULL = "full"
TRUST_UNTRUSTED = "untrusted"

# Keepalive / recycle floors (seconds). Values below are clamped up.
KEEPALIVE_FLOOR_S = 10
IDLE_TIMEOUT_FLOOR_S = 30
MAX_LIFETIME_FLOOR_S = 60

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


@dataclass(frozen=True)
class ResolvedConnection:
    """Connection-defining fields after `${VAR}` interpolation.

    Kept separate from the persisted config so a resolved value is never written
    back to `mcp-servers.json` and the config stays shareable.
    """

    command: str
    args: list[str]
    url: Optional[str]
    auth: Optional[dict[str, Any]]
    ssl_verify: Union[bool, str]


class MCPServerConfig(BaseModel):
    """One local stdio MCP server, as explicitly configured by the operator.

    There is no implicit default: an absent `enabled` is False and an absent
    `selected_tools` selects nothing. A discovered tool is inert until named.
    """

    id: str = Field(min_length=1, max_length=64)
    # A stable, human-meaningful label; defaults to `id`.
    name: Optional[str] = None
    # Transport: a local subprocess (`stdio`) or a remote Streamable-HTTP endpoint.
    transport: MCPServerTransport = "stdio"
    # Executable + argument array as SEPARATE values. Never a shell string.
    # Required for `stdio`; ignored for `http`.
    command: str = ""
    args: list[str] = Field(default_factory=list)
    # Remote endpoint URL. Required for `http` (https, or http on loopback).
    url: Optional[str] = None
    # Header auth for `http`. The VALUE is a vault secret NAME resolved at
    # connect time; a literal value may be given via `env`-style `env`? No —
    # header values are always secret references so a token is never stored here.
    #   {"kind": "header", "name": "Authorization", "prefix": "Bearer ", "secretRef": "x"}
    #   {"kind": "query", "name": "api_key", "secretRef": "x"}   (query params)
    auth: Optional[dict[str, Any]] = None
    # Explicit env values for THIS server only (e.g. a scoped API base URL).
    # Non-secret values only; use `secret_refs` for anything secret.
    env: dict[str, str] = Field(default_factory=dict)
    # Host env var NAMES to copy through to the child (values resolved at spawn).
    env_allowlist: list[str] = Field(default_factory=list)
    # Environment variable NAME → vault secret NAME. The value is resolved from
    # the encrypted vault (served over the authenticated read-only bridge) at
    # spawn time and is never written to this config file, a log, an event, or a
    # run trace. This is the preferred way to give a server a credential.
    secret_refs: dict[str, str] = Field(default_factory=dict)
    # Optional working directory; a relative value resolves against repo_root().
    cwd: Optional[str] = None
    enabled: bool = False
    # Coarse trust tier. `full` (default) keeps the existing operator-declared
    # effect rules. Any other value — including a typo — is treated as
    # `untrusted` (fail-closed): every non-read call needs a per-call approval
    # regardless of `enabled_effects`, and server annotations never satisfy a
    # gate. This is *additional* to — never a replacement for — the effect rules.
    trust: str = TRUST_FULL
    # Explicit include list, or `{include: [...], exclude: [...]}` with
    # fnmatch-style globs (include wins over exclude). Discovery never activates;
    # only this selects. An empty include list selects nothing.
    selected_tools: Union[list[str], dict[str, list[str]]] = Field(default_factory=list)
    # Optional declared effect per original tool name. This is the ONLY trusted
    # source of an effect: a server's own `readOnlyHint` is untrusted metadata
    # and can never, by itself, activate a tool.
    tool_effects: dict[str, EffectClass] = Field(default_factory=dict)
    # The catalog digest the operator last reviewed/confirmed. A tool activates
    # only when the live catalog digest equals this, so a changed tool set,
    # description or schema invalidates prior selection until re-confirmed.
    confirmed_catalog_digest: Optional[str] = None
    # Optional declaration that a selected MCP tool is a native DATA SOURCE for a
    # retrieval data type (e.g. {"get_quote": "current_quote"}). Only a declared
    # tool is adapted into the native `RetrievalSource` contract; an undeclared
    # tool stays directly callable by the model and is never withheld.
    data_source_tools: dict[str, str] = Field(default_factory=dict)
    # Effect classes the operator has opted in to for THIS server. Defaults to
    # {"read"} only. A non-read effect (write/external_action) additionally
    # requires a per-call approval (5G); enabling it here is the standing opt-in.
    enabled_effects: list[str] = Field(default_factory=lambda: ["read"])
    # Budgets / bounds.
    startup_timeout_ms: int = DEFAULT_STARTUP_TIMEOUT_MS
    catalog_timeout_ms: int = DEFAULT_CATALOG_TIMEOUT_MS
    call_timeout_ms: int = DEFAULT_CALL_TIMEOUT_MS
    output_limit_bytes: int = DEFAULT_OUTPUT_LIMIT_BYTES
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY
    max_tools: int = DEFAULT_MAX_TOOLS
    # Lifecycle (Milestone 2). `lazy` registers tools from an on-disk schema
    # cache at boot and spawns only on first call. `keepalive_interval` pings a
    # live remote session. `idle_timeout_seconds`/`max_lifetime_seconds` recycle
    # a stdio child. All default to off unless set.
    lazy: bool = False
    keepalive_interval: Optional[int] = None
    idle_timeout_seconds: Optional[int] = None
    max_lifetime_seconds: Optional[int] = None
    # TLS controls (Milestone 3). `ssl_verify` is True | False | a CA-bundle
    # path. mTLS uses `client_cert`/`client_key` (a combined PEM, or
    # `[cert, key]`, or `[cert, key, passphrase]`).
    ssl_verify: Union[bool, str] = True
    client_cert: Optional[str] = None
    client_key: Optional[Union[str, list[str]]] = None
    # Capability toggles (Milestone 4). Resources/prompts utility tools are
    # registered only when the live session advertises the capability AND the
    # operator has set the toggle true. Default off = fail-closed (discovery is
    # not activation).
    tools: dict[str, bool] = Field(default_factory=dict)
    # Optional per-server narrowing of the resource URI schemes this server may
    # read. The global allowlist is a hard CEILING: a server can only ever remove
    # schemes from it, never add one. An empty/unset list means "no narrowing"
    # (the global list applies); a non-empty list is intersected with the global
    # list, so an unknown scheme can never broaden access.
    resource_schemes: list[str] = Field(default_factory=list)
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

    @field_validator("command", "url")
    @classmethod
    def _no_nul(cls, value: Optional[str]) -> Optional[str]:
        # Defensive, not the boundary: we never use a shell, and the http URL is
        # validated by the SSRF guard. A NUL byte is refused so it cannot reach a
        # spawn or an HTTP client.
        if value is not None and "\x00" in value:
            raise ValueError("value contains a NUL byte")
        return value

    def model_post_init(self, __context: Any) -> None:  # noqa: D401 - pydantic hook
        # A transport must be fully specified: stdio needs a command, remote needs
        # a URL. Enforced here (not a field validator) so the error is one clear
        # message and all transports share the same model.
        if self.transport == "stdio":
            if not self.command or not self.command.strip():
                raise ValueError("stdio transport requires `command`")
        elif self.transport in ("http", "sse"):
            if not self.url or not self.url.strip():
                raise ValueError(f"{self.transport} transport requires `url`")
            if self.auth is not None:
                if not isinstance(self.auth, dict) or self.auth.get("kind") not in ("header", "query", "oauth"):
                    raise ValueError("auth must be {kind: 'header'|'query'|'oauth', name, secretRef}")
                if self.auth.get("kind") in ("header", "query"):
                    if not self.auth.get("name") or not self.auth.get("secretRef"):
                        raise ValueError("auth requires `name` and `secretRef`")
                # oauth stores its token in the encrypted vault keyed by server id;
                # no named secret is required (a redirectUri may be supplied).

    def is_untrusted(self) -> bool:
        """True unless `trust` is exactly `full` (fail-closed on a typo)."""
        return str(self.trust or "").strip().lower() != TRUST_FULL

    def resolve_selected(self, available: list[str]) -> set[str]:
        """Resolve `selected_tools` into the concrete set of original tool names.

        Accepts the legacy list form (exact names, byte-for-byte unchanged) and
        the object form `{include, exclude}` with fnmatch-style globs. Include
        wins over exclude; an empty/missing include selects nothing.
        """
        import fnmatch

        selected = self.selected_tools
        if isinstance(selected, dict):
            include = [str(x) for x in (selected.get("include") or [])]
            exclude = [str(x) for x in (selected.get("exclude") or [])]
            chosen: set[str] = set()
            for pattern in include:
                for name in available:
                    if fnmatch.fnmatchcase(name, pattern):
                        chosen.add(name)
            for pattern in exclude:
                for name in list(chosen):
                    if fnmatch.fnmatchcase(name, pattern):
                        chosen.discard(name)
            return chosen
        names = [str(x) for x in (selected or [])]
        return {name for name in available if name in set(names)}

    def tool_enabled(self, capability: str) -> bool:
        """Whether a utility capability (resources|prompts) is enabled."""
        return bool((self.tools or {}).get(capability))

    def _interpolate_local(self, text: str) -> str:
        from .interpolation import interpolate

        if not text:
            return text
        return interpolate(text)[0]

    def resolved_connection(self) -> "ResolvedConnection":
        """Interpolate the connection-defining fields with the fail-closed rule.

        Remote `url`/`auth` values refuse on an unresolved reference (naming the
        variable); local stdio `command`/`args` keep the literal placeholder. A
        stdio server whose command is a `${VAR}` must resolve it, or the spawn
        would run a literal placeholder — that is reported as a refusal too,
        since a command cannot be a placeholder.
        """
        from .interpolation import InterpolationError, interpolate, interpolate_remote

        command = self._interpolate_local(self.command)
        args = [self._interpolate_local(a) for a in self.args]
        url = self.url
        auth = self.auth
        if self.transport == "stdio" and command != self.command and "${" in self.command:
            result, unresolved = interpolate(self.command)
            if unresolved:
                raise InterpolationError(unresolved[0], "command")
            command = result
        if self.transport in ("http", "sse"):
            if url:
                url = interpolate_remote(url, "url")
            if isinstance(auth, dict):
                auth = dict(auth)
                for key in ("name", "prefix", "secretRef"):
                    if isinstance(auth.get(key), str):
                        auth[key] = interpolate_remote(auth[key], f"auth.{key}")
        ssl_verify = self.ssl_verify
        if isinstance(ssl_verify, str) and ssl_verify:
            from .interpolation import interpolate as _i
            ssl_verify = _i(os.path.expanduser(ssl_verify))[0]
        return ResolvedConnection(
            command=command,
            args=args,
            url=url,
            auth=auth,
            ssl_verify=ssl_verify,
        )

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

    def resolve_environment(self, resolved_secrets: Optional[dict[str, str]] = None) -> dict[str, str]:
        """The explicit env for the child: allowlisted host vars + declared values
        + resolved vault secrets.

        Only names in `env_allowlist` are copied from the host; the process
        environment, settings vault, model credentials and callback token are
        never forwarded wholesale. `resolved_secrets` maps an env var NAME to its
        resolved value (from the encrypted vault — see ADR-H41); when a reference
        is unresolved it is simply omitted, never guessed. `${VAR}` in a declared
        value is interpolated locally (a literal placeholder is kept when unset).
        """
        resolved: dict[str, str] = {}
        for name in self.env_allowlist:
            if not name or "\x00" in name:
                continue
            value = os.environ.get(name)
            if value is not None:
                resolved[name] = value
        resolved.update({k: self._interpolate_local(v) for k, v in self.env.items() if k})
        for name, value in (resolved_secrets or {}).items():
            if name and value:
                resolved[name] = value
        return resolved

    def secret_values(self) -> list[str]:
        """Values that must never appear in a log/event/result (for redaction)."""
        return [v for v in self.env.values() if v]

    def secret_ref_names(self) -> list[str]:
        """Vault secret NAMES referenced by this server (not values)."""
        names = [v for v in self.secret_refs.values() if v]
        auth = self.auth or {}
        ref = auth.get("secretRef") if isinstance(auth, dict) else None
        if ref:
            names.append(str(ref))
        return names

    def requires_node_runtime(self) -> bool:
        """Heuristic: does this stdio server likely need Node/npx?

        True for `npx`/`node`/`npm` commands, so diagnostics can tell a user to
        install Node.js. Not a hard requirement check by itself.
        """
        return self.transport == "stdio" and self.command in ("npx", "node", "npm")

    def public_dict(self) -> dict[str, Any]:
        """A secret-free, camelCase view safe to return over the API/UI.

        `env` VALUES are omitted; only the configured KEYS are listed, so an
        operator can see what is scoped without the secret leaving the runtime.
        The wire shape is camelCase to match the TS front door.
        """
        return {
            "id": self.id,
            "name": self.name,
            "transport": self.transport,
            "command": self.command,
            "args": list(self.args),
            "url": self.url,
            # Auth metadata WITHOUT the secret value: the kind/name/prefix and the
            # vault secret NAME only. The resolved token is never in a response.
            "auth": (
                {
                    "kind": (self.auth or {}).get("kind"),
                    "name": (self.auth or {}).get("name"),
                    "prefix": (self.auth or {}).get("prefix"),
                    "secretRef": (self.auth or {}).get("secretRef"),
                }
                if isinstance(self.auth, dict)
                else None
            ),
            "env": {k: None for k in self.env},
            "envKeys": sorted(self.env.keys()),
            "envAllowlist": list(self.env_allowlist),
            # Vault secret REFERENCES: env var name → secret name. Names only;
            # values live encrypted in the vault and are never returned.
            "secretRefs": {k: v for k, v in self.secret_refs.items()},
            "secretRefNames": sorted(self.secret_refs.values()),
            "secretCount": len(self.secret_values()),
            "cwd": self.cwd,
            "enabled": self.enabled,
            "trust": TRUST_UNTRUSTED if self.is_untrusted() else TRUST_FULL,
            "untrusted": self.is_untrusted(),
            "selectedTools": (
                list(self.selected_tools) if isinstance(self.selected_tools, list) else {
                    "include": list(self.selected_tools.get("include") or []),
                    "exclude": list(self.selected_tools.get("exclude") or []),
                }
            ),
            "toolEffects": dict(self.tool_effects),
            "enabledEffects": list(self.enabled_effects),
            "confirmedCatalogDigest": self.confirmed_catalog_digest,
            "dataSourceTools": dict(self.data_source_tools),
            "lazy": self.lazy,
            "keepaliveInterval": self.keepalive_interval,
            "idleTimeoutSeconds": self.idle_timeout_seconds,
            "maxLifetimeSeconds": self.max_lifetime_seconds,
            "sslVerify": self.ssl_verify if isinstance(self.ssl_verify, bool) else "custom-ca",
            "clientCertConfigured": bool(self.client_cert),
            "tools": dict(self.tools),
            "resourceSchemes": list(self.resource_schemes),
            "protocolVersion": self.protocol_version,
            "description": self.description,
            # Raw, operator-set bounds (not the clamped values in `limits`), so
            # the wire is lossless: a view -> model -> view round trip preserves
            # exactly what the operator configured.
            "startupTimeoutMs": self.startup_timeout_ms,
            "catalogTimeoutMs": self.catalog_timeout_ms,
            "callTimeoutMs": self.call_timeout_ms,
            "outputLimitBytes": self.output_limit_bytes,
            "maxConcurrency": self.max_concurrency,
            "maxTools": self.max_tools,
            # The effective, clamped values actually applied at runtime.
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
        # Static screening runs BEFORE the entry is parsed or spawned, so a
        # hand-edited config cannot smuggle a shell/exec payload past the type
        # layer. A refused entry is skipped with a structured diagnostic.
        from .screening import refusals, screen_entry

        blocked = refusals(screen_entry(entry))
        if blocked:
            first = blocked[0].to_public()
            diagnostics.append({
                "server": str((entry or {}).get("id") if isinstance(entry, dict) else "?"),
                "code": first["code"],
                "status": first["status"],
                "message": first["message"],
                "recovery": first["recovery"],
            })
            continue
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


def screen_rejections(entry: dict[str, Any]) -> list[dict[str, str]]:
    """Refusing findings for a raw entry, as structured diagnostics (save path)."""
    from .screening import refusals, screen_entry

    return [f.to_public() for f in refusals(screen_entry(entry))]


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
    _restrict_permissions(path)
    return path


def _restrict_permissions(path: str) -> None:
    """Best-effort owner-only permissions on the config file.

    The file may hold scoped env values, so it is written 0600 where the OS
    supports POSIX modes. On Windows this is a limited no-op (the file inherits
    the user profile's ACL); it is defense in depth, not a substitute for the
    gitignore + secret-free API boundary.
    """
    try:
        os.chmod(path, 0o600)
    except OSError:  # pragma: no cover - some filesystems reject chmod
        log.debug("could not restrict permissions on %s", path)


def upsert_mcp_config(
    server: MCPServerConfig,
    explicit: Optional[str] = None,
    env_keys: Optional[list[str]] = None,
) -> list[MCPServerConfig]:
    """Insert or replace one server by id, preserving the others.

    The merge contract is: **absent means preserve; explicitly present means
    replace — including an explicit `null`, `false`, `{}` or `[]` for
    clearing.** A caller that omits a field (an older UI, an API client, a
    script) must not reset it, while the UI can still clear a field because it
    always sends every field it owns. This distinction is what makes a save
    unable to silently widen a server's authority: `trust`, `enabled_effects`,
    `tool_effects`, `data_source_tools`, `confirmed_catalog_digest` and
    `selected_tools` are preserved unless a caller deliberately supplies them.
    The rule is implemented from the incoming model's `model_fields_set`, never
    from `if value is not None` (which cannot tell "absent" from "present but
    null").

    Env values are the one exception and stay write-only: the UI never receives
    them, so it cannot resend them. `env_keys`, when supplied, is the
    authoritative set of key names that should exist for this server; each key
    keeps its incoming value if provided, otherwise its previously-stored value.
    Keys absent from `env_keys` are removed. When `env_keys` is None, existing
    keys not mentioned in the incoming `env` are preserved (a merge), so a
    card-level enable/disable cannot drop a secret.
    """
    servers, _ = load_mcp_configs(explicit)
    existing: Optional[MCPServerConfig] = next((s for s in servers if s.id == server.id), None)
    existing_env: dict[str, str] = dict(existing.env) if existing is not None else {}

    # Absent means preserve: every field the caller did not mention keeps its
    # stored value. `model_fields_set` distinguishes an omitted field from one
    # explicitly supplied as `null`/`false`/`{}`/`[]`.
    if existing is not None:
        supplied = server.model_fields_set
        preserved = {
            name: getattr(existing, name)
            for name in MCPServerConfig.model_fields
            if name not in supplied
        }
        if preserved:
            server = server.model_copy(update=preserved)

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
