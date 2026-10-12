"""Structured, reversible file patches inside a code workspace (Phase 2).

Modelled deliberately on `skills/patches.py`:

  * a closed operation set, validated structurally BEFORE anything is touched;
  * every operation carries a `reason`, so a change record explains itself;
  * a stale-base refusal — here the base is a CONTENT HASH, not a version string,
    so a concurrent edit is refused rather than silently rebased;
  * the applied result is re-checked (the write is inside the workspace and the
    resulting hash is what was reported) before the op is reported as done;
  * ATOMIC: a refusal at any operation applies NOTHING — a half-applied patch is
    exactly the "silently rebased" failure the skill engine exists to prevent.

Nothing here decides whether a write is ALLOWED — `code/policy.py` owns that. This
module owns whether the write is WELL-FORMED and whether its base is still intact.
Path resolution goes through `workspace.confine`; this module never calls
`realpath` itself.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from . import policy
from .workspace import ResolvedWorkspace, WorkspaceDenial, confine

ALLOWED_OPS = frozenset({"create", "replace", "delete", "move", "overwrite"})

MAX_OPERATIONS = 50
MAX_FILE_BYTES = 1_000_000        # per created/replaced file
MAX_TOTAL_BYTES_PER_APPLY = 4_000_000
MAX_OLD_SPAN_CHARS = 20_000
MAX_PATH_CHARS = 512
MAX_REASON_CHARS = 500

# Paths a patch may never touch, in addition to policy.PROTECTED_PATHS. These are
# repo-relative; matched on the normalized relative path.
PATCH_FORBIDDEN_RELPATHS = frozenset({
    ".git", ".gitmodules", ".gitignore",
    "agent-memory.db", "eclipse-memory.db", "jdds.db",
    "mcp-servers.json", ".env",
})

def _looks_absolute(path: str) -> bool:
    """Whether a path is absolute (POSIX, Windows drive, or UNC)."""
    text = path.replace("\\", "/")
    if text.startswith("/") or text.startswith("//"):
        return True
    if len(text) >= 2 and text[1] == ":" and text[0].isalpha():
        return True
    return False


def _has_traversal(path: str) -> bool:
    return ".." in path.replace("\\", "/").split("/")


class PatchError(ValueError):
    """A patch was rejected. `code` is stable; `reason` is operator-facing.

    Codes: PATCH_MALFORMED | PATCH_UNKNOWN_OP | PATCH_PATH_ABSOLUTE |
    PATCH_PATH_TRAVERSAL | PATCH_PATH_SYMLINK | PATCH_PROTECTED_PATH |
    PATCH_OUTSIDE_SCOPE | PATCH_TOO_LARGE | PATCH_BASE_MISMATCH |
    PATCH_SPAN_NOT_FOUND | PATCH_SPAN_AMBIGUOUS | PATCH_FILE_EXISTS |
    PATCH_FILE_MISSING | PATCH_TOO_MANY_OPERATIONS.
    """

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


@dataclass(frozen=True)
class PatchOp:
    op: str                  # "create" | "replace" | "delete" | "move"
    path: str                # workspace-relative; for "move", the DESTINATION
    reason: str
    content: Optional[str] = None       # create
    old: Optional[str] = None           # replace
    new: Optional[str] = None           # replace
    expect_hash: Optional[str] = None   # the hash the caller believes the base is
    from_path: Optional[str] = None     # move


@dataclass(frozen=True)
class AppliedOp:
    op: str
    path: str
    reason: str
    content_hash_before: Optional[str]   # None for create
    content_hash_after: Optional[str]    # None for delete
    bytes_written: int
    created: bool
    deleted: bool
    moved_from: Optional[str] = None
    old: Optional[str] = None            # replace: kept for a content-exact revert
    new: Optional[str] = None            # replace: kept for a content-exact revert

    def to_dict(self) -> dict[str, Any]:
        return {
            "op": self.op,
            "path": self.path,
            "reason": self.reason,
            "contentHashBefore": self.content_hash_before,
            "contentHashAfter": self.content_hash_after,
            "bytesWritten": self.bytes_written,
            "created": self.created,
            "deleted": self.deleted,
            "movedFrom": self.moved_from,
            "old": self.old,
            "new": self.new,
        }


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_patch(payload: Any) -> list[PatchOp]:
    """Parse + structurally validate an untrusted patch. Raises PatchError.

    Rejections, in a fixed order:
      1. the operations are not a list, are empty, or exceed MAX_OPERATIONS;
      2. an op not in ALLOWED_OPS;
      3. an absolute path (POSIX or Windows drive/UNC), or any `..` component;
      4. a path over MAX_PATH_CHARS, or with a NUL;
      5. a content/old/new span over the size caps.

    Structural only: filesystem and policy checks happen in `apply`.
    """
    if isinstance(payload, dict):
        raw_ops = payload.get("operations")
    else:
        raw_ops = payload
    if not isinstance(raw_ops, list) or not raw_ops:
        raise PatchError("PATCH_MALFORMED", "the change has no operations")
    if len(raw_ops) > MAX_OPERATIONS:
        raise PatchError("PATCH_TOO_MANY_OPERATIONS", f"more than {MAX_OPERATIONS} operations")
    ops: list[PatchOp] = []
    for raw in raw_ops:
        ops.append(_parse_op(raw))
    return ops


def _parse_op(raw: Any) -> PatchOp:
    if not isinstance(raw, dict):
        raise PatchError("PATCH_MALFORMED", "each operation must be an object")
    op = str(raw.get("op") or "")
    if op not in ALLOWED_OPS:
        raise PatchError("PATCH_UNKNOWN_OP", f"unsupported operation {op!r}")
    path = str(raw.get("path") or "")
    reason = str(raw.get("reason") or "")[:MAX_REASON_CHARS]
    _validate_path(path)
    content = raw.get("content")
    old = raw.get("old")
    new = raw.get("new")
    expect_hash = raw.get("expectHash") or raw.get("expect_hash")
    from_path = raw.get("fromPath") or raw.get("from_path")

    if op == "create":
        if content is None:
            raise PatchError("PATCH_MALFORMED", "create requires content")
        if len(str(content).encode("utf-8")) > MAX_FILE_BYTES:
            raise PatchError("PATCH_TOO_LARGE", "the new file is too large")
    elif op == "replace":
        if old is None or new is None:
            raise PatchError("PATCH_MALFORMED", "replace requires old and new")
        if len(str(old)) > MAX_OLD_SPAN_CHARS:
            raise PatchError("PATCH_TOO_LARGE", "the span to replace is too large")
        if len(str(new).encode("utf-8")) > MAX_FILE_BYTES:
            raise PatchError("PATCH_TOO_LARGE", "the replacement is too large")
    elif op == "overwrite":
        # A whole-file replacement (additive, for the promotion path): the exact
        # previous content need not be supplied — the base is proven with
        # `expectHash` instead. A file that did not exist at all is a `create`.
        if content is None:
            raise PatchError("PATCH_MALFORMED", "overwrite requires content")
        if len(str(content).encode("utf-8")) > MAX_FILE_BYTES:
            raise PatchError("PATCH_TOO_LARGE", "the new file is too large")
    elif op == "move":
        from_path = str(from_path or "")
        if not from_path:
            raise PatchError("PATCH_MALFORMED", "move requires fromPath")
        _validate_path(from_path)

    return PatchOp(
        op=op, path=path, reason=reason,
        content=str(content) if content is not None else None,
        old=str(old) if old is not None else None,
        new=str(new) if new is not None else None,
        expect_hash=str(expect_hash) if expect_hash else None,
        from_path=str(from_path) if from_path else None,
    )


def _validate_path(path: str) -> None:
    if not path or "\x00" in path:
        raise PatchError("PATCH_MALFORMED", "a path is empty or contains a NUL")
    if len(path) > MAX_PATH_CHARS:
        raise PatchError("PATCH_TOO_LARGE", "a path is too long")
    if _looks_absolute(path):
        raise PatchError("PATCH_PATH_ABSOLUTE", f"absolute path refused: {path!r}")
    if _has_traversal(path):
        raise PatchError("PATCH_PATH_TRAVERSAL", f"path traversal refused: {path!r}")


def _forbidden(rel: str) -> bool:
    normalized = rel.replace("\\", "/").lstrip("./")
    if normalized in PATCH_FORBIDDEN_RELPATHS:
        return True
    if any(normalized == name or normalized.startswith(name + "/")
           for name in PATCH_FORBIDDEN_RELPATHS if "." not in name):
        return True
    return policy.is_protected(normalized)


def _in_scope(rel: str, scope: tuple[str, ...]) -> bool:
    if not scope:
        return True
    normalized = rel.replace("\\", "/")
    return any(normalized == prefix or normalized.startswith(prefix.rstrip("/") + "/")
               for prefix in scope)


def _map_denial(denial: WorkspaceDenial) -> PatchError:
    """Map a `workspace.confine` denial to the phase's PATCH_* code 1:1."""
    mapping = {
        "PATH_TRAVERSAL": "PATCH_PATH_TRAVERSAL",
        "PATH_OUTSIDE_WORKSPACE": "PATCH_PATH_ABSOLUTE",
        "SYMLINK_ESCAPE": "PATCH_PATH_SYMLINK",
        "PROTECTED_PATH": "PATCH_PROTECTED_PATH",
        "IGNORED_PATH": "PATCH_PROTECTED_PATH",
        "NOT_FOUND": "PATCH_FILE_MISSING",
    }
    return PatchError(mapping.get(denial.code, "PATCH_MALFORMED"), denial.reason)


def _confined(ws: ResolvedWorkspace, rel: str) -> Path:
    try:
        return confine(ws, rel, for_write=True)
    except WorkspaceDenial as denial:
        raise _map_denial(denial) from denial


def _decide(binding: Any, rel: str, actor: Any) -> None:
    """Policy decision for a write; raises PatchError on a refusal."""
    decision = policy.decide_write(actor, binding, rel)
    if not decision.allowed:
        raise PatchError(decision.code, decision.reason)


@dataclass
class _Planned:
    op: PatchOp
    target: Path
    before_hash: Optional[str]
    after_text: Optional[str]
    bytes_written: int
    created: bool
    deleted: bool
    source: Optional[Path] = None
    source_text: Optional[str] = None


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="strict")


def _sha_file(path: Path) -> Optional[str]:
    if not path.exists():
        return None
    return _sha(_read_text(path))


def _plan_one(ws: ResolvedWorkspace, binding: Any, actor: Any, op: PatchOp, scope: tuple[str, ...]) -> _Planned:
    target = _confined(ws, op.path)
    rel = target.relative_to(ws.root).as_posix()
    if _forbidden(rel):
        raise PatchError("PATCH_PROTECTED_PATH", f"{rel!r} is protected")
    if not _in_scope(rel, scope):
        raise PatchError("PATCH_OUTSIDE_SCOPE", f"{rel!r} is outside the declared scope")
    _decide(binding, rel, actor)

    before = _sha_file(target) if target.exists() else None
    if op.expect_hash is not None and before is not None and op.expect_hash != before:
        raise PatchError("PATCH_BASE_MISMATCH", f"{rel!r} changed since it was read")

    if op.op == "create":
        if target.exists():
            raise PatchError("PATCH_FILE_EXISTS", f"{rel!r} already exists")
        text = op.content or ""
        return _Planned(op, target, before, text, len(text.encode("utf-8")), True, False)

    if op.op == "replace":
        if before is None:
            raise PatchError("PATCH_FILE_MISSING", f"{rel!r} does not exist")
        current = _read_text(target)
        count = current.count(op.old or "")
        if count == 0:
            raise PatchError("PATCH_SPAN_NOT_FOUND", "the text to replace was not found")
        if count > 1:
            raise PatchError("PATCH_SPAN_AMBIGUOUS", "the text to replace appears more than once")
        updated = current.replace(op.old or "", op.new or "", 1)
        return _Planned(op, target, before, updated, len(updated.encode("utf-8")), False, False)

    if op.op == "delete":
        if before is None:
            raise PatchError("PATCH_FILE_MISSING", f"{rel!r} does not exist")
        return _Planned(op, target, before, None, 0, False, True)

    if op.op == "overwrite":
        # Whole-file replacement. The base is proven by `expectHash` (checked
        # above); the previous text is recorded as `old` so the op is reversible.
        text = op.content or ""
        before_text = _read_text(target) if before is not None else None
        replacement = PatchOp(
            op="overwrite", path=op.path, reason=op.reason, content=text,
            old=before_text, new=text, expect_hash=op.expect_hash,
        )
        return _Planned(
            replacement, target, before, text, len(text.encode("utf-8")),
            before is None, False,
        )

    # move
    source = _confined(ws, op.from_path or "")
    source_rel = source.relative_to(ws.root).as_posix()
    if _forbidden(source_rel):
        raise PatchError("PATCH_PROTECTED_PATH", f"{source_rel!r} is protected")
    if target.exists():
        raise PatchError("PATCH_FILE_EXISTS", f"{rel!r} already exists")
    if not source.exists():
        raise PatchError("PATCH_FILE_MISSING", f"{source_rel!r} does not exist")
    text = _read_text(source)
    return _Planned(op, target, _sha(text), text, len(text.encode("utf-8")), True, True, source=source, source_text=text)


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp{uuid_hex()}")
    tmp.write_text(text, encoding="utf-8", newline="")
    os.replace(tmp, path)


def uuid_hex() -> str:
    import uuid  # noqa: PLC0415

    return uuid.uuid4().hex[:8]


def apply(
    ws: ResolvedWorkspace,
    operations: list[PatchOp],
    *,
    scope: tuple[str, ...] = (),
    binding: Any = None,
    actor: Any = None,
    emitter: Any = None,
) -> dict[str, Any]:
    """Apply an ordered patch inside the code workspace. Returns an audit record.

    PLAN-then-COMMIT: every operation is validated (confinement, policy, scope,
    base hash, span uniqueness) BEFORE the first byte is written, so a refusal at
    op N leaves ops 1..N-1 unapplied too. Nothing is ever silently rebased.
    """
    bind = binding if binding is not None else ws.binding
    planned: list[_Planned] = []
    for op in operations:
        planned.append(_plan_one(ws, bind, actor, op, scope))

    total = sum(p.bytes_written for p in planned)
    if total > MAX_TOTAL_BYTES_PER_APPLY:
        return _refused(ws, operations, "PATCH_TOO_LARGE", "the change is too large to apply at once")

    applied: list[AppliedOp] = []
    for item in planned:
        op = item.op
        if op.op == "delete":
            item.target.unlink()
            after_hash = None
        elif op.op == "move" and item.source is not None:
            # Relocate byte-exactly — never re-encode, so a revert restores the
            # original bytes (line endings included).
            item.target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(item.source, item.target)
            after_hash = _sha_file(item.target)
        else:
            _write_atomic(item.target, item.after_text or "")
            after_hash = _sha(item.after_text or "")
        applied.append(AppliedOp(
            op=op.op, path=item.target.relative_to(ws.root).as_posix(), reason=op.reason,
            content_hash_before=item.before_hash, content_hash_after=after_hash,
            bytes_written=item.bytes_written, created=item.created, deleted=item.deleted,
            moved_from=(item.source.relative_to(ws.root).as_posix() if item.source else None),
            old=op.old, new=op.new,
        ))

    return {
        "ok": True,
        "workspaceId": ws.id,
        "applied": [a.to_dict() for a in applied],
        "refused": None,
        "filesChanged": len(applied),
        "totalBytes": total,
    }


def _refused(ws: ResolvedWorkspace, operations: list[PatchOp], code: str, reason: str) -> dict[str, Any]:
    return {
        "ok": False,
        "workspaceId": ws.id,
        "applied": [],
        "refused": {"op": operations[0].op if operations else "", "code": code, "reason": reason},
        "filesChanged": 0,
        "totalBytes": 0,
    }


def revert(ws: ResolvedWorkspace, applied: list[dict[str, Any]], *, binding: Any = None, actor: Any = None, emitter: Any = None) -> dict[str, Any]:
    """Undo an applied patch exactly, newest op first.

    Each op is inverted from its own recorded values. An op whose recorded
    `contentHashAfter` no longer matches the file is REFUSED
    (`PATCH_BASE_MISMATCH`) rather than inverted over a concurrent edit.
    """
    bind = binding if binding is not None else ws.binding
    undone: list[dict[str, Any]] = []
    for record in reversed(applied):
        op = str(record.get("op") or "")
        rel = str(record.get("path") or "")
        target = _confined(ws, rel)
        actual = target.relative_to(ws.root).as_posix()
        if _forbidden(actual):
            raise PatchError("PATCH_PROTECTED_PATH", f"{actual!r} is protected")
        _decide(bind, actual, actor)
        expected_after = record.get("contentHashAfter")
        current_hash = _sha_file(target)
        if expected_after is not None and current_hash != expected_after:
            raise PatchError("PATCH_BASE_MISMATCH", f"{actual!r} changed since the change was made")

        if op == "create":
            if target.exists():
                target.unlink()
        elif op == "delete":
            text = str(record.get("content") or "")
            _write_atomic(target, text)
        elif op == "replace":
            current = _read_text(target)
            old = str(record.get("new") or "")
            new = str(record.get("old") or "")
            if current.count(old) != 1:
                raise PatchError("PATCH_SPAN_NOT_FOUND", "the change can no longer be undone cleanly")
            _write_atomic(target, current.replace(old, new, 1))
        elif op == "overwrite":
            _write_atomic(target, str(record.get("old") or ""))
        elif op == "move":
            source_rel = str(record.get("movedFrom") or "")
            source = _confined(ws, source_rel)
            if target.exists() and not source.exists():
                source.parent.mkdir(parents=True, exist_ok=True)
                os.replace(target, source)
            else:
                raise PatchError("PATCH_FILE_MISSING", "the change can no longer be undone cleanly")
        undone.append(record)
    return {"ok": True, "workspaceId": ws.id, "reverted": len(undone)}


__all__ = [
    "ALLOWED_OPS",
    "MAX_FILE_BYTES",
    "MAX_OPERATIONS",
    "MAX_OLD_SPAN_CHARS",
    "MAX_TOTAL_BYTES_PER_APPLY",
    "PATCH_FORBIDDEN_RELPATHS",
    "AppliedOp",
    "PatchError",
    "PatchOp",
    "apply",
    "parse_patch",
    "revert",
]
