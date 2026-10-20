"""Operator-triggered credential verification (MCP integrity, Phase 1b).

Separate from `test_server` (which only proves the process started and listed
tools) and never automatic: `verify_credentials` makes ONE operator-chosen read
call with operator-supplied arguments, bounded by a short timeout, and records a
content-free verdict. Extracted as a mixin so `manager.py` stays under its size
ratchet; `MCPManager` inherits it, so the public API is unchanged.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from .client import (
    MCPClosedError,
    MCPConnection,
    MCPError,
    MCPTimeoutError,
)
from .runtime import _ServerRuntime

log = logging.getLogger("harness.mcp.verify")

READ_EFFECT = "read"

# The Verify action is a single, operator-triggered call with a short, fixed
# timeout. It is never automatic and never a loop.
VERIFY_TIMEOUT_MS = 10_000


class VerifyMixin:
    """The operator-triggered Verify action over the configured runtimes."""

    async def secret_presence(self, names: Any) -> dict[str, bool]:
        """Whether each vault secret NAME resolves to a value (never the value).

        Used by the external-capability proposal and its install gate so the
        runtime can say "credential present / missing" without reading a secret
        value into a tool result, a record or a log. No resolver wired means the
        answer is unknown (`{}`), never an optimistic True.
        """
        resolver = getattr(self, "_secret_resolver", None)
        if resolver is None:
            return {}
        out: dict[str, bool] = {}
        seen: set[str] = set()
        for raw in names or ():
            name = str(raw or "").strip()
            if not name or name in seen:
                continue
            seen.add(name)
            try:
                value = resolver(name)
                if inspect.isawaitable(value):
                    value = await value
                out[name] = bool(value)
            except Exception:  # noqa: BLE001 - a resolver failure is "not verified"
                out[name] = False
        return out

    async def verify_credentials(
        self,
        server_id: str,
        *,
        tool: str,
        arguments: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """Operator-triggered proof that a server's credentials actually work.

        SEPARATE from `test_server` (which only proves the process started and
        listed tools) and never automatic: it is run only when the operator asks.
        It calls ONE operator-chosen read tool with operator-supplied arguments,
        bounded by a short timeout, and records a content-free diagnostic:

          * `credentials_valid`      — the call reached the provider and returned a
                                       normal (non-provider-error) result;
          * `credentials_rejected`   — the provider returned an error status/code;
          * `verify_inconclusive`    — the server could not be reached/connected,
                                       the tool is not a read tool, or the call
                                       failed for a non-provider reason.

        The response body is NEVER returned or stored; only a stable code and the
        provider's status/code (when present) are recorded.
        """
        rt = self._runtimes.get(server_id)
        now = datetime.now(timezone.utc).isoformat()
        if rt is None:
            return self._verify_verdict("verify_inconclusive", now, tool, "server not found")
        if not rt.config.enabled:
            return self._record(rt, self._verify_verdict("verify_inconclusive", now, tool, "server is disabled"))

        # The chosen tool must be a declared/selected READ tool: Verify must never
        # call a write.
        declared = rt.config.tool_effects.get(tool)
        tool_known = tool in rt.descriptors
        if declared not in (READ_EFFECT, None):
            return self._record(rt, self._verify_verdict("verify_inconclusive", now, tool, "not a read tool"))

        connection = rt.connection if rt.state == "connected" else None
        temporary = False
        if connection is None:
            # Verify is opt-in and bounded; spawn a temporary connection if the
            # server is lazy/not connected, then always tear it down.
            connection = MCPConnection(
                rt.config, secret_resolver=self._secret_resolver, bridge_fetch=self._bridge_fetch
            )
            temporary = True
            try:
                await connection.start()
            except MCPError as exc:
                return self._record(rt, self._verify_verdict(
                    "verify_inconclusive", now, tool, f"could not connect: {exc.code}"
                ))
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                return self._record(rt, self._verify_verdict(
                    "verify_inconclusive", now, tool, "could not connect"
                ))
        if not tool_known:
            discovered = {t.name for t in connection.tools}
            if tool not in discovered:
                if temporary:
                    await self._safe_close(connection)
                return self._record(rt, self._verify_verdict("verify_inconclusive", now, tool, "unknown tool"))
        try:
            outcome = await connection.call_tool(tool, arguments or {}, timeout_ms=VERIFY_TIMEOUT_MS)
            provider_error = (outcome.data or {}).get("providerError")
            if provider_error is not None or not outcome.ok:
                code = (provider_error or {}).get("code") if provider_error else None
                status = (provider_error or {}).get("status") if provider_error else None
                result = self._verify_verdict(
                    "credentials_rejected", now, tool, None, providerCode=code, providerStatus=status
                )
            else:
                result = self._verify_verdict("credentials_valid", now, tool, None)
        except MCPTimeoutError:
            result = self._verify_verdict("verify_inconclusive", now, tool, "call timed out")
        except MCPClosedError:
            result = self._verify_verdict("verify_inconclusive", now, tool, "server not connected")
        except MCPError as exc:
            result = self._verify_verdict("verify_inconclusive", now, tool, exc.code)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            result = self._verify_verdict("verify_inconclusive", now, tool, "call failed")
        finally:
            if temporary:
                await self._safe_close(connection)
        return self._record(rt, result)

    def _record(self, rt: _ServerRuntime, result: dict[str, Any]) -> dict[str, Any]:
        rt.verify_result = result
        return result

    async def _safe_close(self, connection: MCPConnection) -> None:
        try:
            await connection.close()
        except Exception:  # noqa: BLE001 - teardown must not mask the verdict
            log.warning("MCP verify connection did not close cleanly", exc_info=True)

    def _verify_verdict(
        self,
        verdict: str,
        verified_at: str,
        tool: str,
        reason: Optional[str],
        *,
        providerCode: Optional[str] = None,
        providerStatus: Optional[int] = None,
    ) -> dict[str, Any]:
        """A content-free Verify verdict. Never carries the response body."""
        result: dict[str, Any] = {
            "code": verdict,
            "verifiedAt": verified_at,
            "tool": tool,
            "bounded": True,
        }
        if providerCode:
            result["providerCode"] = providerCode
        if providerStatus is not None:
            result["providerStatus"] = providerStatus
        if reason:
            result["reason"] = reason
        return result


__all__ = ["VerifyMixin", "VERIFY_TIMEOUT_MS"]
