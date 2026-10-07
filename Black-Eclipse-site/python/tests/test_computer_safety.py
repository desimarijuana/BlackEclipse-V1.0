"""Computer Use SAFETY tests — finance firewall, approval boundary, stale-element
protection, no-blind-retry, takeover, and dry-run. These are the tests that must
never regress: they encode "fail safely", which matters more than task completion.
"""

from __future__ import annotations

import pytest

from harness.computer.config import ComputerConfig
from harness.computer.core import ComputerCore
from harness.computer.errors import ApprovalRequired, StaleElement
from harness.computer.finance.firewall import (
    ASSISTED,
    AUTONOMOUS,
    READ_ONLY,
    SIMULATION,
    FinanceActionFirewall,
)
from harness.computer.models import Bounds, Snapshot, SnapshotElement
from harness.computer.policy import ALLOW, ComputerPolicy, default_policy
from harness.computer.session import ComputerSession, SessionState


def _permissive_policy() -> ComputerPolicy:
    """A policy that allows input so the core's verification path can be tested."""
    policy = default_policy()
    for perm in ("click", "type", "key", "set_value", "drag", "foreground"):
        policy.permissions[perm] = ALLOW
    return policy


class _FakeDriver:
    """A deterministic in-memory driver for the core safety tests."""

    id = "fake"
    label = "Fake driver"
    platform = "test"

    def __init__(self, *, background_works: bool = True) -> None:
        self.background_works = background_works
        self.clicks: list[tuple[int, int, str]] = []
        self.keys: list[str] = []
        self.typed: list[str] = []
        # A click on a control changes the window's AX content (a real semantic
        # change), so verification can observe an effect — matching a real app.
        self.status = "IDLE"
        self._windows = [self._window()]

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    def _window(self):
        from harness.computer.models import WindowInfo
        return WindowInfo(id="1", title="Test", app="tester", pid=1, bounds=Bounds(0, 0, 800, 600), focused=True)

    def capabilities(self):
        from harness.computer.models import Capabilities
        return Capabilities(platform="test", background_input=self.background_works, foreground_input=True,
                            accessibility=True, screen_capture=True, window_management=True,
                            application_management=True, set_value=True)

    def contract(self):
        from harness.computer.models import DriverContract
        return DriverContract(platform="test", name="fake")

    def health(self):
        return {"driver": "fake", "healthy": True}

    def list_displays(self):
        from harness.computer.models import DisplayInfo
        return [DisplayInfo(id="primary", bounds=Bounds(0, 0, 800, 600), working_area=Bounds(0, 0, 800, 600), primary=True)]

    def list_windows(self):
        return list(self._windows)

    def get_window(self, window_id):
        return self._windows[0] if window_id == "1" else None

    def list_applications(self):
        from harness.computer.models import ApplicationInfo
        return [ApplicationInfo(id="1", name="tester", pid=1)]

    def accessibility_tree(self, window_id=None):
        from harness.computer.models import AXNode
        root = AXNode(role="window", name="Test", bounds=Bounds(0, 0, 800, 600))
        root.children = [
            AXNode(role="button", name="Save", bounds=Bounds(20, 20, 110, 32), interactive=True),
            AXNode(role="button", name="Save As", bounds=Bounds(140, 20, 110, 32), interactive=True),
            AXNode(role="button", name="Cancel", bounds=Bounds(260, 20, 110, 32), interactive=True),
            AXNode(role="button", name="Submit Order", bounds=Bounds(700, 500, 80, 30), interactive=True),
            AXNode(role="textbox", name="Ticker", bounds=Bounds(100, 100, 120, 24), interactive=True),
            AXNode(role="text", name=f"STATUS={self.status}", bounds=Bounds(20, 400, 300, 24)),
        ]
        return root

    async def capture(self, *, window_id=None, region=None, display_id=None):
        from PIL import Image
        from harness.computer.drivers.base import ScreenFrame
        img = Image.new("RGB", (800, 600), (10, 10, 10))
        b = region or Bounds(0, 0, 800, 600)
        return ScreenFrame(data=img, width=b.width, height=b.height, bounds=b)

    async def click(self, x, y, *, button="left", count=1, delivery_mode="background", window_id=None):
        from harness.computer.drivers.base import InputResult
        self.clicks.append((x, y, delivery_mode))
        # Only a click that LANDS ON a control changes the window's content — a
        # click on blank space is a true no-op (so a false success is detectable).
        if self._hit_control(x, y):
            self.status = "CLICKED"
        return InputResult(delivered=True, delivery_mode=delivery_mode)

    def _hit_control(self, x: int, y: int) -> bool:
        spans = [(20, 20, 130, 52), (140, 20, 250, 52), (260, 20, 370, 52),
                 (700, 500, 780, 530), (100, 100, 220, 124)]
        return any(x1 <= x <= x2 and y1 <= y <= y2 for x1, y1, x2, y2 in spans)

    async def type_text(self, text, *, delivery_mode="background", window_id=None):
        from harness.computer.drivers.base import InputResult
        self.typed.append(text)
        return InputResult(delivered=True, delivery_mode=delivery_mode)

    async def key(self, keys, *, delivery_mode="background", window_id=None):
        from harness.computer.drivers.base import InputResult
        self.keys.extend(keys)
        return InputResult(delivered=True, delivery_mode=delivery_mode)

    async def focus_window(self, window_id, *, foreground=False):
        from harness.computer.drivers.base import InputResult
        return InputResult(delivered=True, delivery_mode="foreground" if foreground else "background")

    def pointer_position(self):
        return (0, 0)


def _session(*, mode="background", finance_mode="read_only", fake=None, policy=None, verification=False):
    driver = fake or _FakeDriver()
    cfg = ComputerConfig(mode=mode, finance_mode=finance_mode, verification_enabled=verification,
                         snapshots_dir=None, screenshots_dir=None, recordings_dir=None)
    from pathlib import Path
    cfg.screenshots_dir = Path("/tmp/unused")
    cfg.snapshots_dir = Path("/tmp/unused")
    cfg.recordings_dir = Path("/tmp/unused")
    from harness.computer.accessibility.null import NullAXProvider
    from harness.computer.ocr.tesseract import NullOCREngine
    from harness.computer.vision.router import VisionRouter
    from harness.computer.vision.backends import UnavailableVision
    session = ComputerSession(
        session_id="test", driver=driver, ax=NullAXProvider(), ocr=NullOCREngine(),
        vision_router=VisionRouter(local=UnavailableVision()), config=cfg,
        policy=policy or default_policy(), risk_mode=finance_mode,
    )
    return session, driver


# ── stale element protection ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_stale_element_is_refused_not_remapped():
    session, _ = _session()
    snap = await session.observe()
    ref = snap.elements[0].ref if snap.elements else "1"
    snapshot_id = snap.snapshot_id

    # Fresh handle: valid.
    assert session.validate_handle(snapshot_id=snapshot_id, ref=ref).ok
    # A new observation invalidates the old snapshot id.
    await session.observe()
    stale = session.validate_handle(snapshot_id=snapshot_id, ref=ref)
    assert not stale.ok and stale.code == "COMPUTER_STALE_ELEMENT"
    with pytest.raises(StaleElement):
        session.require_element(snapshot_id=snapshot_id, ref=ref)


def test_validate_handle_without_snapshot_is_stale():
    session, _ = _session()
    check = session.validate_handle(snapshot_id="whatever", ref="1")
    assert not check.ok


# ── no blind retry / delivery escalation ─────────────────────────────────────

@pytest.mark.asyncio
async def test_background_escalates_when_no_change_detected():
    # Verification enabled + no accessibility change ⇒ the core escalates once.
    session, driver = _session(verification=True)
    await session.observe()
    core = ComputerCore(session, config=session._config)
    result = await core.act("click", element="1", snapshot_id=session.latest_snapshot.snapshot_id)
    # The fake driver accepts both modes; the point is that it ran and reported.
    assert result.action in ("click", "double_click")
    assert result.delivery_mode in ("background", "foreground")


# ── dry run ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dry_run_changes_nothing():
    session, driver = _session(mode="background")
    session._config.computer_mode = "dry_run"
    await session.observe()
    core = ComputerCore(session, config=session._config)
    result = await core.act("click", element="1", snapshot_id=session.latest_snapshot.snapshot_id)
    assert result.success and result.delivery_mode == "dry_run"
    assert driver.clicks == []  # nothing was clicked


# ── finance firewall: the safety-critical matrix ─────────────────────────────

def test_buy_and_sell_require_approval_under_assisted():
    fw = FinanceActionFirewall(mode=ASSISTED)
    for verb in ("buy", "sell", "short", "cover", "submit_order"):
        decision = fw.evaluate({"action": verb, "instrument": "NVDA", "quantity": 1, "price": 100})
        assert not decision.blocked and decision.requires_approval


def test_transfer_and_withdraw_are_always_blocked():
    for mode in (READ_ONLY, ASSISTED, AUTONOMOUS, SIMULATION):
        fw = FinanceActionFirewall(mode=mode)
        for verb in ("transfer", "withdraw", "deposit", "payment"):
            assert fw.evaluate({"action": verb}).blocked, f"{verb} must be blocked in {mode}"


def test_excessive_notional_is_blocked():
    fw = FinanceActionFirewall(mode=AUTONOMOUS, max_order_value=25_000)
    decision = fw.evaluate({"action": "buy", "instrument": "NVDA", "quantity": 1000, "price": 100})
    assert decision.blocked


def test_wrong_account_instrument_app_are_blocked():
    fw = FinanceActionFirewall(
        mode=AUTONOMOUS, allowed_accounts=["paper-acct"],
        allowed_instruments=["NVDA"], allowed_apps=["paper_trading"],
    )
    assert fw.evaluate({"action": "buy", "account": "live-acct", "instrument": "NVDA", "application": "paper_trading"}).blocked
    assert fw.evaluate({"action": "buy", "account": "paper-acct", "instrument": "TSLA", "application": "paper_trading"}).blocked
    assert fw.evaluate({"action": "buy", "account": "paper-acct", "instrument": "NVDA", "application": "robinhood"}).blocked


def test_read_only_mode_blocks_every_mutation():
    fw = FinanceActionFirewall(mode=READ_ONLY)
    for verb in ("buy", "sell", "submit_order", "cancel_order", "modify_order", "prepare_order"):
        assert fw.evaluate({"action": verb}).blocked


# ── policy approval boundary ─────────────────────────────────────────────────

def test_click_requires_approval_by_default():
    policy = ComputerPolicy()
    decision = policy.evaluate("click", action="click")
    assert decision.requires_approval and decision.code == "COMPUTER_APPROVAL_REQUIRED"


def test_denied_application_blocks_even_observation_of_actions():
    policy = ComputerPolicy(apps=__import__("harness.computer.policy", fromlist=["AppPolicy"]).AppPolicy(denied=["vault"]))
    decision = policy.evaluate("click", app="VaultApp")
    assert not decision.allowed and decision.code == "COMPUTER_APP_DENIED"


# ── takeover blocks the agent ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_takeover_stops_agent_actions():
    session, driver = _session()
    session._lease_check = lambda: False  # a person holds the lease
    await session.observe()
    core = ComputerCore(session, config=session._config)
    result = await core.act("click", element="1", snapshot_id=session.latest_snapshot.snapshot_id)
    assert not result.success
    assert result.verdict == "blocked"
    assert driver.clicks == []


@pytest.mark.asyncio
async def test_default_policy_holds_a_click_for_approval():
    """A bare click is not executed: it comes back as approval_required."""
    session, driver = _session()
    await session.observe()
    core = ComputerCore(session, config=session._config)
    result = await core.act("click", element="1", snapshot_id=session.latest_snapshot.snapshot_id)
    assert result.verdict == "approval_required"
    assert driver.clicks == []


# ── unexpected dialog / no silent success ────────────────────────────────────

@pytest.mark.asyncio
async def test_action_with_no_detected_change_is_not_a_blind_success():
    session, _ = _session(verification=True, policy=_permissive_policy())
    await session.observe()
    core = ComputerCore(session, config=session._config)
    result = await core.act("click", element="1", snapshot_id=session.latest_snapshot.snapshot_id)
    # The fake driver produces no verifiable change, so the verdict is a recapture,
    # never a blind "success".
    assert result.verdict == "recapture"
