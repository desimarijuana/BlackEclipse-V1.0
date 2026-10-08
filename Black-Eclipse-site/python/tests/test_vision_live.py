"""Live vision smoke tests — OPT-IN, never part of `npm test`.

These call a REAL multimodal model (a cloud provider or a local VLM through
Ollama/LM Studio) and assert it actually reads text out of an image. They are
skipped unless the operator explicitly enables them, exactly like
`test_application_provider_live.py` and `test_git_provider_live.py`:

    BLACK_ECLIPSE_VISION_IT=1                 # turn the vision smoke on
    BLACK_ECLIPSE_VISION_PROVIDER=ollama      # default: ollama
    BLACK_ECLIPSE_VISION_MODEL=<model>        # REQUIRED, e.g. llava / a vision model
    BLACK_ECLIPSE_VISION_BASE_URL=http://127.0.0.1:11434/v1
    BLACK_ECLIPSE_VISION_API_KEY=<key>        # optional; env/vault is used otherwise

They NEVER run in CI and NEVER run without the opt-in, because they touch a live
model (and may incur cost). When they are not enabled the run reports
"NOT RUN — provider credentials unavailable" rather than a false success.

The offline suites (`test_vision_orchestrator.py`, `test_vision_tools.py`) cover
the same paths deterministically with a scripted model.
"""

from __future__ import annotations

import asyncio
import base64
import io
import os

import pytest

from harness.schemas import ModelSettings
from harness.vision.contracts import VisionInput
from harness.vision.orchestrator import VisionContext, orchestrate

_ENABLED = os.environ.get("BLACK_ECLIPSE_VISION_IT") in ("1", "true", "True")
_PROVIDER = (os.environ.get("BLACK_ECLIPSE_VISION_PROVIDER") or "ollama").strip()
_MODEL = (os.environ.get("BLACK_ECLIPSE_VISION_MODEL") or "").strip()
_BASE_URL = (os.environ.get("BLACK_ECLIPSE_VISION_BASE_URL") or "").strip() or None
_API_KEY = (os.environ.get("BLACK_ECLIPSE_VISION_API_KEY") or "").strip() or None

pytestmark = pytest.mark.skipif(
    not _ENABLED or not _MODEL,
    reason=(
        "NOT RUN — live vision smoke is opt-in: set BLACK_ECLIPSE_VISION_IT=1 and "
        "BLACK_ECLIPSE_VISION_MODEL (plus BLACK_ECLIPSE_VISION_PROVIDER/BASE_URL)"
    ),
)

# The word "42" is drawn into the test image; a vision model that reads the image
# returns it. OCR engines also read the digits, so this is a robust assertion.
_KNOWN_TOKEN = "42"


def _image_b64(text: str) -> str:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (360, 130), (255, 255, 255))
    draw = ImageDraw.Draw(img)
    draw.text((20, 55), text, fill=(0, 0, 0))
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode()


def _settings() -> ModelSettings:
    return ModelSettings(
        provider=_PROVIDER, model=_MODEL, base_url=_BASE_URL, api_key=_API_KEY,
    )


def test_live_native_vision_reads_the_image():
    """A real model reads the drawn text (the native-vision path)."""
    b64 = _image_b64(f"ECLIPSE VISION {_KNOWN_TOKEN}")
    result = asyncio.run(orchestrate(
        VisionInput(source=b64, source_kind="base64", mode="analyze",
                    question="What text is written in this image?"),
        VisionContext(run_settings=_settings()),
    ))
    assert result.ok, (
        f"the live vision model {_PROVIDER}/{_MODEL} did not return a result: "
        f"{(result.error or {}).get('errorClass')} {(result.error or {}).get('message')}"
    )
    assert _KNOWN_TOKEN in (result.description or "") or any(
        _KNOWN_TOKEN in o.text for o in result.observations
    ), f"the model answered but did not read the drawn {_KNOWN_TOKEN!r}: {result.description!r}"


def test_live_ocr_reads_the_image():
    """The deterministic OCR engine reads the drawn digits (no model required)."""
    from harness.vision.image import decode_bytes
    from harness.vision.ocr import ocr_available, run_ocr

    if not ocr_available():
        pytest.skip("no OCR engine on this machine")
    decoded = decode_bytes(base64.b64decode(_image_b64(f"BALANCE {_KNOWN_TOKEN}.56")))
    run = run_ocr(decoded)
    assert run.text, "the OCR engine returned no text"
    assert _KNOWN_TOKEN in run.text, f"OCR did not read the drawn {_KNOWN_TOKEN!r}: {run.text!r}"


def test_live_auxiliary_fallback_to_configured_model():
    """A run model that cannot see images falls back to the configured model."""
    b64 = _image_b64(f"FALLBACK {_KNOWN_TOKEN}")
    # The run model is a deliberately text-only provider; the aux is the real one.
    run_settings = ModelSettings(provider="ollama", model="__no_such_text_model__",
                                 base_url=_BASE_URL, api_key=None)
    result = asyncio.run(orchestrate(
        VisionInput(source=b64, source_kind="base64", mode="analyze", question="What number is shown?"),
        VisionContext(run_settings=run_settings, aux_settings=_settings()),
    ))
    assert result.ok, f"auxiliary fallback failed: {result.error}"
    assert result.provenance.get("fallback") is True or _KNOWN_TOKEN in (result.description or "")
