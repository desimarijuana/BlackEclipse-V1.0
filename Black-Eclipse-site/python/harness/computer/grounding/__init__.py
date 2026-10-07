"""Target grounding — turning an intent into a concrete on-screen target.

The hierarchy is fixed and observable:

    1. accessibility element
    2. application-specific semantic selector
    3. structured UI element (from the snapshot)
    4. OCR target
    5. vision target
    6. relative coordinate
    7. raw coordinate

Coordinates are the FALLBACK, never the primary method. `grounder.py` runs the
ladder and returns a `Target` with confidence, method and bounds; `matching.py`
holds the pure text/role scoring so it is testable without an OS.
"""

from __future__ import annotations

from .grounder import Grounder
from .matching import GroundingQuery, score_element

__all__ = ["Grounder", "GroundingQuery", "score_element"]
