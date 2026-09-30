"""Continuation Milestone 6 — live OSV supply-chain check at the spawn path.

Offline: the OSV client is injected with recorded responses, so no network call
runs in the suite. Proves the fail-closed/fail-open split, the cache, and that a
real executable is never queried.
"""

from __future__ import annotations

import pytest

from harness.mcp.supply_chain import (
    BLOCKED,
    CLEAN,
    UNKNOWN,
    OSV_QUERY_URL,
    SupplyChainChecker,
    ecosystem_for_runner,
    parse_package_spec,
)

# A recorded OSV malware response.
_MALWARE = {
    "vulns": [
        {
            "id": "MAL-2024-1234",
            "summary": "Malicious code in the package",
            "database_specific": {"type": "malware"},
        }
    ]
}
_CLEAN = {"vulns": []}
_ORDINARY_CVE = {
    "vulns": [{"id": "GHSA-xxxx", "summary": "A regular vulnerability"}],
}


def test_parse_package_spec_handles_scopes_and_versions():
    assert parse_package_spec("foo") == ("foo", None, None)
    assert parse_package_spec("foo@1.2.3") == ("foo", "1.2.3", None)
    assert parse_package_spec("@scope/name") == ("@scope/name", None, None)
    assert parse_package_spec("@scope/name@1.2.3") == ("@scope/name", "1.2.3", None)


def test_ecosystem_for_runner():
    assert ecosystem_for_runner("npx") == "npm"
    assert ecosystem_for_runner("uvx") == "PyPI"
    assert ecosystem_for_runner("/usr/bin/python") is None
    assert ecosystem_for_runner("node") is None


@pytest.mark.asyncio
async def test_confirmed_malware_advisory_blocks():
    async def fetch(url, payload):
        assert url == OSV_QUERY_URL
        return _MALWARE

    checker = SupplyChainChecker(fetcher=fetch)
    verdict = await checker.check("npx", ["-y", "evil-pkg"])
    assert verdict.code == BLOCKED and verdict.blocked
    assert verdict.advisory_ids == ["MAL-2024-1234"]


@pytest.mark.asyncio
async def test_ordinary_cve_is_not_a_malware_block():
    async def fetch(url, payload):
        return _ORDINARY_CVE

    verdict = await SupplyChainChecker(fetcher=fetch).check("npx", ["-y", "pkg"])
    assert verdict.code == CLEAN


@pytest.mark.asyncio
async def test_network_failure_fails_open_and_is_labelled():
    async def fetch(url, payload):
        raise TimeoutError("no network")

    verdict = await SupplyChainChecker(fetcher=fetch).check("npx", ["-y", "pkg"])
    assert verdict.code == UNKNOWN
    assert verdict.blocked is False
    assert "lookup failed" in (verdict.reason or "")


@pytest.mark.asyncio
async def test_a_non_package_runner_is_never_queried():
    async def fetch(url, payload):
        raise AssertionError("a real executable must not be queried")

    verdict = await SupplyChainChecker(fetcher=fetch).check("node", ["server.js"])
    assert verdict.code == CLEAN
    assert verdict.reason == "not a package runner"


@pytest.mark.asyncio
async def test_cache_prevents_a_second_query():
    calls = {"n": 0}

    async def fetch(url, payload):
        calls["n"] += 1
        return _CLEAN

    checker = SupplyChainChecker(fetcher=fetch, ttl_s=3600)
    first = await checker.check("npx", ["-y", "pkg"])
    second = await checker.check("npx", ["-y", "pkg"])
    assert calls["n"] == 1
    assert second.cached is True
    assert first.code == CLEAN


@pytest.mark.asyncio
async def test_network_failure_is_not_cached():
    calls = {"n": 0}

    async def fetch(url, payload):
        calls["n"] += 1
        raise TimeoutError("down")

    checker = SupplyChainChecker(fetcher=fetch, ttl_s=3600)
    await checker.check("npx", ["-y", "pkg"])
    await checker.check("npx", ["-y", "pkg"])
    # A failure is retried: not cached.
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_cache_expires_with_the_clock():
    calls = {"n": 0}
    t = {"now": 1000.0}

    async def fetch(url, payload):
        calls["n"] += 1
        return _CLEAN

    checker = SupplyChainChecker(fetcher=fetch, ttl_s=100, clock=lambda: t["now"])
    await checker.check("npx", ["-y", "pkg"])
    t["now"] += 101
    await checker.check("npx", ["-y", "pkg"])
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_screen_spawn_blocks_malware_and_allows_a_network_failure():
    from types import SimpleNamespace

    from harness.mcp.supply_chain import screen_spawn

    async def malware_fetch(url, payload):
        return _MALWARE

    async def down_fetch(url, payload):
        raise TimeoutError("down")

    import harness.mcp.supply_chain as sc
    from harness.mcp.supply_chain import SupplyChainChecker

    original = sc._CHECKER
    try:
        sc._CHECKER = SupplyChainChecker(fetcher=malware_fetch)
        blocked = await screen_spawn(
            SimpleNamespace(transport="stdio", command="npx"),
            SimpleNamespace(command="npx", args=["-y", "evil-pkg"]),
        )
        assert blocked is not None and "malware" in blocked.lower()

        sc._CHECKER = SupplyChainChecker(fetcher=down_fetch)
        allowed = await screen_spawn(
            SimpleNamespace(transport="stdio", command="npx"),
            SimpleNamespace(command="npx", args=["-y", "pkg"]),
        )
        assert allowed is None
    finally:
        sc._CHECKER = original
