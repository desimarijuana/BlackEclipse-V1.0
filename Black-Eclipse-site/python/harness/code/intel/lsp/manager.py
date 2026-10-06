"""The LSP Manager — discover, start, route, monitor and stop language servers.

One manager per CIUE instance. It owns a `ClientSet` per workspace root, routes a
request to the client that serves the file's language, caches server capabilities,
restarts a crashed server a bounded number of times, and — critically — NEVER
lets a language-server failure crash the runtime. A missing or failed server is a
structured `LANGUAGE_SERVER_MISSING` / `LANGUAGE_SERVER_FAILED` that the manager
maps to a fallback, not an exception the agent sees.

Multiple workspaces (multi-root) and multiple language servers coexist: the key is
`(root, provider_id)`.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .client import LSPClient
from .provider import LanguageServerProvider, resolve_launch_argv
from .providers import build_providers

log = logging.getLogger("harness.code.intel.lsp")

MAX_RESTARTS = 2
RESTART_BACKOFF_S = 0.5
MAX_CLIENTS = 16


@dataclass
class ServerStatus:
    provider_id: str
    language: str
    root: str
    state: str            # running | starting | failed | missing | stopped
    pid: Optional[int] = None
    restarts: int = 0
    reason: str = ""
    started_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "provider": self.provider_id, "language": self.language, "root": self.root,
            "state": self.state, "restarts": self.restarts,
        }
        if self.pid is not None:
            payload["pid"] = self.pid
        if self.reason:
            payload["reason"] = self.reason
        return payload


class LSPManager:
    """The ONE language server orchestrator for a CIUE instance."""

    def __init__(
        self,
        *,
        providers: Optional[list[LanguageServerProvider]] = None,
        on_event: Optional[Callable[[str, dict[str, Any]], None]] = None,
    ) -> None:
        self._providers = providers if providers is not None else build_providers()
        self._by_language: dict[str, LanguageServerProvider] = {}
        for provider in self._providers:
            spec = provider.spec(Path("."))
            languages = spec.languages if spec else provider.languages
            for language in languages:
                self._by_language.setdefault(language, provider)
        self._clients: dict[tuple[str, str], LSPClient] = {}
        self._statuses: dict[tuple[str, str], ServerStatus] = {}
        self._lock = threading.RLock()
        self._on_event = on_event
        self._capability_cache: dict[tuple[str, str], dict[str, Any]] = {}

    # ── introspection ──────────────────────────────────────────────────────────
    def supported_languages(self) -> list[str]:
        return sorted(self._by_language)

    def provider_for(self, language: str) -> Optional[LanguageServerProvider]:
        return self._by_language.get(language)

    def provider_status(self, root: Path) -> list[dict[str, Any]]:
        """Every provider with an honest installed/serves verdict for `root`."""
        out: list[dict[str, Any]] = []
        for provider in self._providers:
            spec = provider.spec(root)
            languages = list(spec.languages) if spec else list(provider.languages)
            out.append({
                "provider": provider.provider_id,
                "languages": languages,
                "installed": bool(spec and resolve_launch_argv(spec, root)),
                "argv": list(spec.argv) if spec else [],
            })
        return out

    def statuses(self) -> list[dict[str, Any]]:
        with self._lock:
            return [s.to_dict() for s in self._statuses.values()]

    # ── lifecycle ──────────────────────────────────────────────────────────────
    def ensure_client(self, root: Path, language: str) -> tuple[Optional[LSPClient], str]:
        """Return a running client for `(root, language)`, or `(None, reason_code)`.

        The reason is a stable code: SERVER_MISSING when nothing is installed,
        SERVER_FAILED when the launch/handshake failed, UNSUPPORTED_LANGUAGE when
        no provider serves the language.
        """
        provider = self._by_language.get(language)
        if provider is None:
            return None, "UNSUPPORTED_LANGUAGE"
        root = Path(root)
        key = (str(root), provider.provider_id)
        with self._lock:
            existing = self._clients.get(key)
            if existing is not None and existing.alive:
                return existing, ""
            if existing is not None:
                existing.stop()
                self._clients.pop(key, None)
            if len(self._clients) >= MAX_CLIENTS:
                self._evict_one_locked()
            spec = provider.spec(root)
            if spec is None:
                return None, "LANGUAGE_SERVER_MISSING"
            argv = resolve_launch_argv(spec, root)
            if argv is None:
                self._statuses[key] = ServerStatus(
                    provider_id=provider.provider_id, language=language,
                    root=str(root), state="missing", reason="not installed",
                )
                return None, "LANGUAGE_SERVER_MISSING"
            if self._should_skip_restart(key):
                return None, "LANGUAGE_SERVER_FAILED"
            client = self._start_client(key, provider.provider_id, root, argv, spec, language)
            if client is None:
                return None, "LANGUAGE_SERVER_FAILED"
            return client, ""

    def _start_client(
        self, key: tuple[str, str], provider_id: str, root: Path, argv: list[str],
        spec: Any, language: str,
    ) -> Optional[LSPClient]:
        self._emit("lsp.starting", {"provider": provider_id, "root": str(root), "language": language})
        client = LSPClient(provider_id, root, argv, initialization_options=spec.initialization_options)
        try:
            client.start()
        except Exception as exc:  # noqa: BLE001 - a failed server is a diagnostic
            client.stop()
            self._record_failure(key, provider_id, language, root, str(exc))
            return None
        self._clients[key] = client
        prior = self._statuses.get(key)
        self._statuses[key] = ServerStatus(
            provider_id=provider_id, language=language, root=str(root), state="running",
            pid=client.pid, restarts=(prior.restarts + 1) if prior and prior.state == "failed" else (prior.restarts if prior else 0),
            started_at=time.monotonic(),
        )
        self._capability_cache[key] = dict(client.capabilities)
        self._emit("lsp.started", {"provider": provider_id, "pid": client.pid, "root": str(root)})
        return client

    def _record_failure(self, key: tuple[str, str], provider_id: str, language: str, root: Path, error: str) -> None:
        prior = self._statuses.get(key)
        restarts = (prior.restarts + 1) if prior else 1
        self._statuses[key] = ServerStatus(
            provider_id=provider_id, language=language, root=str(root),
            state="failed", restarts=restarts, reason=error[:300],
        )
        self._emit("lsp.failed", {"provider": provider_id, "error": error[:300], "restarts": restarts})

    def _should_skip_restart(self, key: tuple[str, str]) -> bool:
        prior = self._statuses.get(key)
        return bool(prior and prior.state == "failed" and prior.restarts > MAX_RESTARTS)

    def restart(self, root: Path, language: str) -> dict[str, Any]:
        provider = self._by_language.get(language)
        if provider is None:
            return {"ok": False, "code": "UNSUPPORTED_LANGUAGE"}
        key = (str(Path(root)), provider.provider_id)
        self.stop_client(root, language)
        with self._lock:
            if key in self._statuses:
                self._statuses[key].restarts = 0
                self._statuses[key].state = "stopped"
        client, reason = self.ensure_client(root, language)
        return {"ok": client is not None, "code": reason or "OK"}

    def stop_client(self, root: Path, language: str) -> bool:
        provider = self._by_language.get(language)
        if provider is None:
            return False
        key = (str(Path(root)), provider.provider_id)
        with self._lock:
            client = self._clients.pop(key, None)
        if client is None:
            return False
        try:
            client.shutdown()
        except Exception:  # noqa: BLE001 - shutdown must never raise
            client.stop()
        self._emit("lsp.stopped", {"provider": provider.provider_id, "root": str(root)})
        return True

    def stop_all(self) -> int:
        with self._lock:
            items = list(self._clients.items())
            self._clients.clear()
        for _key, client in items:
            try:
                client.shutdown()
            except Exception:  # noqa: BLE001
                client.stop()
        if items:
            self._emit("lsp.shutdown", {"count": len(items)})
        return len(items)

    def _evict_one_locked(self) -> None:
        """Drop the oldest running client to stay under the bound. Caller holds lock."""
        if not self._clients:
            return
        oldest_key = min(
            self._clients,
            key=lambda k: self._statuses.get(k, ServerStatus("", "", "", "stopped")).started_at or 0.0,
        )
        client = self._clients.pop(oldest_key, None)
        if client is not None:
            try:
                client.shutdown(timeout_s=2.0)
            except Exception:  # noqa: BLE001
                client.stop()

    # ── routing ─────────────────────────────────────────────────────────────────
    def client_for_file(self, root: Path, rel_path: str, language: str) -> tuple[Optional[LSPClient], str]:
        return self.ensure_client(root, language)

    def health_check(self) -> list[dict[str, Any]]:
        """Reap dead clients so a crashed server is observable, not stale."""
        with self._lock:
            dead = [key for key, client in self._clients.items() if not client.alive]
            for key in dead:
                client = self._clients.pop(key)
                status = self._statuses.get(key)
                if status is not None and status.state == "running":
                    status.state = "failed"
                    status.reason = client.last_error or "the language server exited"
            return [s.to_dict() for s in self._statuses.values()]

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event_type, data)
        except Exception:  # noqa: BLE001 - an event must never break CIUE
            pass


__all__ = ["LSPManager", "MAX_RESTARTS", "ServerStatus"]
