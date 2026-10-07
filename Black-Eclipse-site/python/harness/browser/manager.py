"""The process-wide BrowserManager.

Owns every live `BrowserSession`, the provider registry, the router, the vault,
the profile manager and the durable store. It is the ONLY thing that creates or
destroys a browser, enforces the concurrency limit, and performs deterministic
cleanup (idle sweep + shutdown). Tools resolve it through the module singleton,
so agent and UI share one browser runtime.

This is not a second execution path: launching a browser is delegated to a
`BrowserProvider`, and persistence goes through the ONE agent-memory connection.
"""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import Any, Optional

from .config import BrowserConfig, MAX_SESSIONS_CEILING, browser_config
from .errors import BrowserError, BrowserSessionError, BrowserUnavailable
from .policy import BrowserPolicy, DomainPolicy, default_policy
from .profiles import ProfileManager
from .providers import (
    AgentBrowserProvider,
    BrowserUseProvider,
    BrowserbaseProvider,
    CDPProvider,
    FirecrawlProvider,
    LaunchOptions,
    LightpandaProvider,
    LocalChromiumProvider,
)
from ..persistence import now_iso
from .router import BrowserProviderRouter, RoutingRequest
from .session import BrowserSession, SessionState
from .store import BrowserStore, new_session_id
from .trace import BrowserTrace
from .vault import BrowserVault

log = logging.getLogger("harness.browser.manager")


class BrowserManager:
    def __init__(
        self,
        config: Optional[BrowserConfig] = None,
        *,
        agent_store: Any = None,
        resolver: Any = None,
        bus: Any = None,
    ) -> None:
        self.config = config or browser_config()
        self.bus = bus
        self.store = BrowserStore(agent_store) if agent_store is not None else None

        self._local = LocalChromiumProvider()
        self._providers: dict[str, Any] = {
            "local_chromium": self._local,
            "cdp": CDPProvider(self._local),
            "browser_use": BrowserUseProvider(),
            "browserbase": BrowserbaseProvider(self._local),
            "lightpanda": LightpandaProvider(),
            "agent_browser": AgentBrowserProvider(),
            "firecrawl": FirecrawlProvider(),
        }
        self.router = BrowserProviderRouter(self.config, self._providers)
        self.vault = BrowserVault(store=self.store, resolver=resolver)
        self.profiles = ProfileManager(self.config.profiles_dir)
        self._sessions: dict[str, BrowserSession] = {}
        self._lock = asyncio.Lock()
        self._sweep_task: Optional[asyncio.Task[Any]] = None

    # ── discovery / health ───────────────────────────────────────────────────

    def providers(self) -> list[dict[str, Any]]:
        return [self._providers[pid].to_dict() for pid in self._providers]

    def capabilities(self) -> dict[str, Any]:
        return {
            "enabled": self.config.enabled,
            "defaultProvider": self.config.default_provider,
            "providers": self.providers(),
            "limits": {
                "maxConcurrent": self.config.max_concurrent,
                "maxSteps": self.config.max_steps,
                "maxExecutionSeconds": self.config.max_execution_seconds,
                "idleTimeoutSeconds": self.config.idle_timeout_seconds,
            },
            "policy": default_policy().to_dict(),
            "artifactsRoot": str(self.config.artifacts_root),
        }

    def active_count(self) -> int:
        return sum(1 for s in self._sessions.values() if not s.state.terminal)

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self.bus is None:
            return
        try:
            from ..persistence import now_iso  # noqa: PLC0415

            self.bus.publish({
                "id": f"browser_{event_type}_{now_iso()}", "runId": None,
                "type": event_type, "seq": 0, "at": now_iso(), "data": data,
            })
        except Exception:  # noqa: BLE001 - observability must never break a session
            pass

    # ── session lifecycle ────────────────────────────────────────────────────

    def build_policy(
        self, *, permissions: Optional[dict[str, str]] = None,
        domains: Optional[DomainPolicy] = None,
    ) -> BrowserPolicy:
        policy = default_policy()
        if permissions:
            for key, value in permissions.items():
                if key in policy.permissions or key in ("credentials", "payments"):
                    policy.permissions[key] = value
        if domains is not None:
            policy.domains = domains
        return policy

    async def create_session(
        self,
        *,
        provider: Optional[str] = None,
        url: Optional[str] = None,
        headless: Optional[bool] = None,
        profile_id: Optional[str] = None,
        persistent: bool = False,
        agent_id: Optional[str] = None,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        policy: Optional[BrowserPolicy] = None,
        required_capabilities: tuple[str, ...] = (),
        interactive: bool = True,
        allow_remote: bool = False,
        cdp_endpoint: Optional[str] = None,
        viewport: Optional[dict[str, int]] = None,
    ) -> BrowserSession:
        if not self.config.enabled:
            raise BrowserUnavailable(
                "The browser capability is disabled in configuration.",
                code="BROWSER_DISABLED",
            )
        async with self._lock:
            if self.active_count() >= self.config.max_concurrent:
                raise BrowserSessionError(
                    f"Eclipse already has {self.active_count()} browsers open; "
                    f"the most it keeps at once is {self.config.max_concurrent}.",
                    code="BROWSER_SESSION_LIMIT",
                )
        if self.config.max_concurrent > MAX_SESSIONS_CEILING:
            self.config.max_concurrent = MAX_SESSIONS_CEILING

        # Route a provider: explicit choice, else capability/policy/explicit rules.
        decision = self.router.decide(RoutingRequest(
            provider=provider, url=url, required_capabilities=required_capabilities,
            interactive=interactive, allow_remote=allow_remote,
        ))
        if not decision.provider:
            raise BrowserUnavailable(
                decision.rationale, code="BROWSER_PROVIDER_UNAVAILABLE",
                metadata={"rejected": decision.rejected},
            )
        provider_impl = self._providers[decision.provider]

        user_data_dir = None
        if persistent or profile_id:
            resolved_profile = profile_id or "default"
            user_data_dir = self.profiles.ensure(resolved_profile)
            profile_id = resolved_profile

        options = LaunchOptions(
            headless=self.config.headless if headless is None else bool(headless),
            browser_type=self.config.browser_type,
            viewport_width=(viewport or {}).get("width", self.config.viewport_width),
            viewport_height=(viewport or {}).get("height", self.config.viewport_height),
            user_agent=self.config.user_agent,
            locale=self.config.locale,
            timezone=self.config.timezone,
            proxy=self.config.proxy,
            user_data_dir=user_data_dir,
            downloads_dir=self.config.downloads_dir,
            cdp_endpoint=cdp_endpoint or self.config.cdp_endpoint,
        )
        # A cloud provider needs its credential resolved INTERNALLY (never shown to
        # the model). The vault resolves the configured reference; when it cannot
        # be resolved the provider reports an honest CREDENTIAL_UNAVAILABLE.
        if decision.provider == "browserbase":
            options.extra = {
                "apiKey": await self._resolve_cloud_credential(self.config.browserbase_api_key_ref),
                "projectId": self.config.browserbase_project_id,
            }

        session_id = new_session_id()
        trace = BrowserTrace(session_id=session_id, run_id=run_id or "", task_id=task_id or "", store=self.store)
        try:
            if decision.provider == "cdp" or (options.cdp_endpoint and decision.provider in ("cdp", "lightpanda")):
                ps = await provider_impl.connect(options)
            else:
                ps = await provider_impl.launch(options)
        except BrowserError as exc:
            self._emit("browser.session.failed", {"provider": decision.provider, "code": exc.code})
            raise
        except Exception as exc:  # noqa: BLE001
            self._emit("browser.session.failed", {"provider": decision.provider, "error": str(exc)[:200]})
            raise BrowserUnavailable(
                "Eclipse couldn't start a browser.", provider=decision.provider, metadata={"error": str(exc)[:200]},
            ) from exc

        session = BrowserSession(
            session_id=session_id, provider=provider_impl, provider_session=ps,
            config=self.config, policy=policy or default_policy(), store=self.store,
            trace=trace, agent_id=agent_id, task_id=task_id, run_id=run_id, profile_id=profile_id,
        )
        session._transition(SessionState.READY)  # noqa: SLF001
        self._sessions[session_id] = session
        if self.store is not None and profile_id:
            self.store.save_profile({
                "id": profile_id, "name": profile_id,
                "path": str(user_data_dir or ""), "persistent": bool(user_data_dir),
                "lastUsedAt": now_iso(),
            })
        self._emit("browser.session.created", {
            "sessionId": session_id, "provider": decision.provider,
            "backend": session.backend, "rationale": decision.rationale,
            "persistent": bool(user_data_dir), "profileId": profile_id,
        })
        if url:
            await session.navigate(url)
        return session

    async def _resolve_cloud_credential(self, reference: Optional[str]) -> Optional[str]:
        """Resolve a cloud provider's credential reference through the vault.

        Returns None when the reference is absent or cannot be resolved, so the
        provider reports an honest CREDENTIAL_UNAVAILABLE. The value is never
        logged or emitted.
        """
        if not reference:
            return None
        try:
            from .vault import parse_reference  # noqa: PLC0415

            ref = reference if parse_reference(reference) else f"vault://browserbase/{reference}"
            return await self.vault.resolve(ref)
        except Exception:  # noqa: BLE001 - an unreachable vault is not a value
            return None

    def get_session(self, session_id: str) -> Optional[BrowserSession]:
        return self._sessions.get(session_id)

    def require_session(self, session_id: str) -> BrowserSession:
        session = self._sessions.get(session_id)
        if session is None or session.state.terminal:
            raise BrowserSessionError(
                "That browser session isn't open any more.", code="BROWSER_SESSION_NOT_FOUND",
            )
        return session

    def list_sessions(self) -> list[dict[str, Any]]:
        return [s.snapshot_summary() for s in self._sessions.values()]

    def any_session(self) -> Optional[BrowserSession]:
        """A fallback when a tool is called with no explicit session id."""
        live = [s for s in self._sessions.values() if not s.state.terminal]
        if not live:
            return None
        return max(live, key=lambda s: s.last_activity)

    async def pause_session(self, session_id: str) -> dict[str, Any]:
        return self.require_session(session_id).pause()

    def resume_session(self, session_id: str) -> dict[str, Any]:
        return self.require_session(session_id).resume()

    async def destroy_session(self, session_id: str) -> dict[str, Any]:
        session = self._sessions.get(session_id)
        if session is None:
            return {"destroyed": False, "reason": "no such session"}
        try:
            await session.close()
        finally:
            self._sessions.pop(session_id, None)
        self._emit("browser.session.destroyed", {"sessionId": session_id})
        return {"destroyed": True, "sessionId": session_id}

    def detach_session(self, session_id: str) -> Optional[BrowserSession]:
        """Remove a session from the pool WITHOUT closing it (used by tests)."""
        return self._sessions.pop(session_id, None)

    async def sweep_idle(self) -> list[str]:
        """Close sessions idle beyond the configured timeout. Returns their ids."""
        now = time.time()
        expired: list[str] = []
        for session_id, session in list(self._sessions.items()):
            if session.state.terminal or session.state.value in ("HUMAN_REQUIRED", "PAUSED"):
                continue
            if now - session.last_activity > self.config.idle_timeout_seconds:
                expired.append(session_id)
        for session_id in expired:
            await self.destroy_session(session_id)
        return expired

    # ── runtime sweep task ───────────────────────────────────────────────────

    async def start(self) -> None:
        if self._sweep_task is None or self._sweep_task.done():
            self._sweep_task = asyncio.create_task(self._sweep_loop())

    async def _sweep_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(max(30, self.config.idle_timeout_seconds // 3))
                try:
                    await self.sweep_idle()
                except Exception:  # noqa: BLE001 - a sweep must never kill the task
                    pass
        except asyncio.CancelledError:
            return

    async def stop(self) -> None:
        if self._sweep_task is not None:
            self._sweep_task.cancel()
            try:
                await self._sweep_task
            except asyncio.CancelledError:
                pass
            self._sweep_task = None
        for session_id in list(self._sessions.keys()):
            try:
                await self.destroy_session(session_id)
            except Exception:  # noqa: BLE001 - shutdown must never raise
                pass
        try:
            await self._local.shutdown()
        except Exception:  # noqa: BLE001
            pass


__all__ = ["BrowserManager"]
