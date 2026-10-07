"""The incremental index engine — walk → parse → persist, never a full rebuild.

`IncrementalIndexer` ties the AST engine to the dedicated `CodeIndex`. On a full
pass it walks the workspace (ignore-aware), skips files whose mtime/size/hash are
unchanged, re-parses only what changed, and deletes rows for removed files. On a
single change it re-parses one file. The fs subsystem's existing `WorkspaceWatcher`
drives it, so the same native/polling backends keep the index current.

The index stores symbols, imports, dependencies, references (bounded identifier
mentions) and call edges — enough for definition, references, dependency graph and
call hierarchy without a second parse.
"""

from __future__ import annotations

import hashlib
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from .. import policy
from ..fs import encoding as fs_encoding
from ..fs import symbols as fs_symbols
from ..fs.watch import WatchEvent
from .ast import ASTEngine
from .language.detect import SOURCE_LANGUAGES, detect_language
from .models import CodeSymbol
from .persistence.index import (
    MAX_INDEX_FILES,
    MAX_INDEX_FILE_BYTES,
    CodeIndex,
    IndexStats,
)

MAX_IDENTIFIERS_PER_FILE = 300
MAX_MENTION_LINES = 20
_MAX_IDENTIFIER = 80
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]{2,}")
_CALL_SITE = re.compile(r"([A-Za-z_][A-Za-z0-9_.]*)\s*\(")
_CALL_STOPWORDS = frozenset({
    "if", "for", "while", "switch", "catch", "return", "function", "typeof",
    "new", "do", "else", "try", "finally", "super", "this", "await", "yield",
    "print", "len", "str", "int", "float", "bool", "list", "dict", "set", "tuple",
    "range", "enumerate", "zip", "isinstance", "super", "None", "True", "False",
})


class IncrementalIndexer:
    """Owns the walk/parse/persist loop for one project index."""

    def __init__(
        self,
        root: Path,
        project_id: str,
        index: CodeIndex,
        *,
        ast: Optional[ASTEngine] = None,
        on_event: Optional[Callable[[str, dict[str, Any]], None]] = None,
    ) -> None:
        self.root = Path(root)
        self.project_id = project_id
        self.index = index
        self.ast = ast or ASTEngine(project_id, root=self.root)
        self._on_event = on_event
        self._lock_ok = True
        # The shared `CodeIndex` connection is `check_same_thread=False`, so two
        # writers (the background watcher loop and a synchronous index trigger) can
        # interleave their DELETE-then-INSERT transactions on one connection and
        # lose rows. Every mutation of this project's index is serialized here; the
        # lock is re-entrant because `index_workspace` calls `_index_one` directly.
        self._mutate_lock = threading.RLock()

    # ── workspace walk ─────────────────────────────────────────────────────────
    def iter_source_files(self) -> Iterator[tuple[str, Path]]:
        for dirpath, dirnames, filenames in os.walk(self.root, followlinks=False):
            current = Path(dirpath)
            dirnames[:] = [d for d in dirnames if d not in policy.IGNORED_DIRS]
            for name in filenames:
                full = current / name
                try:
                    rel = full.relative_to(self.root).as_posix()
                except ValueError:
                    continue
                if policy.is_ignored(rel) or policy.is_protected(rel):
                    continue
                if detect_language(rel) not in SOURCE_LANGUAGES:
                    continue
                yield rel, full

    def index_workspace(self, *, force: bool = False, max_files: int = MAX_INDEX_FILES) -> IndexStats:
        started = time.monotonic()
        stats = IndexStats()
        with self._mutate_lock:
            return self._index_workspace_locked(stats, started, force=force, max_files=max_files)

    def _index_workspace_locked(
        self, stats: "IndexStats", started: float, *, force: bool, max_files: int,
    ) -> "IndexStats":
        if force:
            self.index.clear()
        known = self.index.known_files()
        seen: set[str] = set()
        for rel, full in self.iter_source_files():
            if stats.scanned >= max_files:
                stats.truncated = True
                break
            stats.scanned += 1
            seen.add(rel)
            try:
                st = full.stat()
            except OSError:
                continue
            if st.st_size > MAX_INDEX_FILE_BYTES:
                continue
            prior = self.index.file_signature(rel)
            if prior is not None and prior[2] == st.st_mtime_ns and prior[1] == st.st_size:
                stats.unchanged += 1
                continue
            try:
                decoded = fs_encoding.read_text(full)
            except Exception:  # noqa: BLE001 - an unreadable file is skipped
                continue
            digest = hashlib.sha256(decoded.text.encode("utf-8")).hexdigest()
            if prior is not None and prior[0] == digest:
                # Content identical despite a touch: refresh mtime only, keep rows.
                self.index.touch_file(rel, mtime_ns=st.st_mtime_ns, size=st.st_size)
                stats.unchanged += 1
                continue
            count = self._index_one(rel, full, decoded.text, st.st_mtime_ns, st.st_size, digest)
            stats.updated += 1
            stats.symbols += count
        for rel in known - seen:
            self.index.remove_file(rel)
            stats.removed += 1
        stats.duration_ms = int((time.monotonic() - started) * 1000)
        self._emit("intel.index.completed", stats.to_dict())
        return stats

    def reindex_file(self, rel: str) -> bool:
        """Re-parse ONE file. False when it is gone/ignored (row removed)."""
        with self._mutate_lock:
            return self._reindex_file_locked(rel)

    def _reindex_file_locked(self, rel: str) -> bool:
        if policy.is_ignored(rel) or policy.is_protected(rel):
            self.index.remove_file(rel)
            return False
        try:
            full = (self.root / rel).resolve()
        except OSError:
            self.index.remove_file(rel)
            return False
        if not full.exists() or not full.is_file() or detect_language(rel) not in SOURCE_LANGUAGES:
            self.index.remove_file(rel)
            return False
        try:
            st = full.stat()
            if st.st_size > MAX_INDEX_FILE_BYTES:
                self.index.remove_file(rel)
                return False
            decoded = fs_encoding.read_text(full)
        except Exception:  # noqa: BLE001
            self.index.remove_file(rel)
            return False
        digest = hashlib.sha256(decoded.text.encode("utf-8")).hexdigest()
        self._index_one(rel, full, decoded.text, st.st_mtime_ns, st.st_size, digest)
        self._emit("intel.index.file", {"file": rel})
        return True

    def apply_watch_events(self, events: list[WatchEvent]) -> dict[str, Any]:
        """Apply debounced watcher events: update/remove only affected files."""
        updated = removed = 0
        with self._mutate_lock:
            for event in events:
                try:
                    if event.event == "deleted":
                        self.index.remove_file(event.path)
                        removed += 1
                    else:
                        if self._reindex_file_locked(event.path):
                            updated += 1
                        if event.event == "renamed" and event.old_path:
                            self.index.remove_file(event.old_path)
                            removed += 1
                except Exception:  # noqa: BLE001 - a bad event must not stop the loop
                    continue
        result = {"updated": updated, "removed": removed, "processed": len(events)}
        if events:
            self._emit("intel.index.incremental", result)
        return result

    def _index_one(
        self, rel: str, full: Path, text: str, mtime_ns: int, size: int, digest: str,
    ) -> int:
        parsed = self.ast.parse_file(rel, text)
        symbols = [s.to_dict() for s in parsed.symbols]
        imports = [i.to_dict() for i in parsed.imports]
        dependencies = [d.to_dict() for d in parsed.dependencies]
        references = self._references(parsed.symbols, text)
        call_edges = extract_call_edges(self.project_id, rel, text, parsed.symbols)
        try:
            return self.index.upsert_file(
                rel=rel, language=parsed.language, sha256=digest, size=size,
                mtime_ns=mtime_ns, line_count=parsed.line_count, engine=parsed.engine,
                symbols=symbols, imports=imports, dependencies=dependencies,
                references=references, call_edges=call_edges,
            )
        except Exception as exc:  # noqa: BLE001 - a persistence failure is a diagnostic
            self._emit("intel.index.file_failed", {"file": rel, "error": str(exc)[:200]})
            return 0

    def _references(self, symbols: list[CodeSymbol], text: str) -> list[dict[str, Any]]:
        """Bounded identifier → mention rows, marking definition sites."""
        declaration_lines: dict[str, set[int]] = {}
        for symbol in symbols:
            declaration_lines.setdefault(symbol.name, set()).add(symbol.line)
        out: list[dict[str, Any]] = []
        seen: dict[str, int] = {}
        for index, line in enumerate(text.splitlines(), start=1):
            if len(line) > 2_000:
                line = line[:2_000]
            for match in _IDENTIFIER.finditer(line):
                name = match.group(0)
                if len(name) > _MAX_IDENTIFIER:
                    continue
                count = seen.get(name, 0)
                if count >= MAX_MENTION_LINES:
                    continue
                seen[name] = count + 1
                if len(seen) > MAX_IDENTIFIERS_PER_FILE and name not in declaration_lines:
                    continue
                out.append({
                    "name": name, "line": index, "column": match.start() + 1,
                    "definition": index in declaration_lines.get(name, ()),
                })
        return out

    def _emit(self, event_type: str, data: dict[str, Any]) -> None:
        if self._on_event is None:
            return
        try:
            self._on_event(event_type, data)
        except Exception:  # noqa: BLE001
            pass


def extract_call_edges(
    project_id: str, rel: str, text: str, symbols: list[CodeSymbol],
) -> list[dict[str, Any]]:
    """Best-effort call edges: calls whose site falls inside a symbol's span.

    Deterministic and conservative: only a `name(` occurrence inside a known
    function/method's line span (or the whole file when spans are unknown) becomes
    an edge. A call to something that is not a known symbol stays `resolved=False`
    so the caller can tell a resolved call from an unresolved name.
    """
    functions = [
        s for s in symbols if s.kind in ("function", "method", "constructor")
    ]
    known_names = {s.name for s in symbols}
    lines = text.splitlines()
    edges: list[dict[str, Any]] = []
    if not functions:
        functions = [CodeSymbol(id=f"{project_id}:{rel}:0:0:<module>", name="<module>",
                                kind="module", file=rel, line=1, project_id=project_id)]
        span_end = len(lines)
    else:
        span_end = None
    for caller in functions:
        end = min(caller.end_line or len(lines), len(lines))
        start = max(1, caller.line)
        for line_no in range(start, end + 1):
            raw = lines[line_no - 1]
            for match in _CALL_SITE.finditer(raw):
                name = match.group(1).split(".")[-1]
                if name in _CALL_STOPWORDS or not name:
                    continue
                if name == caller.name:
                    continue
                edges.append({
                    "caller": caller.id, "callerName": caller.name,
                    "callee": name if name in known_names else name,
                    "calleeName": name, "line": line_no,
                    "resolved": name in known_names, "engine": "ast",
                })
                if len(edges) >= 500:
                    return edges
    return edges


__all__ = [
    "IncrementalIndexer",
    "extract_call_edges",
]
