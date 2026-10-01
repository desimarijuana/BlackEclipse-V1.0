"""Inbound trigger paths (Phase 6 §6.5).

Three ways a job starts, all of which enqueue exactly what the scheduler would:

  * `file_watch` — a bounded poller over `watch_path` (mtime + size signature)
    inside an existing workspace root; the path is policy-checked on every poll.
  * `webhook`    — `POST /jobs/{id}/trigger`; the job's token is compared as a
    SHA-256 hash (only the hash is ever stored; the token is shown once at
    creation and never again).
  * `manual`     — the UI / route, already behind `require_operator`.

A webhook trigger carries NO parameters that can change the job — it fires the
stored definition or nothing. A body cannot select a skill, raise a budget, or
widen a permission (the same "an inbound message can never widen authority" rule
MCP applies to server results).
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..code import policy
from ..code.workspace import WorkspaceDenial, default_root
from .model import JobDefinition


# ── Webhook tokens ───────────────────────────────────────────────────────────


def make_webhook_token() -> tuple[str, str]:
    """A fresh token + its SHA-256 hash. Store the hash; show the token ONCE."""
    token = secrets.token_urlsafe(32)
    return token, hash_webhook_token(token)


def hash_webhook_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_webhook_token(job: JobDefinition, token: Optional[str]) -> bool:
    """Constant-time compare of a presented token against the stored hash."""
    if not job.webhook_token_hash or not token:
        return False
    return hmac.compare_digest(hash_webhook_token(token), job.webhook_token_hash)


# ── File watch ───────────────────────────────────────────────────────────────


def file_signature(path: Path) -> str:
    """A bounded signature of a file: size + mtime, never its contents."""
    try:
        stat = path.stat()
    except OSError:
        return "missing"
    return f"{int(stat.st_size)}:{int(stat.st_mtime_ns)}"


@dataclass
class FileWatcher:
    """Tracks the last-seen signature of a watch path inside a workspace root.

    The state is per-process and in-memory: a restart reconciles through the
    scheduler's missed-run policy, not by replaying file events. `poll` returns
    True on the FIRST observation after start only when `fire_on_start` is set —
    otherwise a change is required.
    """

    path: Path
    last_signature: Optional[str] = None
    fire_on_start: bool = False

    def poll(self) -> bool:
        """Whether the watched file changed since the last poll."""
        current = file_signature(self.path)
        changed = False
        if self.last_signature is None:
            changed = self.fire_on_start and current != "missing"
        else:
            changed = current != self.last_signature and current != "missing"
        self.last_signature = current
        return changed


def resolve_watch_path(job: JobDefinition) -> Optional[Path]:
    """Resolve a file-watch job's path inside its workspace, or None.

    Refuses (returns None) rather than raising: the scheduler records a `refused`
    run with the reason. Confinement reuses `policy.resolve_within`, so a path
    outside the workspace in a traversal or symlink is refused.
    """
    raw = job.watch_path
    if not raw:
        return None
    root = None
    if job.target.workspace_root:
        candidate = Path(job.target.workspace_root)
        if candidate.is_dir():
            root = Path(os.path.realpath(candidate))
    if root is None:
        root = default_root()
    if root is None:
        return None
    try:
        return policy.resolve_within(root, raw)
    except (WorkspaceDenial, policy.PolicyDenial):
        return None


__all__ = [
    "FileWatcher",
    "file_signature",
    "hash_webhook_token",
    "make_webhook_token",
    "resolve_watch_path",
    "verify_webhook_token",
]
