"""Browser app-origin resolution + honest navigation causes (QA Round 1, Q4a/b).

The QA run saw `BROWSER_NAVIGATION_FAILED` while the hidden cause was a
transport failure, and misread it as a policy boundary. These pin the
classification and the origin resolver without needing Playwright.
"""

from __future__ import annotations

from harness.browser import app_origin


def test_classifies_common_transport_failures():
    assert "resolve" in app_origin.classify_navigation_error(
        Exception("net::ERR_NAME_NOT_RESOLVED at https://blackeclipse")
    )[0]
    assert "refused" in app_origin.classify_navigation_error(
        Exception("net::ERR_CONNECTION_REFUSED")
    )[0]
    assert "timed out" in app_origin.classify_navigation_error(
        Exception("Timeout 30000ms exceeded")
    )[0]


def test_unknown_failure_still_yields_a_plain_sentence():
    cause, hint = app_origin.classify_navigation_error(Exception("weird"))
    assert cause and hint


def test_origin_candidates_are_ordered_and_deduplicated(monkeypatch):
    monkeypatch.setenv("HARNESS_BROWSER_APP_ORIGIN", "http://127.0.0.1:3000")
    monkeypatch.setenv("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")
    monkeypatch.setenv("BE_CANONICAL_HOST", "blackeclipse")
    origins = app_origin.app_origins()
    assert origins[0] == "http://127.0.0.1:3000"
    assert origins.count("http://127.0.0.1:3000") == 1
    assert "https://blackeclipse" in origins
    assert "http://blackeclipse" in origins


def test_recognises_loopback_and_canonical_urls(monkeypatch):
    monkeypatch.setenv("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")
    monkeypatch.setenv("BE_CANONICAL_HOST", "blackeclipse")
    assert app_origin.is_app_url("http://127.0.0.1:3000/?tab=memory")
    assert app_origin.is_app_url("https://blackeclipse/?tab=memory")
    assert not app_origin.is_app_url("https://example.com/api")


def test_retarget_preserves_path_and_query():
    moved = app_origin.retarget(
        "http://127.0.0.1:3000/?tab=memory&sub=memory.reviews",
        "https://blackeclipse",
    )
    assert moved == "https://blackeclipse/?tab=memory&sub=memory.reviews"


def test_resolve_returns_the_first_reachable_origin(monkeypatch):
    monkeypatch.setenv("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")
    monkeypatch.delenv("HARNESS_BROWSER_APP_ORIGIN", raising=False)
    monkeypatch.setenv("BE_CANONICAL_HOST", "blackeclipse")

    def fake_probe(origin, timeout=1.5):
        return origin == "https://blackeclipse"

    monkeypatch.setattr(app_origin, "probe_origin", fake_probe)
    origin, tried = app_origin.resolve_app_origin()
    assert origin == "https://blackeclipse"
    assert any(item["origin"] == "http://127.0.0.1:3000" and not item["reachable"] for item in tried)
    assert tried[-1]["reachable"] is True


def test_resolve_reports_none_when_nothing_answers(monkeypatch):
    monkeypatch.setenv("HARNESS_CALLBACK_URL", "http://127.0.0.1:3000")
    monkeypatch.delenv("HARNESS_BROWSER_APP_ORIGIN", raising=False)
    monkeypatch.delenv("BE_CANONICAL_HOST", raising=False)
    monkeypatch.setattr(app_origin, "probe_origin", lambda origin, timeout=1.5: False)
    origin, tried = app_origin.resolve_app_origin()
    assert origin is None
    assert tried and all(not item["reachable"] for item in tried)
