"""Image generation through the ONE provider abstraction.

Image generation is a vision-adjacent capability: it uses the same model
settings and, where the provider exposes it, the same credential path. It does
NOT go through the multimodal chat `build_chat_model` factory — generation is a
different API surface — so it is a small, dedicated adapter that speaks the
OpenAI-compatible `/images/generations` protocol (used by OpenAI, Azure-compatible
gateways, LiteLLM, OpenRouter-compatible gateways and local Stable-Diffusion
servers).

Honest by construction: if the resolved provider has no image-generation
capability, or no reachable endpoint, the call raises a classified `VisionError`
(never a placeholder image).
"""

from __future__ import annotations

import base64
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from .config import VisionConfig, vision_config
from .contracts import now_iso
from .errors import VisionError, VisionErrorClass
from .image import DecodedImage, decode_bytes


@dataclass
class GeneratedImage:
    decoded: DecodedImage
    prompt: str
    provider: Optional[str]
    model: Optional[str]
    revised_prompt: Optional[str] = None
    created_at: str = field(default_factory=now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": "generated_image",
            "assetId": self.decoded.asset_id,
            "width": self.decoded.width,
            "height": self.decoded.height,
            "mimeType": self.decoded.mime_type,
            "provider": self.provider,
            "model": self.model,
            "revisedPrompt": self.revised_prompt,
            "createdAt": self.created_at,
        }


def _image_generation_supported(settings: Any) -> tuple[bool, str]:
    """Whether the resolved model declares image-generation support."""
    if settings is None:
        return False, "no model settings were resolved"
    try:
        from ..model_runtime import get_runtime  # noqa: PLC0415

        resolution = get_runtime().resolve_for_run(settings, task="image_generation")
        model = resolution.model
        if model is not None and model.capabilities.is_supported("image_generation"):
            return True, ""
        return False, (
            f"the resolved model {getattr(resolution.settings, 'provider', '?')}/"
            f"{getattr(resolution.settings, 'model', '?')} does not declare image-generation support"
        )
    except Exception as exc:  # noqa: BLE001
        return False, f"image-generation capability could not be resolved: {exc}"


def _endpoint_and_key(settings: Any) -> tuple[str, Optional[str]]:
    base = (getattr(settings, "base_url", None) or "").rstrip("/")
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    if base and not base.endswith("/v1") and "/v1" not in base:
        # An OpenAI-compatible server usually exposes /v1; only append when the
        # URL looks like a bare host, never rewriting a path the operator chose.
        if base.count("/") <= 2:
            base = base + "/v1"
    url = (base + "/images/generations") if base else "https://api.openai.com/v1/images/generations"
    key = getattr(settings, "api_key", None)
    if not key:
        provider = getattr(settings, "provider", None)
        try:
            from ..models import PROVIDER_CATALOG  # noqa: PLC0415

            spec = PROVIDER_CATALOG.get(provider)
            if spec is not None and spec.env_var:
                key = os.environ.get(spec.env_var)
        except Exception:  # noqa: BLE001
            key = None
        if not key:
            key = "local"
    return url, key


async def generate_image(
    settings: Any,
    prompt: str,
    *,
    size: str = "1024x1024",
    model: Optional[str] = None,
    cfg: Optional[VisionConfig] = None,
    timeout_s: float = 120.0,
) -> GeneratedImage:
    """Generate an image from a text prompt. Raises a classified `VisionError`."""
    cfg = cfg or vision_config()
    if not prompt or not prompt.strip():
        raise VisionError(VisionErrorClass.INVALID_INPUT, "an image-generation prompt is required")
    if settings is None:
        raise VisionError(VisionErrorClass.NO_VISION_MODEL, "no model settings were resolved for image generation")

    supported, reason = _image_generation_supported(settings)
    if not supported:
        raise VisionError(VisionErrorClass.NO_VISION_MODEL, reason)

    try:
        import httpx  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        raise VisionError(
            VisionErrorClass.PROVIDER_UNAVAILABLE, "the HTTP client is unavailable", cause=exc
        ) from exc

    url, key = _endpoint_and_key(settings)
    use_model = model or getattr(settings, "model", None)
    payload = {"prompt": prompt, "n": 1, "size": size}
    if use_model:
        payload["model"] = use_model
    headers = {"Content-Type": "application/json"}
    if key and key != "local":
        headers["Authorization"] = f"Bearer {key}"

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.post(url, json=payload, headers=headers)
    except httpx.HTTPError as exc:
        raise VisionError(
            VisionErrorClass.PROVIDER_UNAVAILABLE, f"the image endpoint could not be reached: {exc}",
            provider=getattr(settings, "provider", None), model=use_model, cause=exc,
        ) from exc

    if response.status_code in (401, 403):
        raise VisionError(
            VisionErrorClass.AUTH_ERROR, "the image endpoint rejected the credentials",
            provider=getattr(settings, "provider", None), model=use_model,
        )
    if response.status_code == 429:
        raise VisionError(
            VisionErrorClass.RATE_LIMIT, "the image endpoint rate-limited the request",
            provider=getattr(settings, "provider", None), model=use_model,
        )
    if response.status_code >= 400:
        raise VisionError(
            VisionErrorClass.PROVIDER_ERROR,
            f"the image endpoint returned HTTP {response.status_code}: {response.text[:200]}",
            provider=getattr(settings, "provider", None), model=use_model,
        )

    try:
        body = response.json()
    except ValueError as exc:
        raise VisionError(
            VisionErrorClass.MALFORMED_RESPONSE, "the image endpoint returned non-JSON",
            provider=getattr(settings, "provider", None), model=use_model, cause=exc,
        ) from exc

    entries = body.get("data") if isinstance(body, dict) else None
    if not isinstance(entries, list) or not entries:
        raise VisionError(
            VisionErrorClass.MALFORMED_RESPONSE, "the image endpoint returned no image data",
            provider=getattr(settings, "provider", None), model=use_model,
        )
    entry = entries[0] if isinstance(entries[0], dict) else {}
    raw: Optional[bytes] = None
    if entry.get("b64_json"):
        try:
            raw = base64.b64decode(entry["b64_json"])
        except (ValueError, TypeError):
            raw = None
    if raw is None and entry.get("url"):
        try:
            async with httpx.AsyncClient(timeout=timeout_s, follow_redirects=True) as client:
                image_response = await client.get(entry["url"])
            if image_response.status_code < 400:
                raw = image_response.content
        except httpx.HTTPError:
            raw = None
    if raw is None:
        raise VisionError(
            VisionErrorClass.MALFORMED_RESPONSE, "the image endpoint returned no usable image bytes",
            provider=getattr(settings, "provider", None), model=use_model,
        )

    decoded = decode_bytes(raw, cfg=cfg, source="generated", expected_mime=entry.get("mime_type"))
    return GeneratedImage(
        decoded=decoded, prompt=prompt,
        provider=getattr(settings, "provider", None), model=use_model,
        revised_prompt=entry.get("revised_prompt"),
    )


__all__ = ["GeneratedImage", "generate_image"]
