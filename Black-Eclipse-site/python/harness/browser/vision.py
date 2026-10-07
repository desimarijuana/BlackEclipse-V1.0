"""Vision — a fallback/augmentation layer, never the default.

Observation hierarchy: accessibility tree → DOM → structured page state → vision.
Vision is used when the DOM/accessibility layer is thin or absent (canvas, charts,
graphical controls, rendered PDFs, visual position) and for visual verification.

Two real mechanisms, no fake model:

  * a **screenshot** is captured and persisted (a real PNG artifact), and
  * a **visual map** of interactive elements (ref + role + name + bounding box)
    is derived from the live DOM, so a caller can reason about on-screen position.

DOM+vision FUSION chooses between the DOM and vision paths from their confidences
and records WHY in the trace. When no vision model is configured, the screenshot
and map are returned honestly labelled — the tool never claims an interpretation
it did not produce.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from .resolver import STRATEGY_CONFIDENCE


@dataclass
class VisualElement:
    ref: str
    role: str
    name: str
    box: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {"ref": self.ref, "role": self.role, "name": self.name, "box": self.box}


@dataclass
class VisualMap:
    url: str
    width: int
    height: int
    screenshot: Optional[str]
    elements: list[VisualElement] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "url": self.url, "width": self.width, "height": self.height,
            "screenshot": self.screenshot,
            "elements": [e.to_dict() for e in self.elements],
            "note": self.note,
        }


@dataclass
class FusionDecision:
    chosen: str            # "dom" | "vision"
    dom_confidence: float
    vision_confidence: float
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "chosen": self.chosen,
            "domConfidence": round(self.dom_confidence, 3),
            "visionConfidence": round(self.vision_confidence, 3),
            "rationale": self.rationale,
        }


def fuse(dom_confidence: float, vision_confidence: float, *, dom_threshold: float = 0.6) -> FusionDecision:
    """Choose the action path from DOM vs vision confidence.

    The rule is deliberately simple and explained in the trace: prefer DOM unless
    it is below the threshold AND vision is confidently higher.
    """
    if dom_confidence >= dom_threshold:
        chosen = "dom"
        rationale = (
            f"The page's own structure identified the element (confidence "
            f"{dom_confidence:.2f}); visuals weren't needed."
        )
    elif vision_confidence > dom_confidence:
        chosen = "vision"
        rationale = (
            f"The page's structure was uncertain (confidence {dom_confidence:.2f}); "
            f"a visual match was stronger ({vision_confidence:.2f})."
        )
    else:
        chosen = "dom"
        rationale = (
            "Neither the page structure nor the visual match was confident; Eclipse "
            "used the page structure and reported the uncertainty."
        )
    return FusionDecision(chosen=chosen, dom_confidence=dom_confidence, vision_confidence=vision_confidence, rationale=rationale)


async def locate(session: Any, text: str, *, query: Optional[str] = None, model_settings: Any = None) -> dict[str, Any]:
    """Fuse the DOM locator with a visual match to locate a target on a page.

    The DOM path (visible text) yields a confidence; when a multimodal model is
    configured, a bounded visual question over the screenshot yields another. The
    `fuse` decision picks the path and records WHY, and the result carries a stable
    snapshot reference when one is known so the caller can act on it.
    """
    page = session.page()
    dom_confidence = 0.0
    ref = ""
    count = 0
    try:
        locator = page.get_by_text(text, exact=False)
        count = await locator.count()
        if count >= 1:
            dom_confidence = 0.92 if count == 1 else 0.7
            snapshot = session.snapshots.latest
            if snapshot is not None:
                needle = text.strip().lower()
                for element in snapshot.elements.values():
                    if element.name and needle in element.name.strip().lower():
                        ref = element.ref
                        break
    except Exception:  # noqa: BLE001
        count = 0
    vision_confidence = 0.0
    interpretation = None
    shot = None
    try:
        shot = await session.screenshot()
    except Exception:  # noqa: BLE001
        shot = None
    if shot is not None:
        from .vision_model import BrowserVisionInterpreter  # noqa: PLC0415

        interp = BrowserVisionInterpreter(model_settings)
        interpretation = await interp.interpret(shot, query=query or text)
        if interpretation.available:
            vision_confidence = 0.85 if interpretation.elements else 0.4
    decision = fuse(dom_confidence, vision_confidence)
    return {
        "text": text,
        "domConfidence": dom_confidence,
        "visionConfidence": vision_confidence,
        "ref": ref,
        "domCount": count,
        "screenshot": shot,
        "fusion": decision.to_dict(),
        "interpretation": interpretation.to_dict() if interpretation else {"available": False},
    }


class VisionEngine:
    """Captures screenshots and derives a live visual map for a session."""

    def __init__(self, *, session_id: str, screenshots_dir: Path) -> None:
        self._session_id = session_id
        self._dir = Path(screenshots_dir) / session_id

    async def screenshot(self, page: Any, *, full_page: bool = False) -> str:
        """Capture a PNG and return its path (persisted artifact)."""
        self._dir.mkdir(parents=True, exist_ok=True)
        path = self._dir / f"shot-{int(time.time() * 1000)}.png"
        try:
            await page.screenshot(path=str(path), full_page=full_page)
        except Exception:  # noqa: BLE001
            try:
                await page.screenshot(path=str(path))
            except Exception as exc:  # noqa: BLE001
                raise RuntimeError(f"screenshot failed: {exc}") from exc
        return str(path)

    async def visual_map(self, page: Any, snapshot_engine: Any = None, *, screenshot: Optional[str] = None) -> VisualMap:
        """A map of interactive elements with bounding boxes, from the live DOM."""
        url = ""
        try:
            url = page.url
        except Exception:  # noqa: BLE001
            pass
        viewport = {"width": 0, "height": 0}
        try:
            viewport = page.viewport_size or {"width": 0, "height": 0}
        except Exception:  # noqa: BLE001
            pass
        elements: list[VisualElement] = []
        snapshot = snapshot_engine.latest if snapshot_engine is not None else None
        if snapshot is not None:
            from .resolver import Resolver, Target  # noqa: PLC0415

            resolver = Resolver(snapshot_engine)
            for element in list(snapshot.elements.values())[:200]:
                if not element.interactive:
                    continue
                found = resolver._locator_for(page, Target(ref=element.ref))  # noqa: SLF001
                if found is None:
                    continue
                try:
                    box = await found[0].bounding_box()
                except Exception:  # noqa: BLE001
                    box = None
                if box:
                    elements.append(VisualElement(
                        ref=element.ref, role=element.role, name=element.name,
                        box={
                            "x": round(box["x"], 1), "y": round(box["y"], 1),
                            "width": round(box["width"], 1), "height": round(box["height"], 1),
                        },
                    ))
        note = (
            "Screenshot and element positions are provided as raw visual evidence. "
            "No vision interpretation model is configured, so Eclipse did not "
            "interpret the image — it captured it and mapped what the page reports."
        )
        return VisualMap(
            url=url, width=int(viewport.get("width", 0)), height=int(viewport.get("height", 0)),
            screenshot=screenshot, elements=elements, note=note,
        )


__all__ = ["FusionDecision", "STRATEGY_CONFIDENCE", "VisualElement", "VisualMap", "VisionEngine", "fuse"]
