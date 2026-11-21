"""Endpoint guard: no private/link-local endpoints, loopback only on purpose."""

from __future__ import annotations

import pytest

from harness.model_runtime import endpoint_guard as G
from harness.schemas import ModelSettings


@pytest.mark.parametrize("address", ["8.8.8.8", "1.1.1.1", "2606:4700:4700::1111"])
def test_public_literals_are_allowed(address):
    assert G.is_public_address(address) is True


@pytest.mark.parametrize("address", [
    "127.0.0.1", "10.0.0.5", "192.168.1.10", "172.16.0.1",
    "169.254.169.254", "0.0.0.0", "::1", "fe80::1", "224.0.0.1",
])
def test_private_loopback_link_local_and_metadata_are_refused(address):
    assert G.is_public_address(address) is False


def test_a_private_ip_literal_is_blocked_even_without_dns(monkeypatch):
    monkeypatch.delenv("BE_ENDPOINT_PINNING", raising=False)
    with pytest.raises(G.EndpointBlocked) as exc:
        G.resolve_public_endpoint("http://169.254.169.254/latest/meta-data")
    assert exc.value.code == "PRIVATE_ADDRESS"


def test_a_public_ip_literal_passes():
    resolved = G.resolve_public_endpoint("https://8.8.8.8/v1")
    assert resolved.addresses == ("8.8.8.8",)


def test_loopback_is_allowed_when_explicitly_local():
    resolved = G.resolve_public_endpoint("http://127.0.0.1:11434/v1", allow_private=True)
    assert resolved.port == 11434


def test_a_hostname_is_not_resolved_unless_pinning_is_on(monkeypatch):
    monkeypatch.delenv("BE_ENDPOINT_PINNING", raising=False)
    resolved = G.resolve_public_endpoint("https://api.example.com/v1")
    assert resolved.addresses == ()
    assert resolved.host == "api.example.com"


def test_a_hostname_that_resolves_privately_is_refused_when_pinning():
    with pytest.raises(G.EndpointBlocked) as exc:
        G.resolve_public_endpoint(
            "https://evil.example.com/v1", resolver=["10.0.0.7"])
    assert exc.value.code == "PRIVATE_RESOLUTION"


def test_a_hostname_that_resolves_publicly_passes():
    resolved = G.resolve_public_endpoint(
        "https://api.example.com/v1", resolver=["93.184.216.34"])
    assert resolved.addresses == ("93.184.216.34",)


def test_empty_host_and_bad_scheme_are_refused():
    for url, code in [
        ("", "EMPTY_URL"),
        ("ftp://example.com", "BAD_SCHEME"),
        ("http:///nohost", "NO_HOST"),
    ]:
        with pytest.raises(G.EndpointBlocked) as exc:
            G.resolve_public_endpoint(url)
        assert exc.value.code == code


def test_build_chat_model_refuses_a_metadata_endpoint():
    from harness.models import build_chat_model

    settings = ModelSettings.model_validate({
        "provider": "openai",
        "baseUrl": "http://169.254.169.254/v1",
        "apiKey": "sk-test",
        "model": "gpt-4o",
    })
    with pytest.raises(ValueError) as exc:
        build_chat_model(settings)
    assert "ENDPOINT_NOT_ALLOWED" in str(exc.value)
