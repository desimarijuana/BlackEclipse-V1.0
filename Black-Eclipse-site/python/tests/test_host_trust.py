"""Host-header trust boundary for the loopback operator surface.

A DNS-rebinding page makes the browser resolve the attacker's hostname to
127.0.0.1, so `request.client.host` is loopback while the request is
attacker-controlled. The Host header must also name loopback; these tests pin
that rule for both the operator dependency and the identity resolver.
"""

from starlette.requests import Request

from harness.deps import _host_header_is_loopback
from harness.security.identity import _is_loopback as identity_is_loopback


def _request(host: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"host", host.encode("ascii"))],
            "client": ("127.0.0.1", 54321),
        }
    )


def test_loopback_host_headers_are_accepted():
    for host in ("127.0.0.1:8765", "localhost:8765", "[::1]:8765", "testserver"):
        assert _host_header_is_loopback(_request(host)), host


def test_rebinding_host_headers_are_refused():
    for host in ("evil.example:8765", "evil.example", "10.0.0.5:8765", "127.0.0.1.evil.example"):
        assert not _host_header_is_loopback(_request(host)), host


def test_identity_loopback_requires_both_peer_and_host():
    assert identity_is_loopback(_request("127.0.0.1:8765"))
    assert not identity_is_loopback(_request("evil.example:8765"))
