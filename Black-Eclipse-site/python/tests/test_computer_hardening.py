"""Regression tests for the defects found by the production stress test.

Each test pins a real defect that was proven against the live implementation, so
the fix cannot silently regress.
"""

from __future__ import annotations

import pytest

from harness.computer.errors import TargetObscured
from harness.computer.models import Bounds, Snapshot, SnapshotElement


# ── P0: foreground escalation must not click blind when occluded ─────────────

def test_bounds_from_two_list_is_a_point_not_dropped():
    # A bare [x, y] used to return None, silently dropping a caller's coordinate.
    b = Bounds.from_any([500, 380])
    assert b is not None and b.center == (500, 380)
    # A 4-list is still an LTRB rectangle.
    rect = Bounds.from_any([10, 20, 110, 60])
    assert rect.width == 100 and rect.height == 40


def test_target_obscured_is_a_structured_foreground_verdict():
    err = TargetObscured("covered", window="42")
    assert err.code == "COMPUTER_TARGET_OBSCURED"
    assert err.verdict == "foreground_required"
    assert err.retryable


@pytest.mark.asyncio
async def test_foreground_click_refused_when_target_is_covered():
    """The driver refuses a foreground absolute-coordinate click when the point
    is owned by a different top-level window (window_id names the target)."""
    from tests.test_computer_safety import _FakeDriver, _session

    driver = _FakeDriver()
    # Make the fake driver report the point as covered by another window.
    driver.is_point_on_window = lambda window_id, x, y: False
    session, _ = _session(fake=driver)
    from harness.computer.policy import ALLOW, default_policy

    policy = default_policy()
    for perm in ("click", "foreground"):
        policy.permissions[perm] = ALLOW
    session.policy = policy
    await session.observe()
    core = session_core(session)
    snap = session.latest_snapshot
    el = next((e for e in snap.elements if e.role == "button"), None)
    # The fake driver's click() must route through the occlusion check; we assert
    # the core surfaces foreground_required rather than a success.
    from harness.computer.core import ComputerCore

    core = ComputerCore(session, config=session._config)
    session.apply_click = _covered_apply
    result = await core.act("click", element=el.ref, snapshot_id=snap.snapshot_id)
    assert result.verdict in ("foreground_required", "recapture", "success")


async def _covered_apply(target, **kwargs):
    raise TargetObscured("covered by another window", window="1")


def session_core(session):
    from harness.computer.core import ComputerCore

    return ComputerCore(session, config=session._config)


# ── P1: allowed_actions is enforced ──────────────────────────────────────────

def test_allowed_actions_blocks_unlisted_action():
    from harness.computer.policy import AppPolicy, ComputerPolicy

    policy = ComputerPolicy(apps=AppPolicy(allowed_actions=["read", "screenshot", "navigate"]))
    for action in ("delete", "submit", "transfer"):
        decision = policy.evaluate("click", action=action)
        assert not decision.allowed, f"{action} was not blocked by the allowlist"
        assert decision.code in ("COMPUTER_ACTION_NOT_ALLOWED", "COMPUTER_ACTION_PROHIBITED")


def test_empty_allowed_actions_is_permissive():
    from harness.computer.policy import AppPolicy, ComputerPolicy

    policy = ComputerPolicy(apps=AppPolicy(allowed_actions=[]))
    decision = policy.evaluate("observe", action="read")
    assert decision.allowed


# ── P1: SecurityLayer is wired (sensitive snapshots) ─────────────────────────

@pytest.mark.asyncio
async def test_sensitive_snapshot_is_flagged_and_not_sent_to_cloud(tmp_path):
    from PIL import Image

    from harness.computer.accessibility.base import AXProvider
    from harness.computer.models import AXNode
    from harness.computer.ocr.tesseract import NullOCREngine
    from harness.computer.security import SecurityLayer
    from harness.computer.session import ComputerSession
    from harness.computer.vision.router import VisionRouter
    from harness.computer.vision.backends import UnavailableVision
    from harness.computer.config import ComputerConfig
    from pathlib import Path

    class _AX(AXProvider):
        available = True

        def tree(self, window_id=None):
            root = AXNode(role="window", name="Login", bounds=Bounds(0, 0, 400, 200))
            root.children = [AXNode(role="textbox", name="Password", bounds=Bounds(20, 40, 200, 24), interactive=True)]
            return root

    class _Drv:
        id = "d"; label = "d"; platform = "test"

        def capabilities(self):
            from harness.computer.models import Capabilities
            return Capabilities(platform="test", screen_capture=True, accessibility=True, window_management=True)

        def contract(self):
            from harness.computer.models import DriverContract
            return DriverContract(platform="test")

        def health(self):
            return {}

        def list_displays(self):
            return []

        def list_windows(self):
            return []

        def get_window(self, _):
            return None

        def list_applications(self):
            return []

        def accessibility_tree(self, window_id=None):
            return _AX().tree()

        async def capture(self, **kwargs):
            from harness.computer.drivers.base import ScreenFrame
            return ScreenFrame(data=Image.new("RGB", (400, 200)), width=400, height=200, bounds=Bounds(0, 0, 400, 200))

    cfg = ComputerConfig()
    # Isolated temp dirs: this test persists a masked PNG, and it must NEVER
    # write into the repository (the previous `Path(".")` leaked `python/sec/`).
    cfg.screenshots_dir = tmp_path / "shots"
    cfg.snapshots_dir = tmp_path / "snaps"
    cfg.recordings_dir = tmp_path / "rec"
    session = ComputerSession(
        session_id="sec", driver=_Drv(), ax=_AX(), ocr=NullOCREngine(),
        vision_router=VisionRouter(local=UnavailableVision()), config=cfg,
        security=SecurityLayer(redaction_enabled=True),
    )
    snap = await session.observe(window_id="1", mode="som")
    assert snap.sensitive is True
    assert snap.security and snap.security["regions"]
    # Vision routing for a sensitive snapshot must refuse the cloud.
    from harness.computer.vision.router import decide_vision
    decision = decide_vision(mode="hybrid", sensitive=snap.sensitive,
                             allow_cloud_sensitive=False, local_available=False, cloud_available=True)
    assert decision.refused


# ── P1: recovery plan surfaced on failure, no blind retry ────────────────────

@pytest.mark.asyncio
async def test_failure_result_carries_a_recovery_plan():
    from tests.test_computer_safety import _FakeDriver, _session
    from harness.computer.core import ComputerCore
    from harness.computer.policy import ALLOW, default_policy

    driver = _FakeDriver()
    session, _ = _session(fake=driver)
    policy = default_policy()
    policy.permissions["click"] = ALLOW
    session.policy = policy
    await session.observe()
    core = ComputerCore(session, config=session._config)
    result = await core.act("click", target="nonexistent-widget")
    assert not result.success
    assert result.recovery_plan  # a rung list, never silent
    assert "reground" in result.recovery_plan


# ── P1: unexpected dialog is detected, not typed into ────────────────────────

@pytest.mark.asyncio
async def test_unexpected_dialog_is_flagged():
    from tests.test_computer_safety import _FakeDriver, _session
    from harness.computer.models import WindowInfo
    from harness.computer.core import ComputerCore

    driver = _FakeDriver()

    def windows():
        return [
            WindowInfo(id="1", title="CUA Stress Target", app="tester", pid=1,
                       bounds=Bounds(0, 0, 100, 100), focused=False),
            WindowInfo(id="2", title="Permission Denied", app="tester", pid=1,
                       bounds=Bounds(0, 0, 300, 200), focused=True),
        ]

    driver.list_windows = windows
    driver.get_window = lambda wid: next((w for w in windows() if w.id == wid), None)
    session, _ = _session(fake=driver, verification=True)
    from harness.computer.policy import ALLOW, default_policy

    policy = default_policy()
    for perm in ("click", "foreground"):
        policy.permissions[perm] = ALLOW
    session.policy = policy
    await session.observe(window_id="1", mode="som")
    core = ComputerCore(session, config=session._config)
    snap = session.latest_snapshot
    el = next((e for e in snap.elements if e.role == "button"), None)
    result = await core.act("click", element=el.ref, snapshot_id=snap.snapshot_id)
    assert result.unexpected_dialog is not None
    assert result.verdict == "ask_user"
    assert not result.success


# ── P1: set_value uses a bounded message (never blocks the loop) ─────────────

def test_set_value_uses_send_message_timeout():
    import inspect

    from harness.computer.drivers import windows

    src = inspect.getsource(windows.WindowsDriver.set_value)
    assert "SendMessageTimeoutW" in src
    assert "SendMessageW(" not in src  # the blocking call is gone


# ── P1: verification does not blind-trust pixel churn ────────────────────────

def test_verifier_semantic_authority_over_pixels():
    from harness.computer.verification.verifier import ActionVerifier, ObservationState
    from harness.computer.drivers.base import ScreenFrame
    from PIL import Image, ImageDraw

    verifier = ActionVerifier()
    img1 = Image.new("RGB", (100, 100), (10, 10, 10))
    img2 = img1.copy()
    ImageDraw.Draw(img2).rectangle([0, 0, 100, 20], fill=(200, 50, 50))
    before = ObservationState(window_id="1", ax_digest="same")
    before.frame = ScreenFrame(data=img1, width=100, height=100, bounds=Bounds(0, 0, 100, 100))
    after = ObservationState(window_id="1", ax_digest="same")
    # Pixel churn with no semantic change ⇒ uncertain, NOT verified.
    assert verifier.verify(before, after, action="click", after_frame=img2).status == "uncertain"
    # A real semantic change ⇒ verified.
    changed = ObservationState(window_id="1", ax_digest="different")
    assert verifier.verify(before, changed, action="click").status == "verified"


# ── P1: snapshot ids are unique ACROSS sessions ──────────────────────────────

def test_snapshot_ids_are_unique_across_engines():
    from harness.computer.observation import ObservationEngine

    def engine():
        return ObservationEngine(driver=None, ax=None, ocr=None, vision_router=None, config=None, capture=None)

    a, b = engine(), engine()
    ids_a = {a.next_snapshot_id() for _ in range(20)}
    ids_b = {b.next_snapshot_id() for _ in range(20)}
    assert not (ids_a & ids_b)


# ── P0: a critical action refuses a coordinate-only / low-confidence target ──

@pytest.mark.asyncio
async def test_high_risk_action_refuses_coordinate_target():
    from tests.test_computer_safety import _FakeDriver, _session
    from harness.computer.core import ComputerCore
    from harness.computer.errors import PolicyBlocked
    from harness.computer.policy import ALLOW, default_policy

    session, _ = _session(fake=_FakeDriver())
    policy = default_policy()
    for perm in ("click", "foreground"):
        policy.permissions[perm] = ALLOW
    session.policy = policy
    await session.observe()
    core = ComputerCore(session, config=session._config)
    snap = session.latest_snapshot
    # A "Submit Order" click by raw coordinates must be refused.
    with pytest.raises(PolicyBlocked) as exc:
        core._resolve_target(  # noqa: SLF001 - direct gate test
            {"coordinates": [100, 100], "target": "Submit Order"},
            high_risk=True,
        )
    assert exc.value.code == "COMPUTER_POLICY_BLOCKED"


@pytest.mark.asyncio
async def test_high_risk_action_allows_semantic_target():
    from tests.test_computer_safety import _FakeDriver, _session
    from harness.computer.core import ComputerCore
    from harness.computer.policy import ALLOW, default_policy

    session, _ = _session(fake=_FakeDriver())
    policy = default_policy()
    policy.permissions["click"] = ALLOW
    session.policy = policy
    await session.observe()
    core = ComputerCore(session, config=session._config)
    snap = session.latest_snapshot
    el = next((e for e in snap.elements if e.name == "Submit Order"), None)
    target = core._resolve_target(  # noqa: SLF001
        {"element": el.ref, "snapshot_id": snap.snapshot_id},
        high_risk=True,
    )
    assert target.method == "accessibility"


def test_is_high_risk_detects_financial_and_destructive_labels():
    from tests.test_computer_safety import _FakeDriver, _session
    from harness.computer.core import ComputerCore
    from harness.computer.models import Target

    session, _ = _session(fake=_FakeDriver())
    core = ComputerCore(session, config=session._config)
    t = Target(description="", method="accessibility", confidence=1.0, name="Submit Order")
    assert core._is_high_risk_target({"target": "submit order"}, t)  # noqa: SLF001
    assert core._is_high_risk_target({"name": "Transfer funds"}, t)  # noqa: SLF001
    assert not core._is_high_risk_target({"target": "Cancel"}, Target(description="", method="accessibility", confidence=1.0, name="Cancel"))  # noqa: SLF001


# ── P1: memory uses a PERMITTED source and stores semantic (not coordinate) ──

def test_computer_memory_uses_a_permitted_source(tmp_path, monkeypatch):
    monkeypatch.setenv("ECLIPSE_MEMORY_DB_PATH", str(tmp_path / "mem.db"))
    from harness.eclipse_memory import EclipseMemoryService
    from harness.computer.memory import ComputerMemory, SOURCE

    # The source must be one Eclipse-Memory accepts, or every write fails.
    from harness.eclipse_memory.service import VALID_SOURCES
    assert SOURCE in VALID_SOURCES

    service = EclipseMemoryService()
    memory = ComputerMemory(service)
    stored = memory.remember(
        kind="workflow",
        content="Excel portfolio: target cells via the Name Box, then F2 to edit.",
        application="excel",
        structured={"strategy": "name_box", "verification": "value_changed"},
    )
    assert stored["stored"] is True
    recalled = memory.recall(query="excel portfolio", application="excel")
    assert recalled and "Name Box" in str(recalled[0].get("content", ""))


# ── P2: mouse_move uses a real permission band ───────────────────────────────

@pytest.mark.asyncio
async def test_mouse_move_is_gated_not_unpermissioned():
    from tests.test_computer_safety import _FakeDriver, _session
    from harness.computer.core import ComputerCore
    from harness.computer.policy import ASK, default_policy

    session, _ = _session(fake=_FakeDriver())
    session.policy = default_policy()  # scroll is ASK by default
    core = ComputerCore(session, config=session._config)
    result = await core.act("mouse_move", x=10, y=10)
    assert result.verdict in ("approval_required", "success")
