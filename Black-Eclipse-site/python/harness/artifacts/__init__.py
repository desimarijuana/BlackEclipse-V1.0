"""The Eclipse Artifact Center — a persistent, centralized catalog of everything
the runtime and the user produce.

The catalog lives on the ONE `agent-memory.db` (never JDdS, never another
subsystem's tables); bytes live in a confined, content-addressed local store
under `.black-eclipse/artifacts/`. The `ArtifactService` is the single authority
for lifecycle operations; the API routes, agent tools, jobs and producers all
call it. See `docs/harness/artifact-center.md`.
"""

from __future__ import annotations

from .bootstrap import (
    get_artifact_service,
    install_artifact_layer,
    set_artifact_service,
    start_artifact_reconciler,
    stop_artifact_reconciler,
)
from .model import (
    Artifact,
    ArtifactCategory,
    ArtifactCollection,
    ArtifactEvent,
    ArtifactPage,
    ArtifactSourceType,
    ArtifactStatus,
    ArtifactVersion,
    PreviewStatus,
)
from .service import ArtifactError, ArtifactService
from .storage import LocalArtifactStorage, StorageError
from .store import ArtifactStore
from .tools import register_artifact_tools

__all__ = [
    "Artifact",
    "ArtifactCategory",
    "ArtifactCollection",
    "ArtifactError",
    "ArtifactEvent",
    "ArtifactPage",
    "ArtifactService",
    "ArtifactSourceType",
    "ArtifactStatus",
    "ArtifactStore",
    "ArtifactVersion",
    "LocalArtifactStorage",
    "PreviewStatus",
    "StorageError",
    "get_artifact_service",
    "install_artifact_layer",
    "register_artifact_tools",
    "set_artifact_service",
    "start_artifact_reconciler",
    "stop_artifact_reconciler",
]
