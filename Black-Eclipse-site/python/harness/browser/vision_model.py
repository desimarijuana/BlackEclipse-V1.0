"""Real visual interpretation for the browser, reusing the harness model runtime.

`browser_vision` produces a screenshot and a DOM-derived visual map. This module
adds an OPTIONAL interpretation layer: when the run has a multimodal model
configured, it asks that model a bounded visual question about the screenshot and
returns prose plus any located elements — no second provider stack, no fake
vision. When no multimodal model is available (or the image cannot be encoded)
the interpreter reports `available: false` honestly and the tool falls back to the
raw screenshot + map, exactly as before.

The screenshot is read from the local artifact path the tool already wrote; the
image bytes never leave the machine except to the operator's OWN configured model
provider.
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)

# The visual reasoning prompt. Bounded, and explicit that a missing target must
# be reported as absent rather than invented.
_LOCATE_QUESTIONS: dict[str, str] = {
    "default": (
        "You are looking at a screenshot of a web page to help an automation "
        "agent. Describe briefly: the page's purpose, the main regions, and the "
        "visible interactive controls (buttons, links, fields) in reading order."
    ),
}


@dataclass
class LocatedElement:
    label: str
    role: str
    x: Optional[float] = None
    y: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label, "role": self.role,
            "x": self.x, "y": self.y, "width": self.width, "height": self.height,
            "confidence": round(self.confidence, 2),
        }


@dataclass
class Interpretation:
    available: bool
    model: Optional[str] = None
    text: str = ""
    elements: list[LocatedElement] = field(default_factory=list)
    confidence: float = 0.0
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "available": self.available, "model": self.model, "text": self.text,
            "elements": [e.to_dict() for e in self.elements],
            "confidence": round(self.confidence, 2), "error": self.error,
        }


def _encode(path: str) -> Optional[str]:
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    return base64.b64encode(data).decode("ascii")


class BrowserVisionInterpreter:
    """Bounded visual Q&A over a screenshot through the harness model runtime."""

    def __init__(self, settings: Any = None) -> None:
        self._settings = settings

    @property
    def available(self) -> bool:
        return self._settings is not None

    def _prompt(self, query: Optional[str]) -> str:
        base = (
            "You are looking at a screenshot of a web page to help an automation "
            "agent. Answer only from what is visible. Reply with one short "
            "sentence, then a JSON object "
            '{"elements":[{"label":..,"role":..,"x":..,"y":..,"width":..,"height":..,"confidence":0..1}]} '
            "where x/y/width/height are pixels in the image. If the target is "
            "absent, return {\"elements\":[]}."
        )
        if query:
            base += f" The agent is specifically looking for: {query!r}."
        return base

    async def interpret(self, screenshot_path: str, *, query: Optional[str] = None) -> Interpretation:
        if not self.available:
            return Interpretation(
                available=False,
                error="no multimodal model is configured for this run",
            )
        b64 = _encode(screenshot_path)
        if b64 is None:
            return Interpretation(available=False, error="the screenshot couldn't be read")
        try:
            from langchain_core.messages import HumanMessage  # noqa: PLC0415

            from ..model_runtime import get_runtime  # noqa: PLC0415
            from ..models import build_chat_model  # noqa: PLC0415

            runtime = get_runtime()
            # The `vision` task profile requires a model whose `vision` capability
            # is known-good; the router refuses one that is not.
            resolution = runtime.resolve_for_run(self._settings, task="vision")
            model = runtime.build(resolution.settings, builder=build_chat_model, adapter=resolution.adapter)
            message = HumanMessage(content=[
                {"type": "text", "text": self._prompt(query)},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ])
            response = await model.ainvoke([message])
            text = getattr(response, "content", "")
            if isinstance(text, list):
                text = "\n".join(str(getattr(part, "text", part)) for part in text)
            model_id = f"{resolution.settings.provider}/{resolution.settings.model}"
            return self._parse(str(text), model_id)
        except Exception as exc:  # noqa: BLE001 - a model failure is an honest miss
            return Interpretation(available=False, error=str(exc)[:200])

    def _parse(self, text: str, model_id: str) -> Interpretation:
        elements: list[LocatedElement] = []
        match = _JSON_BLOCK.search(text or "")
        if match:
            try:
                payload = json.loads(match.group(0))
                raw = payload.get("elements", []) if isinstance(payload, dict) else []
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    elements.append(LocatedElement(
                        label=str(item.get("label") or item.get("name") or ""),
                        role=str(item.get("role") or "element"),
                        x=_num(item.get("x")), y=_num(item.get("y")),
                        width=_num(item.get("width")), height=_num(item.get("height")),
                        confidence=_num(item.get("confidence")) or 0.5,
                    ))
            except (ValueError, TypeError):
                elements = []
        # The prose is the text with the JSON block removed, trimmed.
        prose = _JSON_BLOCK.sub("", text or "").strip()
        confidence = (sum(e.confidence for e in elements) / len(elements)) if elements else 0.4
        return Interpretation(
            available=True, model=model_id, text=prose[:4000],
            elements=elements, confidence=confidence,
        )


def _num(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


__all__ = ["BrowserVisionInterpreter", "Interpretation", "LocatedElement"]
