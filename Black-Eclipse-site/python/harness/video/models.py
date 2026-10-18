"""Contracts for the native video pipeline.

Small and explicit on purpose (the repo's model convention): a structured
`VideoError` with a stable machine-readable code, the closed set of supported
project kinds, and the job vocabulary the Fabric integration pins.

`title_card` renders the built-in proof video; `storyboard` carries a versioned
spec (see `video/spec.py` — the ONE authority, re-checked defensively in Rust).
This module is the shared vocabulary, not a competing contract.
"""

from __future__ import annotations

import uuid

# The Fabric job vocabulary. One job type; `action` in the payload selects the
# operation (render | inspect) and `mode` selects draft | final.
VIDEO_JOB_TYPE = "video"
VIDEO_QUEUE = "video"
VIDEO_WORKER_KIND = "video"

# Supported `VideoProject.kind` values. `storyboard` projects carry a spec that
# must validate against the versioned schema in `video/spec.py`.
SUPPORTED_PROJECT_KINDS: tuple[str, ...] = ("title_card", "storyboard")
PROJECT_SCHEMA_VERSION = 1


class VideoError(Exception):
    """A structured refusal. `code` is a stable machine-readable label."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def new_project_id() -> str:
    return f"vprj_{uuid.uuid4().hex[:16]}"


__all__ = [
    "PROJECT_SCHEMA_VERSION",
    "SUPPORTED_PROJECT_KINDS",
    "VIDEO_JOB_TYPE",
    "VIDEO_QUEUE",
    "VIDEO_WORKER_KIND",
    "VideoError",
    "new_project_id",
]
