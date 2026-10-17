"""Eclipse Canvas — editable artifacts over the ONE artifact catalog.

Canvas never introduces a second persistence plane. A canvas document is an
ordinary `Artifact` whose bytes are the canonical content and whose metadata
carries the canvas kind/language. Manual and AI edits are appended as immutable
artifact versions; every save is guarded by the version the editor loaded.
"""

from .model import (
    CanvasConflict,
    CanvasError,
    CanvasKind,
    CanvasNotFound,
    CanvasProposal,
    CanvasSnapshot,
    EditOperation,
)
from .service import CanvasService

__all__ = [
    "CanvasConflict",
    "CanvasError",
    "CanvasKind",
    "CanvasNotFound",
    "CanvasProposal",
    "CanvasService",
    "CanvasSnapshot",
    "EditOperation",
]
