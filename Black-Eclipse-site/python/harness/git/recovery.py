"""The Git recovery manager.

Recovery is what makes the subsystem safe to let an agent drive:

  * **Pre-operation snapshot** — before a `dangerous`/`destructive`/`critical`
    operation, the current HEAD, branch and stash count are recorded on the
    journal row. Nothing is changed; the snapshot is a label an operator (or a
    later recovery call) can return to.
  * **State reconciliation** — after any operation, the repository's own sentinel
    files (`MERGE_HEAD`, `rebase-merge/`, …) are the source of truth. When the
    runtime's recorded active operation disagrees with the repository, the
    repository wins and the mismatch is reported — never hidden.
  * **Reflog recovery** — the reflog is the ground truth for "where was I before".
    `recovery_options` reads it and proposes the honest next moves.

Nothing here discards work automatically. A destructive recovery is a
`recovery` command the caller must choose and (for a reset) authorize.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from . import state
from .executor import run
from .repository import Repository


@dataclass(frozen=True)
class PreState:
    head: Optional[str]
    branch: Optional[str]
    stash_count: int
    detached: bool
    unborn: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "head": self.head, "branch": self.branch,
            "stashCount": self.stash_count, "detached": self.detached,
            "unborn": self.unborn,
        }


def snapshot(repo: Repository) -> PreState:
    """The current HEAD/branch/stash count. Read-only; never changes anything."""
    head_result = run(repo.root, "head_sha")
    head = head_result.stdout.strip() if head_result.ok else None
    branch_result = run(repo.root, "head_ref")
    branch_name = branch_result.stdout.strip() if branch_result.ok else None
    detached = branch_name == "HEAD" or bool(repo.detached_head)
    stash_result = run(repo.root, "stash_list")
    stash_count = 0
    if stash_result.ok:
        stash_count = len([ln for ln in stash_result.stdout.splitlines() if ln.strip()])
    return PreState(
        head=head or repo.head,
        branch=None if detached else (branch_name or repo.branch),
        stash_count=stash_count,
        detached=detached,
        unborn=repo.unborn,
    )


@dataclass
class Reconciliation:
    repository_operation: Optional[str]
    recorded_operation: Optional[str]
    consistent: bool
    note: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "repositoryOperation": self.repository_operation,
            "recordedOperation": self.recorded_operation,
            "consistent": self.consistent,
            "note": self.note,
        }


def reconcile(repo: Repository, journal: Any) -> Reconciliation:
    """Compare the repository's operation state with the journal's record."""
    state_now = state.active_operation(repo)
    recorded = None
    if journal is not None:
        try:
            recorded = journal.get_active(str(repo.root))
        except Exception:  # noqa: BLE001 - a journal read must never break recovery
            recorded = None
    repo_op = state_now.operation if state_now is not None else None
    recorded_op = (recorded or {}).get("operation")
    if repo_op == recorded_op:
        note = "The runtime's record matches the repository."
        consistent = True
    elif repo_op is None and recorded_op is not None:
        note = "The repository has no operation open; the runtime's stale record was cleared."
        consistent = False
        if journal is not None:
            try:
                journal.clear_active(str(repo.root))
            except Exception:  # noqa: BLE001
                pass
    elif repo_op is not None and recorded_op is None:
        note = "The repository has an operation open that the runtime did not record."
        consistent = False
    else:
        note = "The repository and the runtime disagree about which operation is open."
        consistent = False
    return Reconciliation(repo_op, recorded_op, consistent, note)


@dataclass
class RecoveryOptions:
    operations: list[dict[str, Any]] = field(default_factory=list)
    reflog: list[dict[str, Any]] = field(default_factory=list)
    can_abort: bool = False
    can_continue: bool = False
    stash_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "operations": self.operations,
            "reflog": self.reflog[:20],
            "canAbort": self.can_abort,
            "canContinue": self.can_continue,
            "stashCount": self.stash_count,
        }


def recovery_options(repo: Repository) -> RecoveryOptions:
    """The honest, read-only menu of recovery moves for the current repository."""
    from .parsers import parse_reflog

    active = state.active_operation(repo)
    operations: list[dict[str, Any]] = []
    if active is not None:
        operations.append(active.to_dict())
        if state.abort_hint(repo):
            operations.append({"name": "abort", "tool": state.abort_hint(repo)})
        if state.continue_hint(repo):
            operations.append({"name": "continue", "tool": state.continue_hint(repo)})
    reflog_result = run(repo.root, "reflog", {"maxCount": 50})
    reflog = parse_reflog(reflog_result.stdout) if reflog_result.ok else []
    pre = snapshot(repo)
    return RecoveryOptions(
        operations=operations,
        reflog=reflog,
        can_abort=bool(active is not None),
        can_continue=bool(active is not None and not active.conflicts),
        stash_count=pre.stash_count,
    )


__all__ = [
    "PreState",
    "RecoveryOptions",
    "Reconciliation",
    "reconcile",
    "recovery_options",
    "snapshot",
]
