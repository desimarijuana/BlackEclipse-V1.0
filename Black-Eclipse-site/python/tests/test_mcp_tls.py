"""Phase 6 Milestone 3 — TLS/mTLS client construction (offline).

The client's `_client_cert_args` is pure; a missing file must fail fast with a
server-scoped message.
"""

from __future__ import annotations

import os
import sys

import pytest

from harness.mcp.client import MCPConnection, MCPStartupError
from harness.mcp.config import MCPServerConfig


def _conn(**overrides) -> MCPConnection:
    data = dict(id="r", transport="http", url="https://api.example.com/mcp")
    data.update(overrides)
    return MCPConnection(MCPServerConfig(**data))


def test_combined_pem_client_cert(tmp_path):
    pem = tmp_path / "combined.pem"
    pem.write_text("-----BEGIN CERTIFICATE-----\n", encoding="utf-8")
    conn = _conn(client_cert=str(pem))
    assert conn._client_cert_args() == str(pem)


def test_client_cert_key_pair(tmp_path):
    cert = tmp_path / "c.pem"
    key = tmp_path / "k.pem"
    cert.write_text("c", encoding="utf-8")
    key.write_text("k", encoding="utf-8")
    conn = _conn(client_cert=str(cert), client_key=str(key))
    assert conn._client_cert_args() == (str(cert), str(key))


def test_client_cert_triple(tmp_path):
    cert = tmp_path / "c.pem"
    cert.write_text("c", encoding="utf-8")
    conn = _conn(client_cert=str(cert), client_key=[str(cert), "keydata", "passphrase"])
    assert conn._client_cert_args() == (str(cert), "keydata", "passphrase")


def test_missing_client_cert_fails_fast(tmp_path):
    conn = _conn(client_cert=str(tmp_path / "missing.pem"))
    with pytest.raises(MCPStartupError) as exc:
        conn._client_cert_args()
    assert exc.value.code == "mcp_tls_error"


def test_missing_ca_bundle_fails_fast_on_client_build(tmp_path):
    conn = _conn(ssl_verify=str(tmp_path / "nope.pem"))
    with pytest.raises(MCPStartupError) as exc:
        conn._http_client({})
    assert exc.value.code == "mcp_tls_error"
