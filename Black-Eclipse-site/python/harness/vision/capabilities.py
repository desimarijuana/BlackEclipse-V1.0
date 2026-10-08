"""Vision capability detection.

Wraps the existing model-runtime capability registry with the vision-specific
questions the orchestrator must answer:

    * can the RUN's model accept an image natively?
    * if not, which configured/available model can?
    * does the chosen model support structured JSON output (for grounding)?

It never assumes a capability: an undeclared model is `UNKNOWN`, and `UNKNOWN`
is treated as "no" for native routing (the orchestrator then falls back to the
auxiliary vision model, or reports honestly). Detected support can be upgraded
by a successful real call (`record_vision_success`) or downgraded by a failure
that is specifically about image input (`record_vision_failure`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..model_runtime.capability import detect_capabilities
from ..model_runtime.types import CapabilityState, ModelCapabilities

# Vision-specific capability keys layered on top of the runtime vocabulary.
VISION_SUPPORT = "vision"

#: Image formats a provider is known to accept. Absent = unknown (we let the
#: provider decide and report honestly on failure).
DEFAULT_IMAGE_FORMATS = ("png", "jpeg", "webp", "gif")


@dataclass
class VisionCapabilities:
    """The vision-relevant slice of a model's capabilities."""

    vision: CapabilityState = CapabilityState.UNKNOWN
    structured_output: CapabilityState = CapabilityState.UNKNOWN
    tool_calling: CapabilityState = CapabilityState.UNKNOWN
    local: bool = False
    model_id: Optional[str] = None
    provider: Optional[str] = None
    max_image_bytes: Optional[int] = None
    supported_formats: tuple[str, ...] = ()

    @property
    def native_vision(self) -> bool:
        return self.vision is CapabilityState.SUPPORTED

    def to_dict(self) -> dict[str, Any]:
        return {
            "vision": self.vision.value,
            "structuredOutput": self.structured_output.value,
            "toolCalling": self.tool_calling.value,
            "nativeVision": self.native_vision,
            "local": self.local,
            "model": self.model_id,
            "provider": self.provider,
            "supportedFormats": list(self.supported_formats),
        }


def _local_provider(provider_id: Optional[str]) -> bool:
    if not provider_id:
        return False
    try:
        from ..model_runtime import get_runtime  # noqa: PLC0415

        provider = get_runtime().providers.get_provider(provider_id)
        return bool(provider is not None and provider.keyless)
    except Exception:  # noqa: BLE001
        return provider_id in ("ollama", "lmstudio", "local", "vllm", "custom")


def capabilities_for_resolution(resolution: Any) -> VisionCapabilities:
    """Build vision capabilities from a model-runtime `Resolution`."""
    model = getattr(resolution, "model", None)
    settings = getattr(resolution, "settings", None)
    provider_id = getattr(settings, "provider", None)
    model_id = getattr(settings, "model", None)
    caps: Optional[ModelCapabilities] = getattr(model, "capabilities", None) if model is not None else None
    if caps is None:
        # Synthesize from declared defaults for an uncatalogued id.
        try:
            caps = detect_capabilities(
                kind=_kind_of(provider_id), model_id=model_id or "",
                context_window=getattr(settings, "context_window", None),
            )
        except Exception:  # noqa: BLE001
            caps = ModelCapabilities({})
    return VisionCapabilities(
        vision=caps.state(VISION_SUPPORT),
        structured_output=caps.state("structured_output"),
        tool_calling=caps.state("tool_calling"),
        local=_local_provider(provider_id),
        model_id=model_id,
        provider=provider_id,
        supported_formats=DEFAULT_IMAGE_FORMATS,
    )


def capabilities_for_settings(settings: Any, *, task: Optional[str] = None) -> VisionCapabilities:
    """Resolve a settings object through the runtime, then read its capabilities."""
    if settings is None:
        return VisionCapabilities()
    try:
        from ..model_runtime import get_runtime  # noqa: PLC0415

        resolution = get_runtime().resolve_for_run(settings, task=task or "default")
        return capabilities_for_resolution(resolution)
    except Exception:  # noqa: BLE001 - detection must never crash the orchestrator
        provider_id = getattr(settings, "provider", None)
        try:
            caps = detect_capabilities(kind=_kind_of(provider_id), model_id=getattr(settings, "model", "") or "")
            return VisionCapabilities(
                vision=caps.state(VISION_SUPPORT),
                structured_output=caps.state("structured_output"),
                local=_local_provider(provider_id),
                model_id=getattr(settings, "model", None), provider=provider_id,
            )
        except Exception:  # noqa: BLE001
            return VisionCapabilities(model_id=getattr(settings, "model", None), provider=provider_id)


def _kind_of(provider_id: Optional[str]) -> str:
    try:
        from ..model_runtime import get_runtime  # noqa: PLC0415

        provider = get_runtime().providers.get_provider(provider_id or "")
        if provider is not None:
            return provider.kind
    except Exception:  # noqa: BLE001
        pass
    return "openai_compatible"


def record_vision_success(model_info: Any) -> None:
    """Upgrade a model's vision capability to SUPPORTED after a real success."""
    if model_info is None:
        return
    try:
        from ..model_runtime import get_runtime  # noqa: PLC0415

        runtime = get_runtime()
        caps = getattr(model_info, "capabilities", None)
        if caps is None:
            return
        upgraded = caps.with_state(VISION_SUPPORT, CapabilityState.SUPPORTED)
        model_info.capabilities = upgraded
        record = getattr(runtime.capabilities, "record_probe", None)
        if callable(record) and getattr(model_info, "provider_id", None):
            try:
                record(f"{model_info.provider_id}/{model_info.id}", {VISION_SUPPORT: CapabilityState.SUPPORTED})
            except TypeError:
                pass
    except Exception:  # noqa: BLE001 - capability bookkeeping must never break a call
        pass


def record_vision_failure(model_info: Any) -> None:
    """Downgrade a claimed vision capability to DEGRADED after a specific failure."""
    if model_info is None:
        return
    try:
        caps = getattr(model_info, "capabilities", None)
        if caps is None or not caps.is_supported(VISION_SUPPORT):
            return
        model_info.capabilities = caps.with_state(VISION_SUPPORT, CapabilityState.DEGRADED)
    except Exception:  # noqa: BLE001
        pass


__all__ = [
    "VISION_SUPPORT", "VisionCapabilities", "capabilities_for_resolution",
    "capabilities_for_settings", "record_vision_success", "record_vision_failure",
    "DEFAULT_IMAGE_FORMATS",
]
