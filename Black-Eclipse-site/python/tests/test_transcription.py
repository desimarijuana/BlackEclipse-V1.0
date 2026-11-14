"""Voice transcription: validation + one OpenAI-compatible provider call.

These tests pin the honest failure classes and the multipart shape without any
network access.
"""

from __future__ import annotations

import base64

import httpx
import pytest

from harness.transcription import service
from harness.transcription.service import TranscriptionError, transcribe


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None) -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}

    def json(self) -> dict:
        return self._payload


class _FakeClient:
    def __init__(self, factory: "_Factory") -> None:
        self.factory = factory

    async def __aenter__(self) -> "_FakeClient":
        return self

    async def __aexit__(self, *exc) -> bool:  # noqa: ANN002
        return False

    async def post(self, url, headers=None, data=None, files=None):  # noqa: ANN001
        self.factory.calls.append(
            {"url": url, "headers": headers or {}, "data": data or {}, "files": files or {}}
        )
        if self.factory.error is not None:
            raise self.factory.error
        return _FakeResponse(self.factory.status, self.factory.payload)


class _Factory:
    def __init__(self, status: int = 200, payload: dict | None = None) -> None:
        self.status = status
        self.payload = payload if payload is not None else {"text": "analyze NVDA earnings"}
        self.error: Exception | None = None
        self.calls: list[dict] = []

    def __call__(self, *args, **kwargs):  # noqa: ANN002, ANN003
        return _FakeClient(self)


AUDIO = base64.b64encode(b"fake-webm-bytes").decode("ascii")


def _kwargs(**overrides):
    base = dict(
        audio_base64=AUDIO,
        mime_type="audio/webm",
        provider="openai",
        base_url="https://api.openai.com/v1",
        api_key="sk-test",
        model="gpt-4o-mini-transcribe",
        language="en",
        prompt="AAPL, NVDA",
        duration_ms=1500,
    )
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_transcribes_with_the_openai_compatible_multipart_shape(monkeypatch):
    factory = _Factory()
    monkeypatch.setattr(service.httpx, "AsyncClient", factory)

    result = await transcribe(**_kwargs())

    assert result["text"] == "analyze NVDA earnings"
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-4o-mini-transcribe"
    call = factory.calls[0]
    assert call["url"] == "https://api.openai.com/v1/audio/transcriptions"
    assert call["headers"]["Authorization"] == "Bearer sk-test"
    assert call["data"]["model"] == "gpt-4o-mini-transcribe"
    assert call["data"]["language"] == "en"
    assert call["data"]["prompt"] == "AAPL, NVDA"
    assert call["files"]["file"][2] == "audio/webm"


@pytest.mark.asyncio
async def test_keyless_local_endpoint_sends_no_authorization(monkeypatch):
    factory = _Factory()
    monkeypatch.setattr(service.httpx, "AsyncClient", factory)

    await transcribe(
        **_kwargs(
            provider="custom",
            base_url="http://127.0.0.1:8080/v1",
            api_key=None,
            model="whisper-1",
        )
    )

    assert "Authorization" not in factory.calls[0]["headers"]


@pytest.mark.asyncio
async def test_provider_rejection_maps_to_key_rejected(monkeypatch):
    monkeypatch.setattr(service.httpx, "AsyncClient", _Factory(status=401))

    with pytest.raises(TranscriptionError) as exc:
        await transcribe(**_kwargs())

    assert exc.value.code == "KEY_REJECTED"
    assert exc.value.status == 502


@pytest.mark.asyncio
async def test_empty_transcript_is_not_reported_as_success(monkeypatch):
    monkeypatch.setattr(service.httpx, "AsyncClient", _Factory(payload={"text": "   "}))

    with pytest.raises(TranscriptionError) as exc:
        await transcribe(**_kwargs())

    assert exc.value.code == "EMPTY_TRANSCRIPT"


@pytest.mark.asyncio
async def test_invalid_base64_is_rejected_before_any_call(monkeypatch):
    factory = _Factory()
    monkeypatch.setattr(service.httpx, "AsyncClient", factory)

    with pytest.raises(TranscriptionError) as exc:
        await transcribe(**_kwargs(audio_base64="not base64!!"))

    assert exc.value.code == "INVALID_AUDIO"
    assert factory.calls == []


@pytest.mark.asyncio
async def test_size_cap_is_enforced(monkeypatch):
    monkeypatch.setattr(service, "MAX_AUDIO_BYTES", 4)
    with pytest.raises(TranscriptionError) as exc:
        await transcribe(**_kwargs())
    assert exc.value.code == "TOO_LARGE"


@pytest.mark.asyncio
async def test_unsupported_mime_is_rejected(monkeypatch):
    with pytest.raises(TranscriptionError) as exc:
        await transcribe(**_kwargs(mime_type="application/pdf"))
    assert exc.value.code == "UNSUPPORTED_MEDIA"
    assert exc.value.status == 415


@pytest.mark.asyncio
async def test_non_http_endpoint_is_refused(monkeypatch):
    with pytest.raises(TranscriptionError) as exc:
        await transcribe(**_kwargs(base_url="file:///etc/passwd"))
    assert exc.value.code == "CONFIG_ERROR"


@pytest.mark.asyncio
async def test_provider_timeout_is_reported(monkeypatch):
    factory = _Factory()
    factory.error = httpx.ReadTimeout("slow")
    monkeypatch.setattr(service.httpx, "AsyncClient", factory)

    with pytest.raises(TranscriptionError) as exc:
        await transcribe(**_kwargs())

    assert exc.value.code == "TIMEOUT"

def test_local_provider_runs_on_device_without_network(monkeypatch):
    """`local` must bypass the HTTP path entirely: no key, no endpoint."""
    import asyncio

    calls: dict = {}

    async def fake_local(**kwargs):
        calls.update(kwargs)
        return {
            "text": "hello from this machine",
            "provider": "local",
            "model": kwargs["model"],
            "language": "en",
            "durationMs": kwargs.get("duration_ms"),
        }

    monkeypatch.setattr(service, "transcribe_local", fake_local)

    result = asyncio.run(
        transcribe(
            audio_base64=base64.b64encode(b"RIFF....WAVE").decode(),
            mime_type="audio/wav",
            provider="local",
            base_url="",
            api_key=None,
            model="base.en",
            language="en-US",
            prompt="tickers: AAPL",
            duration_ms=1200,
        )
    )

    assert result["text"] == "hello from this machine"
    assert result["provider"] == "local"
    assert calls["extension"] == ".wav"  # mime drives the temp suffix
    assert calls["model"] == "base.en"
    assert calls["language"] == "en-US"
