"""The grounding ladder.

`Grounder.ground()` runs the fixed hierarchy over the CURRENT snapshot + app
profile + OCR + vision, returning a `Target` with method, confidence and bounds,
or raising `TargetNotFound`/`AmbiguousTarget`.

The ladder is data-driven: each rung is a small scorer over the snapshot. Vision
is only consulted when a `vision_lookup` callable is supplied (the caller
decides — vision is expensive and possibly cloud), and coordinates are only used
when the caller explicitly allows them.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from ..errors import AmbiguousTarget, TargetNotFound
from ..models import Bounds, Snapshot, Target
from .matching import GroundingQuery, is_ambiguous, rank_elements

# The method names, in ladder order. Coordinate methods are the fallback.
METHOD_ORDER = (
    "accessibility", "semantic", "structured", "ocr", "vision",
    "relative_coordinate", "coordinate",
)


class Grounder:
    """Grounds an intent against one snapshot."""

    def __init__(self, *, min_confidence: float = 0.6, allow_coordinates: bool = False) -> None:
        self._min_confidence = min_confidence
        self._allow_coordinates = allow_coordinates

    def ground(
        self,
        query: GroundingQuery,
        snapshot: Snapshot,
        *,
        app_profile: Any = None,
        ocr_words: Optional[list[dict]] = None,
        vision_lookup: Optional[Callable[[str], list[dict]]] = None,
        allow_coordinates: Optional[bool] = None,
    ) -> Target:
        allow_coords = self._allow_coordinates if allow_coordinates is None else allow_coordinates
        application = snapshot.application
        window_id = snapshot.window_id

        # 1–3. Snapshot elements carry their own source (accessibility/structured/
        # som/ocr/vision). Rank them and pick the best, preferring the higher rung
        # when scores are close.
        candidates: list[dict] = [e.to_dict() for e in snapshot.elements]
        scored = rank_elements(query, candidates)
        if scored:
            best_score, best = scored[0]
            # Ambiguity is only meaningful when the top candidate actually matches.
            if best_score >= 0.5 and is_ambiguous(scored):
                raise AmbiguousTarget(
                    f"More than one on-screen element matches {query.needle!r}.",
                    app=application, window=window_id,
                    metadata={"candidates": [e.get("name") for _, e in scored[:5]]},
                )
            if best_score >= self._min_confidence or len(scored) == 1:
                return self._target_from_element(query, best, best_score, snapshot, application, window_id)

        # 2b. Application profile semantic selector (a per-app known control).
        profile_target = self._from_app_profile(query, app_profile, snapshot)
        if profile_target is not None:
            return profile_target

        # 4. OCR words.
        if ocr_words:
            scored_ocr = rank_elements(query, ocr_words)
            if scored_ocr:
                score, word = scored_ocr[0]
                bounds = Bounds.from_any(word.get("bounds"))
                if bounds is not None and score >= self._min_confidence * 0.8:
                    return Target(
                        description=query.needle, method="ocr", confidence=score, bounds=bounds,
                        application=application, window_id=window_id, snapshot_id=snapshot.snapshot_id,
                        role="text", name=str(word.get("text") or ""),
                    )

        # 5. Vision (only when the caller supplied a lookup).
        if vision_lookup is not None:
            try:
                found = vision_lookup(query.needle)
            except Exception:  # noqa: BLE001 - vision is best-effort
                found = []
            scored_vision = rank_elements(query, found)
            if scored_vision:
                score, item = scored_vision[0]
                bounds = Bounds.from_any(item.get("bounds"))
                if bounds is not None:
                    return Target(
                        description=query.needle, method="vision",
                        confidence=max(score, float(item.get("confidence", score))),
                        bounds=bounds, application=application, window_id=window_id,
                        snapshot_id=snapshot.snapshot_id, role=str(item.get("role") or "element"),
                        name=str(item.get("label") or item.get("name") or ""),
                    )

        # 6. Relative coordinate (an explicit offset within the window).
        if query.relative and snapshot.bounds is not None:
            point = self._parse_relative(query.relative, snapshot.bounds)
            if point is not None:
                return Target(
                    description=query.relative, method="relative_coordinate", confidence=0.4,
                    bounds=Bounds(point[0], point[1], 1, 1), application=application,
                    window_id=window_id, snapshot_id=snapshot.snapshot_id,
                )

        # 7. Raw coordinate (only when explicitly allowed).
        if allow_coords and query.intent:
            point = self._parse_coordinate(query.intent)
            if point is not None:
                return Target(
                    description=query.intent, method="coordinate", confidence=0.25,
                    bounds=Bounds(point[0], point[1], 1, 1), application=application,
                    window_id=window_id, snapshot_id=snapshot.snapshot_id,
                )

        raise TargetNotFound(
            f"Eclipse couldn't find {query.needle!r} on screen.",
            app=application, window=window_id,
            metadata={"searched": list(METHOD_ORDER)},
        )

    def _target_from_element(
        self, query: GroundingQuery, element: dict, score: float, snapshot: Snapshot,
        application: str, window_id: str,
    ) -> Target:
        source = str(element.get("source") or "accessibility")
        method = {
            "accessibility": "accessibility", "som": "structured",
            "structured": "structured", "ocr": "ocr", "vision": "vision",
        }.get(source, "structured")
        bounds = Bounds.from_any(element.get("bounds"))
        return Target(
            description=query.needle or str(element.get("name") or ""),
            method=method, confidence=score, bounds=bounds,
            application=application, window_id=window_id, snapshot_id=snapshot.snapshot_id,
            element_ref=str(element.get("ref") or ""), role=str(element.get("role") or ""),
            name=str(element.get("name") or ""),
        )

    def _from_app_profile(self, query: GroundingQuery, app_profile: Any, snapshot: Snapshot) -> Optional[Target]:
        if app_profile is None:
            return None
        try:
            selector = app_profile.semantic_selector(query)
        except Exception:  # noqa: BLE001
            return None
        if not selector:
            return None
        # The selector is a snapshot element ref or a name.
        ref = str(selector.get("ref") or "")
        element = snapshot.element(ref) if ref else None
        if element is None:
            scored = rank_elements(GroundingQuery(name=str(selector.get("name") or query.needle)), [e.to_dict() for e in snapshot.elements])
            element = scored[0][1] if scored else None
        else:
            element = element.to_dict()
        if element is None:
            return None
        return Target(
            description=query.needle, method="semantic", confidence=0.9,
            bounds=Bounds.from_any(element.get("bounds")),
            application=snapshot.application, window_id=snapshot.window_id,
            snapshot_id=snapshot.snapshot_id, element_ref=str(element.get("ref") or ""),
            role=str(element.get("role") or ""), name=str(element.get("name") or ""),
        )

    def _parse_relative(self, text: str, window: Bounds) -> Optional[tuple[int, int]]:
        # Accepts "0.5,0.5" (fraction of the window) or "left+10,top+20".
        try:
            if "," not in text:
                return None
            a, b = text.split(",", 1)
            if "." in a or "." in b:
                return (window.x + int(float(a) * window.width), window.y + int(float(b) * window.height))
            return (window.x + int(a), window.y + int(b))
        except (ValueError, TypeError):
            return None

    def _parse_coordinate(self, text: str) -> Optional[tuple[int, int]]:
        try:
            cleaned = text.strip().strip("()").replace("x", ",").replace(" ", "")
            a, b = cleaned.split(",")
            return (int(float(a)), int(float(b)))
        except (ValueError, TypeError):
            return None


__all__ = ["METHOD_ORDER", "Grounder"]
