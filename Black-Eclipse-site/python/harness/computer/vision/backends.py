"""Vision backends.

`LocalModelVision` reuses the harness's OWN model runtime (`harness.model_runtime`)
to ask a multimodal model a bounded visual question — no second provider stack.
`UnavailableVision` is the honest state when no multimodal model is configured
(or the resolved model cannot accept images).

The backend returns TEXT and, when the model cooperates, a JSON block of located
elements. It never claims a location it did not receive.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any, Optional

from ..models import Bounds
from .base import LocatedElement, VisionEngine, VisionResult

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _png_b64(image: Any) -> Optional[str]:
    if image is None:
        return None
    try:
        import io  # noqa: PLC0415

        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return base64.b64encode(buffer.getvalue()).decode("ascii")
    except Exception:  # noqa: BLE001
        return None


class UnavailableVision(VisionEngine):
    id = "none"
    available = False

    def __init__(self, reason: str = "") -> None:
        self.reason = reason or "no multimodal vision model is configured"

    async def locate(self, image: Any, query: str, *, bounds: Optional[Bounds] = None) -> VisionResult:
        return VisionResult(available=False, backend=self.id, error=self.reason)

    async def describe(self, image: Any, *, bounds: Optional[Bounds] = None) -> VisionResult:
        return VisionResult(available=False, backend=self.id, error=self.reason)


class LocalModelVision(VisionEngine):
    """Visual reasoning through the harness model runtime.

    `local` reflects whether the resolved model provider is local (e.g. Ollama);
    a cloud model sets `local=False` so the router can refuse sensitive frames.
    """

    id = "model_runtime"

    def __init__(self, *, settings: Any = None, local: bool = True) -> None:
        self._settings = settings
        self.local = local
        self.available = settings is not None

    async def _ask(self, image: Any, prompt: str, *, bounds: Optional[Bounds]) -> VisionResult:
        if not self.available:
            return VisionResult(available=False, backend=self.id, error="no vision model settings were resolved")
        b64 = _png_b64(image)
        if b64 is None:
            return VisionResult(available=False, backend=self.id, error="the frame couldn't be encoded for the model")
        try:
            from langchain_core.messages import HumanMessage  # noqa: PLC0415

            from ...model_runtime import get_runtime  # noqa: PLC0415
            from ...models import build_chat_model  # noqa: PLC0415

            runtime = get_runtime()
            resolution = runtime.resolve_for_run(self._settings, task="vision")
            model = runtime.build(resolution.settings, builder=build_chat_model, adapter=resolution.adapter)
            message = HumanMessage(content=[
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}},
            ])
            response = await model.ainvoke([message])
            text = getattr(response, "content", "")
            if isinstance(text, list):
                text = "\n".join(str(getattr(part, "text", part)) for part in text)
            return self._parse(str(text), bounds)
        except Exception as exc:  # noqa: BLE001 - a model failure is an honest miss
            return VisionResult(available=False, backend=self.id, error=str(exc)[:200], local=self.local)

    def _parse(self, text: str, bounds: Optional[Bounds]) -> VisionResult:
        elements: list[LocatedElement] = []
        match = _JSON_BLOCK.search(text or "")
        if match:
            try:
                payload = json.loads(match.group(0))
                for item in payload.get("elements", []) if isinstance(payload, dict) else []:
                    box = Bounds.from_any(item.get("bounds"))
                    elements.append(LocatedElement(
                        label=str(item.get("label") or item.get("name") or ""),
                        role=str(item.get("role") or "element"),
                        bounds=box, confidence=float(item.get("confidence", 0.5)),
                    ))
            except (ValueError, TypeError):
                elements = []
        return VisionResult(
            available=True, backend=self.id, text=text, elements=elements,
            confidence=(sum(e.confidence for e in elements) / len(elements)) if elements else 0.4,
            local=self.local,
        )

    async def locate(self, image: Any, query: str, *, bounds: Optional[Bounds] = None) -> VisionResult:
        prompt = (
            "You are looking at a desktop screenshot to help an automation agent. "
            f"Find: {query!r}. Reply with a short sentence and a JSON object "
            '{"elements":[{"label":..,"role":..,"bounds":[left,top,right,bottom],"confidence":0..1}]}. '
            "Coordinates are pixels in the image. If the target is absent, return {\"elements\":[]}."
        )
        return await self._ask(image, prompt, bounds=bounds)

    async def describe(self, image: Any, *, bounds: Optional[Bounds] = None) -> VisionResult:
        prompt = (
            "Describe this desktop screenshot briefly for an automation agent: the "
            "application, the main panels, and any visible fields or buttons."
        )
        return await self._ask(image, prompt, bounds=bounds)


__all__ = ["LocalModelVision", "UnavailableVision"]
