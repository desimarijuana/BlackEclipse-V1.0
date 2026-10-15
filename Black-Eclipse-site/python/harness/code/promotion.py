"""Landing a change: confirmed promotion from a disposable copy to the checkout.

Phase 15 (ADR-H119). A code run writes into a DISPOSABLE copy of the project
(`code/worktree.py`); nothing in the runtime ever copies that change back. This
module owns the ONE promotion path:

  1. a PREVIEW names exactly which files would change in the user's real folder,
     with the before/after content hashes and a digest over that exact set;
  2. the runtime records a SINGLE-USE approval bound to that digest;
  3. only an operator's confirmation (the approval) APPLIES it — and only if
     neither the target nor the previewed copy changed since the preview.

It reuses the existing authorities instead of re-implementing them:

  * `worktree.diff` names the changed files in the disposable copy;
  * `code/patch.py` performs the write (path confinement, protected paths, base
    hashes, plan-then-commit atomicity);
  * `mcp/approvals.py` (`request_kind`/`consume_kind`) is the single-use decision.

No git write happens here. A protected path — `code/policy.py` and the other
frozen authorities, `.git`, `.env`, the databases, keys and migrations — can never
be promoted: `policy.is_protected` refuses it in the preview and `patch.apply`
refuses it again at apply time. The target is ALWAYS the server-resolved checkout
root, never a caller-supplied path.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Optional

from . import patch as patch_mod
from . import policy
from . import worktree as worktree_mod
from .patch import PatchError, PatchOp
from .policy import WorkspaceBinding
from .workspace import ResolvedWorkspace, default_root

# The approval kind for a promotion. One store (`McpApproval`), a third kind.
PROMOTION_KIND = "code_promote"

# Bounds. A promotion is an exact, bounded set of files, never a bulk move.
MAX_PROMOTION_FILES = 200
MAX_PROMOTION_BYTES = patch_mod.MAX_TOTAL_BYTES_PER_APPLY

# Where the ORIGINAL contents of a promoted change are kept, so it can be put
# back exactly. Inside the repo's gitignored `.black-eclipse/`, never tracked.
ROLLBACK_ROOT_RELPATH = ".black-eclipse/promotions"


class PromotionError(Exception):
    """A promotion was refused. `code` is stable; `reason` is operator-facing.

    Codes: PROMOTION_UNAVAILABLE | PROMOTION_NO_CHANGE | PROMOTION_ALREADY_DIRECT |
    PROMOTION_OUT_OF_SCOPE | PROMOTION_BASE_CHANGED | PROMOTION_PREVIEW_STALE |
    PROMOTION_NOT_APPROVED | PROMOTION_TOO_MANY_FILES | PROMOTION_TOO_LARGE |
    PROMOTION_FAILED.
    """

    def __init__(self, code: str, reason: str) -> None:
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_text_strict(path: Path) -> str:
    """Read a project file as UTF-8 text, or refuse.

    A promotion is a text change (source, docs, config). A binary or unreadable
    file is refused honestly (`PROMOTION_OUT_OF_SCOPE`) rather than copied byte-
    blind through a text engine.
    """
    try:
        return path.read_text(encoding="utf-8", errors="strict")
    except (UnicodeDecodeError, OSError) as exc:
        raise PromotionError(
            "PROMOTION_OUT_OF_SCOPE",
            f"{path.name} isn't a text change Eclipse can put into your project",
        ) from exc


def promotion_digest(files: list[dict[str, Any]]) -> str:
    """A stable digest over the exact previewed file set (order-independent)."""
    canonical = "\n".join(
        f"{f.get('path')}\x00{f.get('op')}\x00{f.get('beforeHash') or ''}\x00{f.get('afterHash') or ''}"
        for f in sorted(files, key=lambda f: str(f.get("path")))
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _operator_actor(binding_id: str) -> Any:
    from ..skills.permissions import Actor  # noqa: PLC0415

    # An operator-confirmed write. The `code.write` verb comes from `edit_verify`;
    # the confirmation itself is the single-use approval consumed by the route.
    return Actor(id="promoter", operator=True, workspace_id=binding_id, autonomy="edit_verify")


def _recent_workspace(code_store: Any, run_id: str) -> Optional[dict[str, Any]]:
    """The run's most recent unreleased disposable workspace, or None."""
    if code_store is None:
        return None
    try:
        rows = code_store.list_workspaces(run_id=run_id, limit=20)
    except Exception:  # noqa: BLE001 - a store failure means "nothing to promote"
        return None
    live = [r for r in rows if not r.get("releasedAt")]
    return live[0] if live else None


def build_preview(
    run_id: str, *, code_store: Any, checkout_root: Optional[Path] = None,
) -> dict[str, Any]:
    """The exact set of changes a run made, ready for a human to confirm.

    Raises `PromotionError` when there is nothing to promote, the change is
    already in the real folder, or the change touches a protected/escaping path.
    Reads only; writes nothing.
    """
    row = _recent_workspace(code_store, run_id)
    if row is None:
        raise PromotionError(
            "PROMOTION_NO_CHANGE",
            "There's no prepared change from this task to put into your project.",
        )
    strategy = str(row.get("strategy") or "")
    if strategy == "direct":
        raise PromotionError(
            "PROMOTION_ALREADY_DIRECT",
            "This task already changed your folder directly, so there's nothing to put back.",
        )
    ws_id = str(row.get("id") or "")
    worktree_root = Path(str(row.get("root") or ""))
    if not ws_id or not worktree_root.is_dir():
        raise PromotionError(
            "PROMOTION_NO_CHANGE",
            "The prepared change from this task is no longer available.",
        )
    checkout = Path(checkout_root) if checkout_root is not None else default_root()
    if checkout is None:
        raise PromotionError("PROMOTION_UNAVAILABLE", "There's no project folder to put the change into.")
    checkout = Path(checkout)
    base = str(row.get("baseRevision") or "HEAD") or "HEAD"

    diff = worktree_mod.diff(ws_id, base, strategy=strategy)
    specs: list[tuple[str, str]] = []
    specs += [(p, "create") for p in (diff.get("added") or [])]
    specs += [(p, "overwrite") for p in (diff.get("modified") or [])]
    specs += [(p, "delete") for p in (diff.get("deleted") or [])]
    if not specs:
        raise PromotionError(
            "PROMOTION_NO_CHANGE",
            "This task didn't change any files, so there's nothing to put into your project.",
        )
    if len(specs) > MAX_PROMOTION_FILES:
        raise PromotionError(
            "PROMOTION_TOO_MANY_FILES",
            f"This change touches more than {MAX_PROMOTION_FILES} files; Eclipse won't put it in at once.",
        )

    files: list[dict[str, Any]] = []
    total_bytes = 0
    for raw_path, op in specs:
        rel = str(raw_path).replace("\\", "/").lstrip("./")
        if not rel:
            continue
        if policy.is_protected(rel) or policy.is_ignored(rel):
            raise PromotionError(
                "PROMOTION_OUT_OF_SCOPE",
                "This change touches a file Eclipse isn't allowed to put into your project.",
            )
        try:
            policy.resolve_within(checkout, rel)
        except policy.PolicyDenial as denial:
            raise PromotionError("PROMOTION_OUT_OF_SCOPE", denial.reason) from denial

        target = checkout / rel
        before_hash: Optional[str] = None
        if target.exists():
            before_hash = _sha_text(_read_text_strict(target))
        after_hash: Optional[str] = None
        after_text: Optional[str] = None
        if op != "delete":
            after_text = _read_text_strict(worktree_root / rel)
            after_hash = _sha_text(after_text)
            total_bytes += len(after_text.encode("utf-8"))

        if op == "create" and before_hash is not None:
            raise PromotionError(
                "PROMOTION_BASE_CHANGED",
                f"{rel} already exists in your project, so Eclipse won't overwrite it.",
            )
        if op in ("overwrite", "delete") and before_hash is None:
            raise PromotionError(
                "PROMOTION_BASE_CHANGED",
                f"{rel} is missing from your project, so Eclipse can't put this change in.",
            )
        files.append({"path": rel, "op": op, "beforeHash": before_hash, "afterHash": after_hash})

    if total_bytes > MAX_PROMOTION_BYTES:
        raise PromotionError(
            "PROMOTION_TOO_LARGE",
            "This change is too large to put into your project at once.",
        )

    files.sort(key=lambda f: str(f.get("path")))
    added = sum(1 for f in files if f["op"] == "create")
    modified = sum(1 for f in files if f["op"] == "overwrite")
    deleted = sum(1 for f in files if f["op"] == "delete")
    return {
        "workspaceId": ws_id,
        "runId": run_id,
        "checkoutRoot": str(checkout),
        "worktreeRoot": str(worktree_root),
        "strategy": strategy,
        "files": files,
        "filesChanged": len(files),
        "added": added,
        "modified": modified,
        "deleted": deleted,
        "previewDigest": promotion_digest(files),
        "unified": str(diff.get("unified") or ""),
        "truncated": bool(diff.get("truncated")),
    }


_BASE_CODES = {"PATCH_BASE_MISMATCH", "PATCH_FILE_EXISTS", "PATCH_FILE_MISSING"}
_SCOPE_CODES = {
    "PATCH_PROTECTED_PATH", "PATCH_OUTSIDE_SCOPE",
    "PATCH_PATH_TRAVERSAL", "PATCH_PATH_ABSOLUTE", "PATCH_PATH_SYMLINK",
}


def _map_patch_error(code: str, reason: str) -> PromotionError:
    if code in _BASE_CODES:
        return PromotionError("PROMOTION_BASE_CHANGED", reason or "Your project changed since the preview.")
    if code in _SCOPE_CODES:
        return PromotionError("PROMOTION_OUT_OF_SCOPE", reason or "This change isn't allowed in your project.")
    if code == "PATCH_TOO_LARGE":
        return PromotionError("PROMOTION_TOO_LARGE", reason or "This change is too large.")
    return PromotionError("PROMOTION_FAILED", reason or code or "The change couldn't be put into your project.")


def apply_promotion(preview: dict[str, Any]) -> dict[str, Any]:
    """Apply a CONFIRMED preview to the real checkout.

    The caller MUST have already consumed the single-use approval bound to
    `preview['previewDigest']`. This function re-checks the previewed content
    (each disposable-copy file still hashes to its previewed value) and the target
    base (each checkout file still hashes to its previewed value), then writes
    atomically through `patch.apply`. Raises `PromotionError` on any mismatch.
    """
    checkout = Path(str(preview.get("checkoutRoot") or ""))
    worktree_root = Path(str(preview.get("worktreeRoot") or ""))
    files = list(preview.get("files") or [])
    if not checkout or not worktree_root or not files:
        raise PromotionError("PROMOTION_NO_CHANGE", "There's nothing to put into your project.")

    ops: list[PatchOp] = []
    for f in files:
        rel = str(f.get("path") or "")
        op = str(f.get("op") or "")
        if not rel or op not in ("create", "overwrite", "delete"):
            raise PromotionError("PROMOTION_FAILED", "The prepared change is not valid.")
        if op == "delete":
            ops.append(PatchOp(
                op="delete", path=rel, reason="Put the reviewed change into the project.",
                expect_hash=f.get("beforeHash"),
            ))
            continue
        text = _read_text_strict(worktree_root / rel)
        if _sha_text(text) != f.get("afterHash"):
            raise PromotionError(
                "PROMOTION_PREVIEW_STALE",
                "The prepared change was altered after you reviewed it; review it again.",
            )
        if op == "create":
            ops.append(PatchOp(
                op="create", path=rel, reason="Put the reviewed change into the project.",
                content=text,
            ))
        else:
            ops.append(PatchOp(
                op="overwrite", path=rel, reason="Put the reviewed change into the project.",
                content=text, expect_hash=f.get("beforeHash"),
            ))

    # Capture the ORIGINAL contents BEFORE writing, so the change can be put back
    # exactly (inverse promotion). Reads only; a failure here aborts before any
    # write. Both versions survive: the backup directory is kept after apply.
    rollback_id = _capture_backup(checkout, preview, files)

    binding_id = "promote_" + hashlib.sha256(str(checkout).encode("utf-8")).hexdigest()[:16]
    binding = WorkspaceBinding(id=binding_id, root=checkout, base_revision="", strategy="direct")
    resolved = ResolvedWorkspace(
        id=binding_id, root=checkout, base_revision="", strategy="direct", binding=binding,
    )
    actor = _operator_actor(binding_id)
    try:
        result = patch_mod.apply(resolved, ops, scope=(), binding=binding, actor=actor)
    except PatchError as exc:
        _discard_backup(checkout, rollback_id)
        raise _map_patch_error(exc.code, exc.reason) from exc
    if not result.get("ok"):
        _discard_backup(checkout, rollback_id)
        refused = result.get("refused") or {}
        raise _map_patch_error(str(refused.get("code") or ""), str(refused.get("reason") or ""))

    # Whole-file contents are not echoed back: the caller only needs a summary.
    applied = [
        {k: v for k, v in record.items() if k not in ("old", "new")}
        for record in result.get("applied", [])
    ]
    return {
        "ok": True,
        "checkoutRoot": str(checkout),
        "filesChanged": int(result.get("filesChanged") or 0),
        "totalBytes": int(result.get("totalBytes") or 0),
        "applied": applied,
        "previewDigest": preview.get("previewDigest"),
        # The id to put this exact change back (rollback_promotion).
        "rollbackId": rollback_id,
    }


def _rollback_dir(checkout: Path, rollback_id: str) -> Path:
    return checkout / ROLLBACK_ROOT_RELPATH / rollback_id


def _capture_backup(checkout: Path, preview: dict[str, Any], files: list[dict[str, Any]]) -> str:
    """Save the ORIGINAL contents of every file the promotion will touch.

    Returns the rollback id (the preview digest). Only reads the checkout, so the
    caller can abort before any write if this raises.
    """
    rollback_id = str(preview.get("previewDigest") or "")
    if not rollback_id:
        raise PromotionError("PROMOTION_FAILED", "The prepared change is missing its identity.")
    directory = _rollback_dir(checkout, rollback_id)
    directory.mkdir(parents=True, exist_ok=True)
    originals: list[dict[str, Any]] = []
    for f in files:
        rel = str(f.get("path") or "")
        op = str(f.get("op") or "")
        entry: dict[str, Any] = {
            "path": rel, "op": op, "existed": op != "create",
            "beforeHash": f.get("beforeHash"), "afterHash": f.get("afterHash"),
        }
        if op != "create":
            text = _read_text_strict(checkout / rel)
            backup_name = rel.replace("/", "__")
            (directory / backup_name).write_text(text, encoding="utf-8")
            entry["backup"] = backup_name
        originals.append(entry)
    manifest = {
        "rollbackId": rollback_id,
        "checkoutRoot": str(checkout),
        "previewDigest": preview.get("previewDigest"),
        "workspaceId": preview.get("workspaceId"),
        "runId": preview.get("runId"),
        "files": originals,
    }
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return rollback_id


def _discard_backup(checkout: Path, rollback_id: str) -> None:
    try:
        shutil.rmtree(_rollback_dir(checkout, rollback_id))
    except OSError:
        pass


def rollback_promotion(rollback_id: str, *, checkout_root: Optional[Path] = None) -> dict[str, Any]:
    """Put a previously-promoted change back — the exact original contents.

    The inverse of `apply_promotion`: a file the promotion CREATED is removed, a
    file it EDITED is restored from the saved backup, and a file it DELETED is
    recreated. Both versions survive (the backup is kept, never discarded).
    Reuses `code/patch.py` (path confinement, protected paths, atomicity) and
    refuses if a restored file changed since the promotion (`PROMOTION_BASE_CHANGED`).
    """
    checkout = Path(checkout_root) if checkout_root is not None else default_root()
    if checkout is None:
        raise PromotionError("PROMOTION_UNAVAILABLE", "There's no project folder to put the change back into.")
    checkout = Path(checkout)
    directory = _rollback_dir(checkout, rollback_id)
    manifest_path = directory / "manifest.json"
    if not manifest_path.is_file():
        raise PromotionError("PROMOTION_NO_ROLLBACK", "There's no saved version to put back for this change.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise PromotionError("PROMOTION_NO_ROLLBACK", "The saved version is unreadable.") from exc
    recorded = str(manifest.get("checkoutRoot") or "")
    if recorded and Path(os.path.realpath(recorded)) != Path(os.path.realpath(checkout)):
        raise PromotionError("PROMOTION_OUT_OF_SCOPE", "The saved version belongs to a different project folder.")

    ops: list[PatchOp] = []
    restored: list[str] = []
    for f in manifest.get("files") or []:
        rel = str(f.get("path") or "")
        op = str(f.get("op") or "")
        if not rel:
            continue
        if policy.is_protected(rel) or policy.is_ignored(rel):
            raise PromotionError("PROMOTION_OUT_OF_SCOPE", "This change touches a file Eclipse isn't allowed to change.")
        if op == "create":
            # The promotion created the file; putting it back removes it.
            ops.append(PatchOp(op="delete", path=rel, reason="Put the previous version back."))
        elif op == "delete":
            text = (directory / str(f.get("backup"))).read_text(encoding="utf-8")
            ops.append(PatchOp(op="create", path=rel, reason="Put the previous version back.", content=text))
        else:  # overwrite — restore the saved original, refusing if the file moved on
            text = (directory / str(f.get("backup"))).read_text(encoding="utf-8")
            ops.append(PatchOp(op="overwrite", path=rel, reason="Put the previous version back.",
                               content=text, expect_hash=f.get("afterHash")))
        restored.append(rel)

    if not ops:
        raise PromotionError("PROMOTION_NO_ROLLBACK", "There's nothing to put back for this change.")

    binding_id = "rollback_" + hashlib.sha256(str(checkout).encode("utf-8")).hexdigest()[:16]
    binding = WorkspaceBinding(id=binding_id, root=checkout, base_revision="", strategy="direct")
    resolved = ResolvedWorkspace(
        id=binding_id, root=checkout, base_revision="", strategy="direct", binding=binding,
    )
    actor = _operator_actor(binding_id)
    try:
        result = patch_mod.apply(resolved, ops, scope=(), binding=binding, actor=actor)
    except PatchError as exc:
        raise _map_patch_error(exc.code, exc.reason) from exc
    if not result.get("ok"):
        refused = result.get("refused") or {}
        raise _map_patch_error(str(refused.get("code") or ""), str(refused.get("reason") or ""))
    return {
        "ok": True,
        "rollbackId": rollback_id,
        "restored": sorted(restored),
        "filesChanged": int(result.get("filesChanged") or 0),
    }


__all__ = [
    "MAX_PROMOTION_FILES",
    "PROMOTION_KIND",
    "ROLLBACK_ROOT_RELPATH",
    "PromotionError",
    "apply_promotion",
    "build_preview",
    "promotion_digest",
    "rollback_promotion",
]
