"""Observation — building a `Snapshot` from whichever sources are available.

Modes:
  * `ax`   — the accessibility tree only, rendered as text + elements.
  * `som`  — a screen-of-marks: the (window) screenshot plus NUMBERED interactable
             elements from the accessibility tree, with bounds/roles/names/values.
  * `ocr`  — OCR words as elements (for canvas/graphical apps).
  * `vision` — a plain screenshot (+ optional model description).

Every snapshot gets a `snapshot_id` and a `generation`; the numbered element
handles (`#1`, `#2`, …) the model sees are validated against this snapshot before
an action runs, so a stale handle is refused rather than silently repointed.

The engine is honest: an absent AX tree yields an empty element list (never
invented elements), and OCR/vision are used only when their backends are real.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Optional

from .accessibility.base import looks_interactive
from .models import AXNode, Bounds, Snapshot, SnapshotElement


def _flatten(node: Optional[AXNode]) -> list[AXNode]:
    if node is None:
        return []
    return [n for n in node.walk() if n is not None]


def _identity(role: str, name: str, value: str, bounds: Optional[Bounds]) -> str:
    raw = f"{role}|{name}|{value}|{bounds.to_list() if bounds else ''}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def ax_digest(node: Optional[AXNode]) -> str:
    """A digest of the accessibility tree's content, for state-change detection."""
    if node is None:
        return ""
    parts = [f"{n.role}:{n.name}:{n.value}" for n in _flatten(node)]
    return hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:20]


class ObservationEngine:
    """Builds snapshots for one session."""

    def __init__(self, *, driver: Any, ax: Any, ocr: Any, vision_router: Any, config: Any, capture: Any) -> None:
        self._driver = driver
        self._ax = ax
        self._ocr = ocr
        self._vision = vision_router
        self._config = config
        self._capture = capture
        self._counter = 0

    def next_snapshot_id(self) -> str:
        self._counter += 1
        return f"snap-{self._counter}-{int(time.time() * 1000)}"

    async def observe(
        self,
        *,
        window_id: Optional[str] = None,
        mode: Optional[str] = None,
        persist_image: bool = True,
        session_id: str = "session",
        include_vision_description: bool = False,
    ) -> Snapshot:
        mode = (mode or self._config.observation_default_mode).lower()
        snapshot_id = self.next_snapshot_id()
        generation = self._counter

        window_title = ""
        bounds: Optional[Bounds] = None
        if window_id:
            try:
                window = self._driver.get_window(window_id)
                if window is not None:
                    window_title = window.title
                    bounds = window.bounds
            except Exception:  # noqa: BLE001
                pass

        ax_tree = None
        if mode in ("ax", "som"):
            try:
                ax_tree = self._driver.accessibility_tree(window_id)
            except Exception:  # noqa: BLE001
                ax_tree = None

        elements: list[SnapshotElement] = []
        if ax_tree is not None:
            elements = self._elements_from_ax(ax_tree)

        ocr_result = None
        image = None
        image_path = None
        if mode in ("ocr", "som", "vision") and self._config.ocr_enabled:
            try:
                frame = await self._driver.capture(window_id=window_id)
                image = getattr(frame, "data", None)
                if persist_image and mode != "ax":
                    image_path = self._capture.persist(frame, session_id=session_id, label="snapshot")
            except Exception:  # noqa: BLE001
                frame = None
            if mode == "ocr" and image is not None and self._ocr is not None and getattr(self._ocr, "available", False):
                ocr_result = self._ocr.read(image, bounds=bounds)
                elements = self._elements_from_ocr(ocr_result)
        elif mode == "vision":
            try:
                frame = await self._driver.capture(window_id=window_id)
                image = getattr(frame, "data", None)
                if persist_image:
                    image_path = self._capture.persist(frame, session_id=session_id, label="snapshot")
            except Exception:  # noqa: BLE001
                pass

        # SOM: if AX gave no interactables but an image exists, add OCR marks.
        if mode == "som" and not elements and image is not None and self._ocr is not None and getattr(self._ocr, "available", False):
            ocr_result = self._ocr.read(image, bounds=bounds)
            elements = self._elements_from_ocr(ocr_result)

        text = self._render_text(mode, elements, ocr_result)
        snapshot = Snapshot(
            snapshot_id=snapshot_id, generation=generation,
            application=str(getattr(self._driver, "id", "")),
            window_id=window_id or "", window_title=window_title, bounds=bounds,
            mode=mode, elements=elements, text=text, image_path=image_path,
            ax_digest=ax_digest(ax_tree),
            ocr_digest=(hashlib.sha256(ocr_result.text.encode("utf-8")).hexdigest()[:20] if ocr_result and ocr_result.available else ""),
            chars=len(text),
            truncated=len(text) > self._config.snapshot_max_chars,
        )
        if include_vision_description and image is not None:
            engine = self._vision.engine(sensitive=False)
            if engine.available:
                try:
                    result = await engine.describe(image, bounds=bounds)
                    if result.text:
                        snapshot.text = (snapshot.text + "\n\n" + result.text)[: self._config.snapshot_max_chars]
                except Exception:  # noqa: BLE001
                    pass
        return snapshot

    # ── element builders ─────────────────────────────────────────────────────

    def _elements_from_ax(self, tree: AXNode) -> list[SnapshotElement]:
        elements: list[SnapshotElement] = []
        counter = 0
        for node in _flatten(tree):
            if not self._is_interactable(node):
                continue
            counter += 1
            elements.append(SnapshotElement(
                ref=str(counter), role=node.role, name=node.name, value=node.value,
                bounds=node.bounds, enabled=node.enabled, focused=node.focused,
                states=list(node.states), source="accessibility",
                identity=_identity(node.role, node.name, node.value, node.bounds),
            ))
        return elements

    def _is_interactable(self, node: AXNode) -> bool:
        if node.bounds is None or node.bounds.width <= 0 or node.bounds.height <= 0:
            return False
        if node.name or node.value:
            return True
        return looks_interactive(node.role)

    def _elements_from_ocr(self, ocr_result: Any) -> list[SnapshotElement]:
        elements: list[SnapshotElement] = []
        for i, word in enumerate(getattr(ocr_result, "words", []), start=1):
            elements.append(SnapshotElement(
                ref=str(i), role="text", name=word.text, bounds=word.bounds,
                source="ocr", confidence=word.confidence,
                identity=_identity("text", word.text, "", word.bounds),
            ))
        return elements

    # ── rendering ────────────────────────────────────────────────────────────

    def _render_text(self, mode: str, elements: list[SnapshotElement], ocr_result: Any) -> str:
        header = f"[observation mode: {mode}]"
        if not elements:
            body = "(no interactable elements were found)"
            if ocr_result is not None and getattr(ocr_result, "available", False) and ocr_result.text:
                body = ocr_result.text
            return f"{header}\n{body}"
        lines = [header]
        for element in elements:
            box = element.bounds.to_dict() if element.bounds else {}
            value = f' = "{element.value}"' if element.value else ""
            lines.append(
                f"#{element.ref} {element.role} \"{element.name}\"{value} "
                f"at ({box.get('x', 0)},{box.get('y', 0)},{box.get('width', 0)}x{box.get('height', 0)})"
            )
        return "\n".join(lines)


__all__ = ["ObservationEngine", "ax_digest"]
