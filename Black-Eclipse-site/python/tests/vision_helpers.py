"""Shared helpers for the vision test suite.

Provides a real PNG builder (Pillow) and a fake model factory that satisfies the
LangChain chat-model surface the runtime expects. The fake is used ONLY in tests;
production paths always build a real model through `harness.models`.
"""

from __future__ import annotations

import base64
import io
import json
from typing import Any, Optional


def png_bytes(width: int = 120, height: int = 80, color: tuple[int, int, int] = (200, 200, 200)) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="PNG")
    return buffer.getvalue()


def png_b64(width: int = 120, height: int = 80, color: tuple[int, int, int] = (200, 200, 200)) -> str:
    return base64.b64encode(png_bytes(width, height, color)).decode("ascii")


def data_uri(width: int = 120, height: int = 80) -> str:
    return "data:image/png;base64," + png_b64(width, height)


def jpeg_bytes(width: int = 100, height: int = 70) -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (width, height), (10, 120, 200)).save(buffer, format="JPEG")
    return buffer.getvalue()


class FakeMessage:
    def __init__(self, content: str) -> None:
        self.content = content
        self.usage_metadata = {"input_tokens": 11, "output_tokens": 7, "total_tokens": 18}


class FakeModel:
    """A minimal chat model: returns a scripted payload (or raises)."""

    def __init__(self, payload: Any = None, *, text: Optional[str] = None, error: Optional[BaseException] = None) -> None:
        self._payload = payload
        self._text = text
        self._error = error
        self.calls = 0
        self.messages: list[Any] = []

    def bind_tools(self, tools: Any) -> "FakeModel":
        return self

    def bind(self, **kwargs: Any) -> "FakeModel":
        return self

    async def ainvoke(self, messages: Any, **kwargs: Any) -> FakeMessage:
        self.calls += 1
        self.messages = messages
        if self._error is not None:
            raise self._error
        if self._text is not None:
            return FakeMessage(self._text)
        return FakeMessage(json.dumps(self._payload))


def install_fake_model(monkeypatch: Any, model: FakeModel) -> None:
    """Patch `harness.models.build_chat_model` so the runtime builds our fake."""
    import harness.models as models

    monkeypatch.setattr(models, "build_chat_model", lambda settings: model)


def install_model_sequence(monkeypatch: Any, models_list: list[FakeModel]) -> None:
    """Return a DIFFERENT fake per successive build call (for fallback tests)."""
    import harness.models as models

    calls = {"n": 0}

    def _builder(settings: Any) -> FakeModel:
        index = min(calls["n"], len(models_list) - 1)
        calls["n"] += 1
        return models_list[index]

    monkeypatch.setattr(models, "build_chat_model", _builder)
