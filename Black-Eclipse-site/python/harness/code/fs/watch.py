"""File watching + cache invalidation, normalized across platforms.

A native OS watcher when one is available (Windows `ReadDirectoryChangesW`,
Linux `inotify` — see `watch_native.py`), and a portable polling watch otherwise.
Both produce the SAME normalized event vocabulary and feed the same debounce +
cache-invalidation + incremental-reindex step, so the rest of the subsystem is
unaware of which backend is active. A native backend that fails at any point
transparently degrades to polling — a watch never breaks the runtime.

It detects created / modified / deleted / renamed and:
  * debounces duplicate events (a burst for one path collapses to one),
  * invalidates the metadata/hash cache and incrementally re-indexes only the
    files that changed — never a full rebuild.

A caller may `poll_once()` deterministically (tests, an agent turn) or run the
background thread with `start()`/`stop()`.
"""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional

from .. import policy
from . import metadata as meta
from . import resolver as res
from . import watch_native

CREATED = "created"
MODIFIED = "modified"
DELETED = "deleted"
RENAMED = "renamed"

WATCH_EVENTS = (CREATED, MODIFIED, DELETED, RENAMED)

DEFAULT_POLL_INTERVAL_S = 1.0
DEFAULT_DEBOUNCE_S = 0.25
MAX_WATCH_PATHS = 5_000


@dataclass
class WatchEvent:
    event: str
    path: str
    old_path: Optional[str] = None
    at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        payload = {"event": self.event, "path": self.path, "at": self.at}
        if self.old_path:
            payload["oldPath"] = self.old_path
        return payload


def _snapshot(ws: Any, targets: list[Path], recursive: bool) -> dict[str, tuple[int, int]]:
    """A map rel → (mtime_ns, size) for the watched paths."""
    out: dict[str, tuple[int, int]] = {}
    seen = 0
    for target in targets:
        if target.is_file():
            rel = res.relative(ws, target)
            try:
                st = target.stat()
                out[rel] = (st.st_mtime_ns, st.st_size)
            except OSError:
                pass
            continue
        if not target.is_dir():
            continue
        iterator = target.rglob("*") if recursive else target.glob("*")
        for path in iterator:
            if not path.is_file():
                continue
            rel = res.relative(ws, path)
            if policy.is_protected(rel) or policy.is_ignored(rel):
                continue
            try:
                st = path.stat()
            except OSError:
                continue
            out[rel] = (st.st_mtime_ns, st.st_size)
            seen += 1
            if seen >= MAX_WATCH_PATHS:
                return out
    return out


def _rel_of_absolute(ws: Any, absolute: str) -> Optional[str]:
    """Convert a native absolute path to a workspace-relative path, or None.

    A path outside the workspace (or one that is protected/ignored) is dropped:
    the watch is a workspace-bounded surface, exactly like every other operation.
    """
    try:
        real = Path(os.path.realpath(absolute))
    except (OSError, ValueError):
        return None
    if not res.is_inside(ws, real):
        return None
    rel = res.relative(ws, real)
    if policy.is_protected(rel) or policy.is_ignored(rel):
        return None
    return rel


class WorkspaceWatcher:
    """A debounced watcher over workspace paths (native, else portable polling)."""

    def __init__(
        self,
        ws: Any,
        *,
        targets: Optional[list[str]] = None,
        recursive: bool = True,
        index: Any = None,
        on_event: Optional[Callable[[list[WatchEvent]], None]] = None,
        debounce_s: float = DEFAULT_DEBOUNCE_S,
        poll_interval_s: float = DEFAULT_POLL_INTERVAL_S,
        prefer_native: bool = True,
    ) -> None:
        self.ws = ws
        self.recursive = recursive
        self.index = index
        self.on_event = on_event
        self.debounce_s = max(0.0, float(debounce_s))
        self.poll_interval_s = max(0.05, float(poll_interval_s))
        self._targets = self._resolve_targets(targets)
        self._baseline = _snapshot(ws, self._targets, recursive)
        self._recent: dict[tuple[str, str], float] = {}
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self.events: list[WatchEvent] = []
        self._native: Optional[watch_native.NativeWatchBase] = None
        self._prefer_native = prefer_native
        self._fallback_baseline_stale = False
        self.backend = "polling"

    def _resolve_targets(self, targets: Optional[list[str]]) -> list[Path]:
        if not targets:
            return [self.ws.root]
        resolved: list[Path] = []
        for rel in targets:
            try:
                resolved.append(res.resolve(self.ws, rel))
            except Exception:  # noqa: BLE001 - a bad target is simply not watched
                continue
        return resolved or [self.ws.root]

    # ── native lifecycle ─────────────────────────────────────────────────────
    def _ensure_native(self) -> None:
        """Start the native backend once; on any failure stay on polling."""
        if not self._prefer_native or self._native is not None:
            return
        native = watch_native.create_native_watcher(self._targets, recursive=self.recursive)
        if native is None:
            return
        try:
            native.start()
        except Exception:  # noqa: BLE001 - fall back to polling
            return
        self._native = native
        self.backend = native.name

    def _native_events(self) -> Optional[list[WatchEvent]]:
        """Drain the native backend into normalized events, or None to fall back."""
        native = self._native
        if native is None:
            return None
        if not native.healthy():
            native.stop()
            self._native = None
            self.backend = "polling"
            # The tree may have changed while the native watch was degrading;
            # re-baseline so the fallback reports only future changes.
            self._fallback_baseline_stale = True
            return None
        raw: list[WatchEvent] = []
        for kind, absolute, old_absolute in native.drain():
            rel = _rel_of_absolute(self.ws, absolute)
            if rel is None:
                continue
            old_rel = _rel_of_absolute(self.ws, old_absolute) if old_absolute else None
            raw.append(WatchEvent(kind, rel, old_path=old_rel))
        return raw

    # ── detection ───────────────────────────────────────────────────────────
    def poll_once(self) -> list[WatchEvent]:
        """Return debounced, normalized events since the last call.

        The native backend is drained when it is active; otherwise the portable
        snapshot diff runs. When a native backend stops being healthy the baseline
        is refreshed so the fallback does not re-report the whole tree.
        """
        raw: Optional[list[WatchEvent]] = None
        if self._native is not None:
            raw = self._native_events()
        if raw is None:
            if self._fallback_baseline_stale:
                self._baseline = _snapshot(self.ws, self._targets, self.recursive)
                self._fallback_baseline_stale = False
            raw = self._snapshot_diff()
        events = self._debounce(raw)
        for event in events:
            self._invalidate(event)
        self.events.extend(events)
        if self.on_event is not None and events:
            try:
                self.on_event(events)
            except Exception:  # noqa: BLE001 - a listener must not break the watch
                pass
        return events

    def _snapshot_diff(self) -> list[WatchEvent]:
        current = _snapshot(self.ws, self._targets, self.recursive)
        raw: list[WatchEvent] = []
        for rel, sig in current.items():
            if rel not in self._baseline:
                raw.append(WatchEvent(CREATED, rel))
            elif self._baseline[rel] != sig:
                raw.append(WatchEvent(MODIFIED, rel))
        removed = [rel for rel in self._baseline if rel not in current]
        added = [e for e in raw if e.event == CREATED]
        used_added: set[int] = set()
        for rel in removed:
            old_sig = self._baseline[rel]
            match_index = next(
                (i for i, event in enumerate(added)
                 if i not in used_added and current.get(event.path) == old_sig),
                None,
            )
            if match_index is not None:
                used_added.add(match_index)
                raw.append(WatchEvent(RENAMED, added[match_index].path, old_path=rel))
            else:
                raw.append(WatchEvent(DELETED, rel))
        raw = [e for e in raw if not (e.event == CREATED and any(
            r.event == RENAMED and r.path == e.path for r in raw))]
        self._baseline = current
        return raw

    def _debounce(self, raw: list[WatchEvent]) -> list[WatchEvent]:
        """Emit each event once, suppressing a repeat of the same path+kind within
        the debounce window. Deterministic on a single call: a newly detected
        change is always emitted, and only rapid duplicates are collapsed."""
        now = time.time()
        seen_now: set[tuple[str, str]] = set()
        emitted: list[WatchEvent] = []
        for event in raw:
            key = (event.path, event.event)
            if key in seen_now:
                continue
            seen_now.add(key)
            last = self._recent.get(key, 0.0)
            if now - last < self.debounce_s:
                continue
            self._recent[key] = now
            emitted.append(event)
        return emitted

    def _invalidate(self, event: WatchEvent) -> None:
        meta.clear_hash_cache()
        if self.index is None:
            return
        try:
            if event.event in (DELETED,):
                self.index.remove(event.path)
            elif event.event in (MODIFIED, CREATED, RENAMED):
                self.index.reindex_file(event.path)
                if event.event == RENAMED and event.old_path:
                    self.index.remove(event.old_path)
        except Exception:  # noqa: BLE001 - re-indexing is best-effort
            pass

    # ── background loop ─────────────────────────────────────────────────────
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._ensure_native()
        self._thread = threading.Thread(target=self._loop, name="eclipse-fs-watch", daemon=True)
        self._thread.start()

    def _loop(self) -> None:
        # Prefer native: it wakes promptly on a change. Polling is the fallback.
        while not self._stop.is_set():
            try:
                if self._native is not None:
                    events = self.poll_once()
                    if not events:
                        self._stop.wait(self.poll_interval_s)
                else:
                    self.poll_once()
                    self._stop.wait(self.poll_interval_s)
            except Exception:  # noqa: BLE001 - the loop must survive a transient error
                self._stop.wait(self.poll_interval_s)

    def stop(self) -> None:
        self._stop.set()
        if self._native is not None:
            try:
                self._native.stop()
            except Exception:  # noqa: BLE001
                pass
            self._native = None
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def status(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "backend": self.backend,
            "native": self._native is not None,
            "watching": [res.relative(self.ws, p) for p in self._targets],
            "recursive": self.recursive,
            "running": bool(self._thread and self._thread.is_alive()),
            "trackedFiles": len(self._baseline),
            "events": len(self.events),
        }


def watch_targets(ctx: Any, paths: list[str], *, recursive: bool, index: Any = None) -> dict[str, Any]:
    """Start a watcher over the given paths and return its status."""
    watcher = WorkspaceWatcher(ctx.ws, targets=paths, recursive=recursive, index=index)
    watcher.start()
    return watcher.status()


__all__ = [
    "CREATED",
    "DEFAULT_DEBOUNCE_S",
    "DEFAULT_POLL_INTERVAL_S",
    "DELETED",
    "MODIFIED",
    "RENAMED",
    "WATCH_EVENTS",
    "WatchEvent",
    "WorkspaceWatcher",
    "watch_targets",
]
