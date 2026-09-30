"""MCP setup diagnostics (Phase 5 — actionable setup).

Setup fails for mundane, fixable reasons: `npx`/`node` not installed, a vault
secret missing, a remote endpoint unreachable, a server that starts but exposes
no selected tool, Windows temp-directory permissions. Every check here returns a
STRUCTURED diagnostic with:

  * `code`     — a stable machine category,
  * `status`   — ok | warn | error | skipped,
  * `message`  — what is wrong, in plain language,
  * `recovery` — the exact next step the user can take.

Nothing here activates a server or runs a tool; it only inspects. It never logs
or returns secret values.
"""

from __future__ import annotations

import os
import shutil
import socket
from dataclasses import asdict, dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse

from .config import MCPServerConfig
from .ssrf import check_outbound_url

OK = "ok"
WARN = "warn"
ERROR = "error"
SKIPPED = "skipped"


@dataclass
class Diagnostic:
    code: str
    status: str
    message: str
    recovery: str = ""

    def to_public(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ServerDiagnostics:
    server_id: str
    transport: str
    checks: list[Diagnostic] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(c.status == ERROR for c in self.checks)

    def to_public(self) -> dict[str, Any]:
        return {
            "serverId": self.server_id,
            "transport": self.transport,
            "ok": self.ok,
            "checks": [c.to_public() for c in self.checks],
        }


def _which(executable: str) -> Optional[str]:
    return shutil.which(executable)


def _toolchain_check(executable: str, label: str, recovery: str) -> Diagnostic:
    found = _which(executable)
    if found:
        return Diagnostic(f"{executable}_available", OK, f"{label} found at {found}")
    return Diagnostic(f"{executable}_missing", ERROR, f"{label} was not found on this machine", recovery)


def _secret_resolution_check(config: MCPServerConfig, resolved: Optional[dict[str, bool]]) -> Diagnostic:
    names = config.secret_ref_names()
    if not names:
        return Diagnostic("secrets_not_required", OK, "No vault secrets are required")
    if resolved is None:
        return Diagnostic(
            "secrets_unverified", WARN,
            f"This server needs {len(names)} vault secret(s): {', '.join(names)}",
            "Open Settings › MCP Servers › Secret vault and confirm each name exists.",
        )
    missing = [n for n in names if not resolved.get(n)]
    if missing:
        return Diagnostic(
            "secrets_missing", ERROR,
            f"Missing vault secret(s): {', '.join(missing)}",
            "Add the missing secret by name under Settings › MCP Servers › Secret vault.",
        )
    return Diagnostic("secrets_ok", OK, "All referenced vault secrets are present")


def _network_check(url: str) -> Diagnostic:
    safe, reason = check_outbound_url(url)
    if not safe:
        return Diagnostic(
            "endpoint_unsafe", ERROR,
            f"The endpoint was refused by the safety check: {reason}",
            "Use an https URL for a public host. Private/loopback endpoints are only allowed for local testing.",
        )
    parsed = urlparse(url)
    host = parsed.hostname or ""
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((host, port), timeout=4):
            pass
    except OSError as exc:
        return Diagnostic(
            "endpoint_unreachable", ERROR,
            f"Could not reach {host}:{port} ({exc.__class__.__name__})",
            "Check your network/VPN and that the MCP endpoint is running and reachable.",
        )
    return Diagnostic("endpoint_reachable", OK, f"Reached {host}:{port}")


def _tls_check(config: MCPServerConfig) -> Optional[Diagnostic]:
    """Fail fast when a configured CA bundle / client cert path is missing."""
    if config.transport == "stdio":
        return None
    ssl_verify = config.ssl_verify
    if ssl_verify is False:
        return Diagnostic(
            "tls_verification_disabled", WARN,
            "TLS certificate verification is DISABLED for this server",
            "Only use ssl_verify=false for a trusted local test endpoint; prefer a CA bundle.",
        )
    if isinstance(ssl_verify, str) and ssl_verify:
        path = os.path.expanduser(ssl_verify)
        if not os.path.isfile(path):
            return Diagnostic(
                "ca_bundle_missing", ERROR,
                f"The CA bundle was not found: {path}",
                "Point ssl_verify at an existing PEM file, or set it to true for the system store.",
            )
    if config.client_cert:
        cert = os.path.expanduser(config.client_cert)
        if not os.path.isfile(cert):
            return Diagnostic(
                "client_cert_missing", ERROR,
                f"The client certificate was not found: {cert}",
                "Provide an existing PEM path for client_cert (or clear mTLS).",
            )
    return None


def _auth_check(config: MCPServerConfig, token_status: Optional[dict[str, Any]] = None) -> Optional[Diagnostic]:
    """OAuth-specific checks when the server uses `auth.kind == "oauth"`.

    `token_status` (when the caller owns the vault) is
    `{configured, expired, refreshFailed, rejected}`. Distinguishes "rejected our
    credentials" from "unreachable".
    """
    auth = config.auth if isinstance(config.auth, dict) else None
    if not auth or auth.get("kind") != "oauth":
        return None
    if token_status is None:
        return Diagnostic(
            "oauth_unverified", WARN,
            "This server uses OAuth; token status could not be verified",
            "Use Connect / log in under Settings › MCP Servers to start the OAuth flow.",
        )
    if token_status.get("rejected"):
        return Diagnostic(
            "oauth_rejected", ERROR,
            "The server rejected our credentials (not an outage)",
            "Re-authenticate: Settings › MCP Servers › Connect (or the login action) to obtain a new token.",
        )
    if token_status.get("refreshFailed"):
        return Diagnostic(
            "oauth_refresh_failed", ERROR,
            "The OAuth token could not be refreshed",
            "Re-authenticate to obtain a new refresh token; check the server's OAuth app settings.",
        )
    if not token_status.get("configured"):
        return Diagnostic(
            "oauth_not_logged_in", WARN,
            "No OAuth token is stored for this server",
            "Connect / log in under Settings › MCP Servers to authorize access.",
        )
    if token_status.get("expired"):
        return Diagnostic(
            "oauth_expired", WARN,
            "The stored OAuth token is expired",
            "It should refresh automatically; if it does not, re-authenticate.",
        )
    return Diagnostic("oauth_ok", OK, "OAuth token present and current")


def _credential_check(verify: Optional[dict[str, Any]]) -> Optional[Diagnostic]:
    """Surface the last operator-triggered Verify verdict, when one exists.

    A `credentials_rejected` server is CONNECTED yet cannot complete a call;
    this is deliberately distinct from `endpoint_unreachable` (a network check)
    and `server_not_connected` (a process/state check).
    """
    if not verify:
        return None
    code = verify.get("code")
    if code == "credentials_rejected":
        detail = ""
        if verify.get("providerStatus") is not None:
            detail = f" (status {verify['providerStatus']}"
            if verify.get("providerCode"):
                detail += f", {verify['providerCode']}"
            detail += ")"
        return Diagnostic(
            "credentials_rejected", ERROR,
            f"The server rejected our credentials{detail}; it is connected but cannot complete a call",
            "Fix the credential (vault secret / OAuth sign-in), then Verify again.",
        )
    if code == "credentials_valid":
        return Diagnostic("credentials_valid", OK, "A read call succeeded, so the credential works")
    if code == "verify_inconclusive":
        return Diagnostic("verify_inconclusive", WARN, "Verify could not confirm the credential",
                          "Check the server state and the tool's arguments, then Verify again.")
    return None


def check_server(
    config: MCPServerConfig,
    *,
    resolved_secrets: Optional[dict[str, bool]] = None,
    connection_state: Optional[str] = None,
    discovered_tools: Optional[int] = None,
    selected_tools: Optional[int] = None,
    token_status: Optional[dict[str, Any]] = None,
    verify: Optional[dict[str, Any]] = None,
    tools_discovered: Optional[int] = None,
    tools_kept: Optional[int] = None,
) -> ServerDiagnostics:
    """Run all setup checks for one configured server (pure inspection)."""
    out = ServerDiagnostics(server_id=config.id, transport=config.transport)

    if config.is_untrusted():
        out.checks.append(Diagnostic(
            "server_untrusted", WARN,
            "This server is marked untrusted: every non-read call requires a per-call approval.",
            "Only declare effects you intend; annotate/confirm is not enough for an untrusted server.",
        ))

    if config.transport == "stdio":
        if not config.command:
            out.checks.append(Diagnostic("command_missing", ERROR, "No command is configured",
                                         "Set the executable the server runs (e.g. `npx` or `python`)."))
        else:
            recovery = (
                f"Install {config.command} (or use a tool that exposes it), then Test again."
            )
            out.checks.append(_toolchain_check(config.command, f"Command `{config.command}`", recovery))
            if config.requires_node_runtime():
                out.checks.append(_toolchain_check(
                    "npx", "Node/npx (npx servers need Node.js)",
                    "Install Node.js 20+ (https://nodejs.org), reopen the app, then Test again.",
                ))
    else:
        if not config.url:
            out.checks.append(Diagnostic("url_missing", ERROR, "No endpoint URL is configured",
                                         "Set the https endpoint URL for the remote server."))
        else:
            out.checks.append(_network_check(config.url))
        tls = _tls_check(config)
        if tls is not None:
            out.checks.append(tls)

    out.checks.append(_secret_resolution_check(config, resolved_secrets))

    auth_check = _auth_check(config, token_status)
    if auth_check is not None:
        out.checks.append(auth_check)

    credential_check = _credential_check(verify)
    if credential_check is not None:
        out.checks.append(credential_check)

    if connection_state is not None:
        if connection_state == "connected":
            out.checks.append(Diagnostic("server_connected", OK, "Server connected and responded to discovery"))
        elif connection_state == "lazy":
            out.checks.append(Diagnostic(
                "server_lazy", WARN, "Server is lazy: tools are registered from cache and not yet connected",
                "Call one of its tools (or Test connection) to spawn it; the first call connects.",
            ))
        elif connection_state == "unavailable":
            out.checks.append(Diagnostic(
                "server_unavailable", ERROR, "Server reconnects were exhausted and it is unavailable",
                "Check the network/endpoint, then reload MCP to retry.",
            ))
        elif connection_state in ("failed", "closed", "failed_refused"):
            out.checks.append(Diagnostic(
                "server_not_connected", ERROR, f"Server state is `{connection_state}`",
                "Run Test connection to see the server's own startup error, then fix the cause above.",
            ))
        else:
            out.checks.append(Diagnostic(
                "server_not_started", WARN, f"Server state is `{connection_state}`",
                "Enable the server and Test connection.",
            ))

    if discovered_tools is not None:
        if discovered_tools == 0:
            out.checks.append(Diagnostic("no_tools_discovered", WARN, "The server exposed no tools",
                                         "Confirm the server started correctly; check its Test diagnostic."))
        else:
            out.checks.append(Diagnostic("tools_discovered", OK, f"{discovered_tools} tool(s) discovered"))

    if (
        tools_discovered is not None
        and tools_kept is not None
        and tools_discovered > tools_kept
    ):
        out.checks.append(Diagnostic(
            "tools_truncated", WARN,
            f"This server advertised {tools_discovered} tools but only the first "
            f"{tools_kept} are considered (maxTools); the rest are not listed",
            "Raise maxTools for this server if you need the complete catalog.",
        ))

    if selected_tools is not None and discovered_tools is not None:
        if selected_tools == 0:
            out.checks.append(Diagnostic(
                "no_tools_selected", WARN, "No tools are selected, so nothing is callable",
                "Review the discovered tools and select the read-only ones you want (writes still need approval).",
            ))
        else:
            out.checks.append(Diagnostic("tools_selected", OK, f"{selected_tools} tool(s) selected"))

    return out


def environment_diagnostics() -> list[Diagnostic]:
    """Whole-environment checks shared by every server (Node/Python/temp dir)."""
    checks: list[Diagnostic] = []
    checks.append(_toolchain_check(
        "node", "Node.js",
        "Install Node.js 20+ (https://nodejs.org). npx-based MCP servers need it; Python-based servers do not.",
    ))
    checks.append(_toolchain_check(
        "npx", "npx",
        "npx ships with Node.js — install Node.js 20+ and reopen the app.",
    ))
    checks.append(_toolchain_check(
        "python", "Python",
        "Install Python 3.10+ or run `npm run setup:python` for the bundled runtime.",
    ))
    checks.append(_temp_dir_check())
    return checks


def _temp_dir_check() -> Diagnostic:
    """A writable temp directory is required by the test suite and by some servers.

    On Windows a locked-down `%TEMP%` (or a bad TMPDIR) makes healthy tests look
    broken. We detect it and tell the user how to point the tooling elsewhere.
    """
    import tempfile

    candidates = [os.environ.get("BLACK_ECLIPSE_TMP"), os.environ.get("TMPDIR"), tempfile.gettempdir()]
    for base in candidates:
        if not base:
            continue
        try:
            os.makedirs(base, exist_ok=True)
            probe = os.path.join(base, ".be_write_probe")
            with open(probe, "w", encoding="utf-8") as fh:
                fh.write("ok")
            os.remove(probe)
            return Diagnostic("temp_writable", OK, f"Temporary directory is writable: {base}")
        except OSError:
            continue
    return Diagnostic(
        "temp_not_writable", WARN,
        "No writable temporary directory was found",
        "Set BLACK_ECLIPSE_TMP to a writable folder (e.g. your user temp dir) and restart, so tests and servers can write scratch files.",
    )


__all__ = [
    "Diagnostic",
    "ServerDiagnostics",
    "check_server",
    "environment_diagnostics",
    "OK",
    "WARN",
    "ERROR",
    "SKIPPED",
]
