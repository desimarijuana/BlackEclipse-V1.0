"""Evaluation provenance: what produced a run, and whether it can be compared.

A score is only comparable when the run names the exact code, dataset, task
versions, grader version and configuration that produced it. This module owns
the identity helpers and the refusal: a persisted run missing any required
piece is not a baseline or a candidate, and must not be treated as one.

`gitCommit` is best-effort: a packaged install without `.git` records
`gitCommitUnavailable` instead of inventing a commit.
"""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
from typing import Any, Optional

from .. import __version__ as AGENT_VERSION

_REQUIRED_CONFIG = ("trials", "tier", "split", "graderVersion")


class ProvenanceError(ValueError):
    """A run cannot be used as comparable evidence."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "detail": self.detail}


def repository_commit(root: Optional[str] = None) -> Optional[str]:
    """The checkout's HEAD, or None when git/the repository is unavailable."""
    try:
        base = root or os.path.abspath(
            os.path.join(os.path.dirname(__file__), "..", "..", "..")
        )
        proc = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=base, capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0:
            return proc.stdout.strip() or None
    except Exception:  # noqa: BLE001 - provenance is best-effort, never fatal
        return None
    return None


def task_fingerprint_digest(tasks: list[Any]) -> str:
    """A stable digest over every selected task's `(id, fingerprint)` pair."""
    payload = {
        str(getattr(task, "id", "")): str(getattr(task, "fingerprint", lambda: "")())
        for task in tasks
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def require_provenance(run: dict[str, Any]) -> dict[str, Any]:
    """Return `run` when its identity is complete, else raise `ProvenanceError`.

    Required: a dataset checksum, the agent version, a non-empty config identity
    (`trials`, `tier`, `split`, `graderVersion`), and metadata carrying the
    grader version and task-fingerprint digest. A `gitCommit` is required unless
    the run explicitly records `gitCommitUnavailable`.
    """
    if not isinstance(run, dict):
        raise ProvenanceError("PROVENANCE_INCOMPLETE", "the run record is not an object")

    missing: list[str] = []
    if not str(run.get("datasetChecksum") or "").strip():
        missing.append("datasetChecksum")
    if not str(run.get("agentVersion") or "").strip():
        missing.append("agentVersion")

    config = run.get("config")
    if not isinstance(config, dict) or not config:
        missing.append("config")
    else:
        for key in _REQUIRED_CONFIG:
            if config.get(key) is None or (key == "split" and not str(config.get(key)).strip()):
                missing.append(f"config.{key}")

    metadata = run.get("metadata")
    if not isinstance(metadata, dict) or not metadata:
        missing.append("metadata")
    else:
        if metadata.get("graderVersion") is None:
            missing.append("metadata.graderVersion")
        if not str(metadata.get("taskFingerprintDigest") or "").strip():
            missing.append("metadata.taskFingerprintDigest")
        if not str(run.get("gitCommit") or "").strip() and not metadata.get("gitCommitUnavailable"):
            missing.append("gitCommit")

    if missing:
        raise ProvenanceError(
            "PROVENANCE_INCOMPLETE",
            "missing " + ", ".join(sorted(set(missing))),
        )
    return run


__all__ = [
    "AGENT_VERSION",
    "ProvenanceError",
    "repository_commit",
    "require_provenance",
    "task_fingerprint_digest",
]
