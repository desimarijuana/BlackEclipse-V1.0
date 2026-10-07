"""Browser hardening unit tests (Phase H) — the offline half.

The failure-path integration tests live in `test_browser_hardening.py` behind a
real-Chromium gate. This module pins the pure logic that needs no browser: frame
target parsing/scoping, the device-descriptor resolver's honesty, and that the
context-op overrides are recorded on a session.
"""

from __future__ import annotations

from harness.browser.devices import device_descriptor, known_device_names
from harness.browser.resolver import Resolver, Target


# ── Frame targets (H.1) ──────────────────────────────────────────────────────

def test_target_parses_frame_selector():
    target = Target.parse({"frame": "#outer >> #inner", "role": "button", "name": "Go"})
    assert target.frame == "#outer >> #inner"
    assert "frame=" in target.describe()


def test_target_parses_frame_aliases():
    assert Target.parse({"frameSelector": "#f"}).frame == "#f"
    assert Target.parse({"frameLocator": "#f"}).frame == "#f"


class _FakeScope:
    """Records the chained frame_locator calls and returns a locator stub."""

    def __init__(self) -> None:
        self.chained: list[str] = []

    def frame_locator(self, selector: str) -> "_FakeScope":
        self.chained.append(selector)
        return self

    def locator(self, selector: str):
        return ("locator", self.chained[-1] if self.chained else selector)


def test_resolver_scopes_into_a_single_frame():
    scope = _FakeScope()
    resolver = Resolver(snapshot_engine=None)
    found = resolver._locator_for(scope, Target.parse({"frame": "#frame", "css": "#x"}))  # noqa: SLF001
    assert found is not None
    assert scope.chained == ["#frame"]


def test_resolver_chains_nested_frames():
    scope = _FakeScope()
    resolver = Resolver(snapshot_engine=None)
    resolver._locator_for(scope, Target.parse({"frame": "#outer >> #inner", "css": "#x"}))  # noqa: SLF001
    assert scope.chained == ["#outer", "#inner"]


def test_resolver_without_frame_uses_the_page():
    scope = _FakeScope()
    resolver = Resolver(snapshot_engine=None)
    resolver._locator_for(scope, Target.parse({"css": "#x"}))  # noqa: SLF001
    assert scope.chained == []


# ── Device descriptors (H.3) ─────────────────────────────────────────────────

class _FakePlaywright:
    def __init__(self, devices):
        self.devices = devices


def test_device_descriptor_reads_the_instance_catalog():
    pw = _FakePlaywright({"iPhone 13": {"viewport": {"width": 390, "height": 844}, "user_agent": "ua"}})
    found = device_descriptor(pw, "iPhone 13")
    assert found is not None and found["viewport"]["width"] == 390
    assert known_device_names(pw) == ["iPhone 13"]


def test_device_descriptor_is_honest_when_unknown():
    pw = _FakePlaywright({"Pixel 5": {"viewport": {"width": 393, "height": 851}}})
    assert device_descriptor(pw, "iPhone 13") is None
    assert device_descriptor(None, "iPhone 13") is None
    assert device_descriptor(pw, "") is None


def test_known_device_names_unions_catalogs():
    pw = _FakePlaywright({"A": {}, "B": {}})
    assert known_device_names(pw) == ["A", "B"]


# ── Context ops record overrides (H.3) ───────────────────────────────────────

class _FakePage:
    def __init__(self) -> None:
        self.viewport = None

    async def set_viewport_size(self, size) -> None:
        self.viewport = size


class _FakeContextOpsSession:
    def __init__(self) -> None:
        self._page = _FakePage()
        self.viewport_override = None
        self.user_agent_override = None
        self.locale_override = None
        self.timezone_override = None
        self.emulated_device = None
        self.id = "bsess_x"

    def page(self):
        return self._page


async def test_set_viewport_records_override():
    from harness.browser import context_ops

    session = _FakeContextOpsSession()
    result = await context_ops.set_viewport(session, 480, 900)
    assert result == {"width": 480, "height": 900}
    assert session.viewport_override == {"width": 480, "height": 900}
    assert session._page.viewport == {"width": 480, "height": 900}
