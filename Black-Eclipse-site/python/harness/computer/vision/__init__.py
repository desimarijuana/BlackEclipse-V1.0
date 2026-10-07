"""Vision engine — a provider-agnostic visual reasoning abstraction.

`base.py` defines the `VisionEngine` contract (find text/targets in an image,
describe a screen, answer a visual question). `backends.py` supplies a
multimodal-LLM backend that reuses the harness's OWN model runtime
(`harness.model_runtime`) so no new provider stack is invented, plus an honest
unavailable engine. `router.py` selects local vs cloud per the configured
`vision_mode`, refusing to send sensitive regions to a cloud model unless policy
explicitly allows it.
"""

from __future__ import annotations

from .base import VisionEngine, VisionResult
from .backends import LocalModelVision, UnavailableVision
from .router import VisionRouter, build_vision_router

__all__ = [
    "LocalModelVision",
    "UnavailableVision",
    "VisionEngine",
    "VisionResult",
    "VisionRouter",
    "build_vision_router",
]
