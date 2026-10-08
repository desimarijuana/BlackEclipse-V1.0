"""Vision model calls through the ONE provider abstraction.

Never a second provider stack: this module builds a LangChain `HumanMessage`
carrying image content parts and invokes it through `harness.model_runtime`
(`resolve_for_run` → `build` → `invoke`), so routing, retry, fallback, health,
usage and cost all apply exactly as they do for text.

Provider-specific differences (native OpenAI `image_url`, Anthropic/Google
content blocks) are handled by the LangChain integration the runtime already
selects via `build_chat_model`; this module only shapes the neutral message.
"""

from __future__ import annotations

import base64
import io
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from .contracts import VisionUsage
from .errors import VisionError, VisionErrorClass


@dataclass
class ModelCallResult:
    text: str
    provider: Optional[str]
    model: Optional[str]
    backend: str
    latency_ms: int
    usage: VisionUsage
    model_info: Any = None
    raw: Any = None


def data_uri(image: Any, *, fmt: str = "PNG") -> str:
    """Encode a PIL image (or raw bytes) as a data URI for a multimodal message."""
    if isinstance(image, (bytes, bytearray)):
        payload = bytes(image)
        mime = "image/png"
    else:
        buffer = io.BytesIO()
        image.save(buffer, format=fmt)
        payload = buffer.getvalue()
        mime = "image/jpeg" if fmt.upper() in ("JPEG", "JPG") else f"image/{fmt.lower()}"
    return f"data:{mime};base64,{base64.b64encode(payload).decode('ascii')}"


def build_vision_message(prompt: str, images: list[str], *, image_first: bool = False) -> Any:
    """Build a `HumanMessage` with text + one or more image data URIs."""
    from langchain_core.messages import HumanMessage  # noqa: PLC0415

    parts: list[dict[str, Any]] = []
    image_parts = [
        {"type": "image_url", "image_url": {"url": uri}} for uri in images
    ]
    if image_first:
        parts.extend(image_parts)
        parts.append({"type": "text", "text": prompt})
    else:
        parts.append({"type": "text", "text": prompt})
        parts.extend(image_parts)
    return HumanMessage(content=parts)


async def call_model(
    settings: Any,
    prompt: str,
    images: list[Any],
    *,
    task: str = "vision",
    timeout_s: float = 120.0,
    temperature: Optional[float] = None,
    structured: bool = False,
    backend: str = "model",
) -> ModelCallResult:
    """Invoke a multimodal model and return normalized text + accounting.

    `images` are PIL images or raw bytes. Raises a classified `VisionError` on
    any failure — never a fake success.
    """
    if settings is None:
        raise VisionError(VisionErrorClass.NO_VISION_MODEL, "no model settings were resolved for vision")

    uris = [data_uri(img) for img in images]

    try:
        from ..model_runtime import get_runtime  # noqa: PLC0415
        from ..models import build_chat_model  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise VisionError(
            VisionErrorClass.NO_VISION_MODEL, "the model runtime is unavailable", cause=exc
        ) from exc

    runtime = get_runtime()
    try:
        resolution = runtime.resolve_for_run(settings, task=task)
    except Exception as exc:  # noqa: BLE001
        raise VisionError(
            VisionErrorClass.PROVIDER_ERROR, f"the vision model could not be resolved: {exc}", cause=exc
        ) from exc

    message = build_vision_message(prompt, uris)
    prompt_text = prompt
    if structured:
        prompt_text = prompt + "\n\nReturn ONLY a single JSON object. No prose, no markdown fences."
        message = build_vision_message(prompt_text, uris)

    started = time.monotonic()

    def _builder(s: Any) -> Any:
        return build_chat_model(s)

    async def _invoke(model: Any) -> Any:
        call = model.ainvoke([message])
        import asyncio  # noqa: PLC0415

        return await asyncio.wait_for(call, timeout=timeout_s)

    try:
        response = await runtime.invoke(
            invoke_fn=_invoke,
            primary_model=runtime.build(resolution.settings, builder=_builder, adapter=resolution.adapter),
            resolution=resolution,
            task=task,
            raise_original=True,
        )
    except VisionError:
        raise
    except BaseException as exc:  # noqa: BLE001 - classify the provider failure
        from ..model_runtime.errors import ErrorClass  # noqa: PLC0415

        classified = _classify(exc)
        raise VisionError(
            classified,
            f"the vision model call failed: {str(exc)[:300]}",
            provider=getattr(resolution.settings, "provider", None),
            model=getattr(resolution.settings, "model", None),
            cause=exc,
        ) from exc

    latency_ms = int((time.monotonic() - started) * 1000)
    text = _extract_text(response)
    usage = _extract_usage(response)
    model_info = resolution.model
    return ModelCallResult(
        text=text,
        provider=getattr(resolution.settings, "provider", None),
        model=getattr(resolution.settings, "model", None),
        backend=backend,
        latency_ms=latency_ms,
        usage=usage,
        model_info=model_info,
        raw=response,
    )


def _classify(exc: BaseException) -> VisionErrorClass:
    """Map a provider exception to a vision error class (bounded, no network)."""
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "timeout" in name or "timeout" in text:
        return VisionErrorClass.PROVIDER_TIMEOUT
    if "ratelimit" in name or "429" in text or "rate limit" in text:
        return VisionErrorClass.RATE_LIMIT
    if "auth" in name or "401" in text or "403" in text or "api key" in text:
        return VisionErrorClass.AUTH_ERROR
    if "connect" in name or "network" in name or "unavailable" in text:
        return VisionErrorClass.PROVIDER_UNAVAILABLE
    if "image" in text and ("invalid" in text or "unsupported" in text or "format" in text):
        return VisionErrorClass.UNSUPPORTED_FORMAT
    return VisionErrorClass.PROVIDER_ERROR


def _extract_text(response: Any) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return str(content)


def _extract_usage(response: Any) -> VisionUsage:
    try:
        from ..model_runtime.runtime import extract_usage  # noqa: PLC0415

        usage = extract_usage(response)
        return VisionUsage(
            input_tokens=usage.input_tokens, output_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens, estimated=usage.estimated,
        )
    except Exception:  # noqa: BLE001
        return VisionUsage()


__all__ = ["ModelCallResult", "build_vision_message", "call_model", "data_uri"]
