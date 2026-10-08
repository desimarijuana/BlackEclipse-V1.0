"""Eclipse Vision subsystem.

A production-grade multimodal capability integrated with the existing agent
runtime, model/provider layer, browser automation, computer use, document
handling, the Evidence & Research Engine, security, telemetry, caching and
evaluation.

The public surface:

    VisionInput / VisionResult / VisionError      — contracts
    VisionOrchestrator (`orchestrate`)             — the ONE entry point
    build_asset_store                              — content-addressed storage
    register_vision_tools                          — the agent tools

Nothing here builds a second provider stack: all model calls route through
`harness.model_runtime`.
"""

from __future__ import annotations

from .config import VisionConfig, vision_config, vision_enabled
from .contracts import (
    EvidenceStatus,
    ImageAsset,
    OCRSpan,
    Region,
    VisionInput,
    VisionResult,
    VisionUsage,
    VisualObservation,
)
from .errors import VisionError, VisionErrorClass
from .orchestrator import VisionContext, build_asset_store, orchestrate

__all__ = [
    "VisionConfig",
    "vision_config",
    "vision_enabled",
    "VisionInput",
    "VisionResult",
    "VisionUsage",
    "VisualObservation",
    "OCRSpan",
    "ImageAsset",
    "Region",
    "EvidenceStatus",
    "VisionError",
    "VisionErrorClass",
    "VisionContext",
    "orchestrate",
    "build_asset_store",
]
