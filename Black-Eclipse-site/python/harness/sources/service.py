"""SourceService — the one entry point for roots, probing, reading and routing.

Both the agent tools and the HTTP routes call this object, so the UI and the
model can never disagree about what a file is or what a query covered.
"""

from __future__ import annotations

import base64
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

from .catalog import Catalog, now_iso, normalize_relpath
from .config import SourceConfig, load_config
from .contracts import FileRecord, Hit, RootRecord, SearchResult, SqlResult
from .errors import SourceError
from .indexer import index_files, unindexed
from .planner import absolute_path, plan_and_search
from .probe import probe_file
from .query import run_sql
from .scanner import scan_root
from .semantic import SemanticIndex

_INSTANCE_LOCK = threading.Lock()
_INSTANCE: Optional["SourceService"] = None


def get_sources_service() -> Optional["SourceService"]:
    return _INSTANCE


def set_sources_service(service: Optional["SourceService"]) -> None:
    global _INSTANCE
    with _INSTANCE_LOCK:
        _INSTANCE = service


class SourceService:
    def __init__(
        self,
        config: Optional[SourceConfig] = None,
        *,
        catalog: Optional[Catalog] = None,
        semantic: Optional[SemanticIndex] = None,
    ) -> None:
        self.config = config or load_config()
        self.catalog = catalog or Catalog(self.config)
        self.semantic = semantic or SemanticIndex(self.catalog, self.config)
        self._scan_threads: dict[str, threading.Thread] = {}
        self._scan_state: dict[str, dict[str, Any]] = {}
        self._cancel: dict[str, threading.Event] = {}
        self._background: set[threading.Thread] = set()
        self._lock = threading.RLock()

    def close(self) -> None:
        # Stop every worker before closing the connection: a background indexer
        # holding the SQLite handle while `close()` runs is a use-after-free.
        self.cancel_all()
        threads: list[threading.Thread] = []
        with self._lock:
            threads.extend(self._scan_threads.values())
            threads.extend(self._background)
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=5.0)
        self.catalog.close()
        set_sources_service(None)

    # ── roots ────────────────────────────────────────────────────────────────

    def add_root(self, path: str, label: Optional[str] = None) -> dict[str, Any]:
        root = self.catalog.add_root(path, label)
        # Registering a folder is meant to make it usable immediately: start the
        # catalog scan in the background. A concurrent scan is not an error here.
        try:
            self.start_scan(root.id)
        except SourceError:
            pass
        return root.to_dict()

    def remove_root(self, root_id: str) -> bool:
        return self.catalog.remove_root(root_id)

    def list_roots(self) -> list[dict[str, Any]]:
        return [root.to_dict() for root in self.catalog.list_roots()]

    # ── scanning ─────────────────────────────────────────────────────────────

    def start_scan(self, root_id: str) -> dict[str, Any]:
        root = self.catalog.get_root(root_id)
        if root is None:
            raise SourceError("ROOT_UNKNOWN", "the root is not registered")
        with self._lock:
            thread = self._scan_threads.get(root_id)
            if thread is not None and thread.is_alive():
                raise SourceError("SCAN_BUSY", "a scan is already running for this root")
            token = threading.Event()
            self._cancel[root_id] = token
            state: dict[str, Any] = {"rootId": root_id, "status": "SCANNING", "filesSeen": 0}
            self._scan_state[root_id] = state

            def run() -> None:
                def progress(payload: dict[str, Any]) -> None:
                    state.update(payload)
                try:
                    stats = scan_root(
                        self.catalog, root, config=self.config, cancel=token,
                        on_progress=progress,
                    )
                    state.update(stats.to_dict())
                    state["status"] = "PARTIAL" if stats.truncated else ("ERROR" if stats.error else "READY")
                finally:
                    state["finishedAt"] = now_iso()
                    with self._lock:
                        self._scan_threads.pop(root_id, None)

            thread = threading.Thread(target=run, name=f"sources-scan-{root_id}", daemon=True)
            self._scan_threads[root_id] = thread
            thread.start()
        return dict(state)

    def scan_status(self, root_id: str) -> dict[str, Any]:
        with self._lock:
            state = self._scan_state.get(root_id)
            thread = self._scan_threads.get(root_id)
            running = bool(thread is not None and thread.is_alive())
        root = self.catalog.get_root(root_id)
        payload = dict(state or {})
        payload.update({
            "rootId": root_id,
            "running": running,
            "root": root.to_dict() if root else None,
        })
        return payload

    def wait_scan(self, root_id: str, timeout_s: float = 60.0) -> dict[str, Any]:
        thread = self._scan_threads.get(root_id)
        if thread is not None:
            thread.join(timeout=max(0.0, timeout_s))
        return self.scan_status(root_id)

    def cancel_all(self) -> None:
        for token in list(self._cancel.values()):
            token.set()

    # ── paths ───────────────────────────────────────────────────────────────

    def _root(
        self, root_id: Optional[str], relpath: Optional[str], path: Optional[str]
    ) -> tuple[RootRecord, str]:
        if root_id:
            root = self.catalog.get_root(root_id)
            if root is None:
                raise SourceError("ROOT_UNKNOWN", "the root is not registered")
            if path:
                match = self.catalog.root_for_path(path)
                if match is None or match[0].id != root.id:
                    raise SourceError("PATH_OUTSIDE_ROOT", "the path is outside the requested root")
                return root, match[1]
            return root, normalize_relpath(relpath or "")
        if path:
            match = self.catalog.root_for_path(path)
            if match is None:
                raise SourceError(
                    "ROOT_UNKNOWN",
                    "that path is outside every registered root; add the folder as a source first",
                    details={"path": path},
                )
            return match
        raise SourceError("FILE_NOT_FOUND", "a rootId or an absolute path is required")

    def resolve(self, root_id: Optional[str] = None, relpath: Optional[str] = None,
                path: Optional[str] = None) -> tuple[RootRecord, str, str]:
        root, rel = self._root(root_id, relpath, path)
        base = Path(root.path).resolve()
        target = (base / rel.replace("/", os.sep)).resolve() if rel else base
        if target != base and base not in target.parents:
            raise SourceError("PATH_OUTSIDE_ROOT", "the path escapes its registered root")
        return root, normalize_relpath(rel), str(target)

    def find_file(self, *, root_id: Optional[str] = None, relpath: Optional[str] = None,
                  path: Optional[str] = None) -> tuple[RootRecord, FileRecord, str]:
        root, rel, absolute = self.resolve(root_id=root_id, relpath=relpath, path=path)
        file = self.catalog.get_file(root.id, rel)
        if file is None:
            file = self._adopt_file(root, rel, absolute)
        return root, file, absolute

    def _adopt_file(self, root: RootRecord, rel: str, absolute: str) -> FileRecord:
        """A path inside a root that the scanner has not seen yet."""
        if not os.path.exists(absolute):
            raise SourceError("FILE_GONE", "the file no longer exists on disk")
        if os.path.isdir(absolute):
            raise SourceError("FILE_NOT_FOUND", "that path is a directory; list it instead")
        info = os.stat(absolute)
        from .catalog import extension_of
        from .scanner import quick_class
        from .probe import read_head, sniff_magic

        ext = extension_of(Path(absolute).name)
        magic = sniff_magic(read_head(absolute, 512))
        self.catalog.upsert_file(
            root.id,
            {
                "relpath": rel, "name": Path(absolute).name, "ext": ext,
                "size": int(info.st_size), "mtime": float(info.st_mtime),
                "inode": str(getattr(info, "st_ino", "") or ""),
                "root_path": root.path, "magic": magic,
                "klass": quick_class(ext),
            },
            epoch=self._current_epoch(root.id),
        )
        self.catalog._db.commit()  # noqa: SLF001 - adopt is a write path
        file = self.catalog.get_file(root.id, rel)
        if file is None:  # pragma: no cover - upsert must produce the row
            raise SourceError("FILE_NOT_FOUND", "could not catalog that file")
        return file

    def _current_epoch(self, root_id: str) -> int:
        row = self.catalog._db.execute(  # noqa: SLF001 - epoch is catalog-internal
            "SELECT scanEpoch FROM Root WHERE id = ?", (root_id,)
        ).fetchone()
        return int(row[0]) if row else 0

    # ── open / read ─────────────────────────────────────────────────────────

    def open(self, *, root_id: Optional[str] = None, relpath: Optional[str] = None,
             path: Optional[str] = None) -> dict[str, Any]:
        root, file, absolute = self.find_file(root_id=root_id, relpath=relpath, path=path)
        card = probe_file(
            absolute, klass_hint=file.klass, size=file.size, mtime=file.mtime,
            config=self.config,
        )
        card.indexed = bool(file.indexed_at)
        card.chunks = file.chunk_count
        card.index_state = "INDEXED" if file.indexed_at else "NOT_INDEXED"
        return {"root": root.to_dict(), "file": file.to_dict(), "card": card.to_dict()}

    def read_window(
        self, *, root_id: Optional[str] = None, relpath: Optional[str] = None,
        path: Optional[str] = None, offset: int = 0, length: Optional[int] = None,
        as_text: bool = True,
    ) -> dict[str, Any]:
        _, file, absolute = self.find_file(root_id=root_id, relpath=relpath, path=path)
        if file.klass in ("image", "video", "audio", "binary", "archive"):
            as_text = False
        size = max(0, int(length or self.config.window_bytes))
        if size > self.config.max_read_bytes:
            raise SourceError(
                "READ_LIMIT", f"at most {self.config.max_read_bytes} bytes per window"
            )
        start = max(0, int(offset))
        try:
            with open(absolute, "rb") as handle:
                handle.seek(start)
                chunk = handle.read(size + 1)
        except OSError as exc:
            raise SourceError("FILE_GONE", str(exc)) from exc
        truncated = len(chunk) > size
        chunk = chunk[:size]
        payload: dict[str, Any] = {
            "relpath": file.relpath, "name": file.name, "klass": file.klass,
            "offset": start, "requested": size, "read": len(chunk),
            "eof": (start + len(chunk)) >= file.size, "truncated": truncated,
        }
        if as_text:
            payload["text"] = chunk.decode("utf-8", "replace")
        else:
            payload["bytesBase64"] = base64.b64encode(chunk).decode("ascii")
        return payload

    def read_lines(
        self, *, root_id: Optional[str] = None, relpath: Optional[str] = None,
        path: Optional[str] = None, start_line: int = 1, count: Optional[int] = None,
        max_characters: Optional[int] = None,
    ) -> dict[str, Any]:
        _, file, absolute = self.find_file(root_id=root_id, relpath=relpath, path=path)
        start = max(1, int(start_line))
        want = max(1, min(int(count or 200), self.config.max_line_window))
        char_cap = max(1, int(max_characters or self.config.window_bytes))
        lines: list[str] = []
        total = 0
        truncated = False
        started = time.monotonic()
        with open(absolute, "r", encoding="utf-8", errors="replace", newline="") as handle:
            for index, line in enumerate(handle, start=1):
                if index < start:
                    continue
                if len(lines) >= want or total >= char_cap:
                    truncated = True
                    break
                if time.monotonic() - started > 10.0:
                    truncated = True
                    break
                lines.append(line.rstrip("\r\n"))
                total += len(line)
        return {
            "relpath": file.relpath, "startLine": start, "lines": lines,
            "returned": len(lines), "truncated": truncated,
        }

    # ── search / SQL / index ────────────────────────────────────────────────

    def search(self, **kwargs: Any) -> SearchResult:
        result = plan_and_search(
            self.catalog, cfg=self.config, semantic=self.semantic, **kwargs
        )
        if "scan" in result.plan.engines and result.hits:
            self._kick_index(result.hits)
        return result

    def _kick_index(self, hits: list[Hit]) -> None:
        """Adaptive indexing: index what a query just touched, in the background."""
        paths = {(hit.root_id, hit.relpath) for hit in hits[:20]}

        def run() -> None:
            files = []
            for root_id, relpath in paths:
                file = self.catalog.get_file(root_id, relpath)
                if file is not None and not file.indexed_at and file.size <= self.config.index_max_file_bytes:
                    files.append(file)
            if files:
                try:
                    index_files(self.catalog, files, config=self.config, limit_files=20, budget_s=20.0)
                except Exception:  # noqa: BLE001 - adaptive indexing must never break a search
                    pass

        def wrapped() -> None:
            try:
                run()
            finally:
                with self._lock:
                    self._background.discard(thread)

        thread = threading.Thread(target=wrapped, name="sources-adaptive-index", daemon=True)
        with self._lock:
            self._background.add(thread)
        thread.start()

    def sql(
        self, *, sql: str, root_id: Optional[str] = None, relpath: Optional[str] = None,
        path: Optional[str] = None, max_rows: Optional[int] = None,
        all_root_files: bool = False,
    ) -> SqlResult:
        if all_root_files and root_id:
            root = self.catalog.get_root(root_id)
            if root is None:
                raise SourceError("ROOT_UNKNOWN", "the root is not registered")
            files = self.catalog.list_files(root_ids=[root_id], limit=500, order="size_desc")
            paths = [f.abspath for f in files if f.klass == "table"]
            if not paths:
                return SqlResult(ok=False, sql=sql, error="no table files in this root")
            return run_sql(paths, sql, cfg=self.config, max_rows=max_rows)
        _, _, absolute = self.resolve(root_id=root_id, relpath=relpath, path=path)
        if os.path.isdir(absolute):
            files = self.catalog.list_files(
                root_ids=[root_id] if root_id else None, path_prefix=relpath, limit=500,
                order="size_desc",
            )
            paths = [f.abspath for f in files if f.klass == "table"]
            if not paths:
                return SqlResult(ok=False, sql=sql, error="no table files in that folder")
            return run_sql(paths, sql, cfg=self.config, max_rows=max_rows)
        return run_sql(absolute, sql, cfg=self.config, max_rows=max_rows)

    def index(
        self, *, root_ids: Optional[list[str]] = None, limit_files: int = 100,
        budget_s: float = 30.0, semantic: bool = False,
    ) -> dict[str, Any]:
        files = unindexed(self.catalog, root_ids=root_ids, limit=max(1, int(limit_files)))
        result = index_files(
            self.catalog, files, config=self.config, limit_files=limit_files,
            budget_s=budget_s,
        )
        result["unindexed"] = len(files)
        if semantic:
            from .semantic import run_sync

            result["semantic"] = run_sync(self.semantic.index_files(files)) if self.semantic.available else {
                "available": False, "reason": self.semantic.reason,
            }
        return result

    def list_dir(
        self, *, root_id: str, relpath: str = "", limit: int = 500,
    ) -> dict[str, Any]:
        root = self.catalog.get_root(root_id)
        if root is None:
            raise SourceError("ROOT_UNKNOWN", "the root is not registered")
        prefix = normalize_relpath(relpath)
        files = self.catalog.list_files(
            root_ids=[root_id], path_prefix=prefix, limit=max(1, min(limit, 5_000)),
            order="path",
        )
        return {
            "root": root.to_dict(), "prefix": prefix,
            "files": [file.to_dict() for file in files],
            "truncated": len(files) >= min(limit, 5_000),
        }

    def stats(self) -> dict[str, Any]:
        data = self.catalog.stats()
        data["semantic"] = {"available": self.semantic.available, "reason": self.semantic.reason}
        data["roots"] = self.list_roots()
        return data


def build_service(config: Optional[SourceConfig] = None) -> SourceService:
    service = SourceService(config or load_config())
    set_sources_service(service)
    return service


__all__ = ["SourceService", "build_service", "get_sources_service", "set_sources_service"]
