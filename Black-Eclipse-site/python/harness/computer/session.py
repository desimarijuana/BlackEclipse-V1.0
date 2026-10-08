"""One ComputerSession — the first-class desktop-control object.

Tracks identity (session_id, agent_id, user_id, machine_id, display_state,
active_application, windows, permissions, risk_mode, current snapshot/target,
action history) and owns the deterministic lifecycle. A session holds the only
reference to a live `ComputerDriver` and the per-session engines.

The snapshot cache is GENERATIONAL: every observation increments a generation and
mints a new `snapshot_id`. An element handle is only valid against the snapshot
it came from — a changed generation, window or identity is `STALE_ELEMENT`, and
the model must re-capture. That is what prevents "click element 7" from silently
hitting a different control after the UI moved.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from ..persistence import now_iso
from .actions import KeyboardEngine, MouseEngine, ValueSetter
from .errors import StaleElement
from .grounding.grounder import Grounder
from .grounding.matching import GroundingQuery
from .models import (
    ActionResult,
    Bounds,
    Capabilities,
    Snapshot,
    Target,
    WindowInfo,
)
from .observation import ObservationEngine, ax_digest as ax_digest_of
from .recording import SessionRecorder
from .screenshots.capture import ScreenCapture, frame_digest
from .screenshots.diff import ScreenDiff
from .verification.verifier import ActionVerifier, ObservationState
from .windows.manager import WindowManager
from .applications.manager import ApplicationManager
from .applications.registry import AdapterRegistry, build_adapter_registry


class SessionState(str, Enum):
    CREATING = "CREATING"
    READY = "READY"
    OBSERVING = "OBSERVING"
    ACTING = "ACTING"
    PAUSED = "PAUSED"
    HUMAN_REQUIRED = "HUMAN_REQUIRED"
    FAILED = "FAILED"
    TERMINATED = "TERMINATED"

    @property
    def terminal(self) -> bool:
        return self in (SessionState.TERMINATED, SessionState.FAILED)


@dataclass
class StaleCheck:
    ok: bool
    reason: str = ""
    code: str = "OK"


class ComputerSession:
    def __init__(
        self,
        *,
        session_id: str,
        driver: Any,
        ax: Any,
        ocr: Any,
        vision_router: Any,
        config: Any,
        store: Any = None,
        telemetry: Any = None,
        agent_id: Optional[str] = None,
        user_id: Optional[str] = None,
        task_id: Optional[str] = None,
        run_id: Optional[str] = None,
        machine_id: str = "",
        policy: Any = None,
        risk_mode: str = "read_only",
        bus: Any = None,
        security: Any = None,
        firewall: Any = None,
    ) -> None:
        self.id = session_id
        self.driver = driver
        self.ax = ax
        self.ocr = ocr
        self.vision_router = vision_router
        self._config = config
        self.store = store
        self.telemetry = telemetry
        self.agent_id = agent_id
        self.user_id = user_id
        self.task_id = task_id
        self.run_id = run_id
        self.machine_id = machine_id
        self.policy = policy
        self.risk_mode = risk_mode
        self.bus = bus

        self.state = SessionState.CREATING
        self.created_at = time.time()
        self.last_activity = time.time()
        self.focus_before_action: Optional[str] = None
        # Monotonic count of actions STARTED, for the hard `max_actions` ceiling.
        self.actions_started = 0
        # Whether this session drives its OWN desktop (isolated) or the shared one.
        self._isolated = False

        self.windows = WindowManager(driver)
        self.applications = ApplicationManager(driver)
        self.adapters: AdapterRegistry = build_adapter_registry()
        self.capture = ScreenCapture(driver=driver, screenshots_dir=config.screenshots_dir)
        self.mouse = MouseEngine(driver)
        self.keyboard = KeyboardEngine(driver)
        self.value_setter = ValueSetter(driver=driver, keyboard=self.keyboard, mouse=self.mouse)
        self.security = security
        self.firewall = firewall
        self.observation = ObservationEngine(
            driver=driver, ax=ax, ocr=ocr, vision_router=vision_router, config=config,
            capture=self.capture, security=security,
        )
        self.grounder = Grounder(min_confidence=config.grounding_min_confidence)
        self.verifier = ActionVerifier(enabled=config.verification_enabled)
        self.diff = ScreenDiff()

        self._latest_snapshot: Optional[Snapshot] = None
        self.action_history: list[dict[str, Any]] = []
        self.current_task: Optional[str] = None
        self.recorder = SessionRecorder(
            enabled=config.recording_enabled, screenshots=config.recording_screenshots,
            recordings_dir=config.recordings_dir, session_id=session_id,
        )
        self._transition(SessionState.READY)

    # ── lifecycle ────────────────────────────────────────────────────────────

    def _transition(self, target: SessionState) -> None:
        self.state = target
        self._persist()

    def touch(self) -> None:
        self.last_activity = time.time()

    def _persist(self) -> None:
        if self.store is None:
            return
        try:
            windows = self.driver.list_windows() if self.driver.capabilities().window_management else []
            active = next((w for w in windows if w.focused), None)
            self.store.save_session({
                "id": self.id, "agentId": self.agent_id, "taskId": self.task_id,
                "runId": self.run_id, "userId": self.user_id, "machineId": self.machine_id,
                "driver": self.driver.id, "displayState": self._display_state(),
                "activeApp": (active.app if active else ""),
                "windowCount": len(windows), "riskMode": self.risk_mode,
                "status": self.state.value, "state": self.state.value,
                "createdAt": _iso(self.created_at), "lastActivity": now_iso(),
                "terminatedAt": now_iso() if self.state.terminal else None,
                "metadata": {"driver": self.driver.id},
            })
        except Exception:  # noqa: BLE001 - persistence must never break a session
            pass

    def _display_state(self) -> str:
        try:
            displays = self.driver.list_displays()
            return f"{len(displays)} display(s)"
        except Exception:  # noqa: BLE001
            return "unknown"

    def health_check(self) -> dict[str, Any]:
        health = {"sessionId": self.id, "state": self.state.value, "alive": not self.state.terminal}
        try:
            health["driver"] = self.driver.health()
        except Exception as exc:  # noqa: BLE001
            health["alive"] = False
            health["reason"] = str(exc)[:200]
        return health

    def capabilities(self) -> Capabilities:
        return self.driver.capabilities()

    def snapshot_summary(self) -> dict[str, Any]:
        return {
            "sessionId": self.id, "state": self.state.value, "driver": self.driver.id,
            "displayState": self._display_state(), "riskMode": self.risk_mode,
            "isolated": self._isolated,
            "currentSnapshot": self._latest_snapshot.snapshot_id if self._latest_snapshot else None,
            "currentTask": self.current_task, "actions": len(self.action_history),
            "createdAt": _iso(self.created_at),
        }

    # ── observation ──────────────────────────────────────────────────────────

    async def observe(
        self,
        *,
        window_id: Optional[str] = None,
        mode: Optional[str] = None,
        persist_image: bool = True,
    ) -> Snapshot:
        resolved_mode = (mode or self._config.observation_default_mode).lower()
        # The accessibility tree is per-window, so an AX/SOM observation with no
        # explicit window defaults to the FOCUSED window — otherwise a full-screen
        # capture would yield no numbered elements.
        if window_id is None and resolved_mode in ("ax", "som"):
            window_id = self._focused_window_id() or None
        self._transition(SessionState.OBSERVING)
        try:
            snapshot = await self.observation.observe(
                window_id=window_id, mode=resolved_mode, persist_image=persist_image, session_id=self.id,
            )
        finally:
            self._transition(SessionState.READY)
        # Application identity from the driver + adapter for this window.
        snapshot.application = self._application_for_window(window_id)
        self._latest_snapshot = snapshot
        self.recorder.record("observe", {"snapshot": snapshot.summary()})
        self.touch()
        return snapshot

    def _application_for_window(self, window_id: Optional[str]) -> str:
        if not window_id:
            return ""
        try:
            window = self.driver.get_window(window_id)
        except Exception:  # noqa: BLE001
            return ""
        if window is None:
            return ""
        adapter = self.adapters.select(app_name=window.app, title=window.title)
        return window.app or adapter.name

    @property
    def latest_snapshot(self) -> Optional[Snapshot]:
        return self._latest_snapshot

    def adapter_for(self, *, app_name: str = "", executable: str = "", title: str = "") -> Any:
        return self.adapters.select(app_name=app_name, executable=executable, title=title)

    # ── stale element validation ─────────────────────────────────────────────

    def lease_allows_agent(self) -> bool:
        """Whether the control lease currently permits the agent to act."""
        check = getattr(self, "_lease_check", None)
        return bool(check()) if callable(check) else True

    def acquire_desktop(self) -> bool:
        """Acquire the machine-wide desktop control lease (serialize sessions)."""
        acquire = getattr(self, "_broker_acquire", None)
        return bool(acquire()) if callable(acquire) else True

    def release_desktop(self) -> None:
        release = getattr(self, "_broker_release", None)
        if callable(release):
            try:
                release()
            except Exception:  # noqa: BLE001
                pass

    def validate_handle(self, *, snapshot_id: Optional[str], ref: Optional[str], identity: Optional[str] = None) -> StaleCheck:
        """Confirm a snapshot element handle is still valid.

        A missing snapshot, a different current snapshot, a missing element, or a
        changed identity ⇒ stale. The model must re-capture; we never remap.
        """
        if self._latest_snapshot is None:
            return StaleCheck(False, "there is no current snapshot; capture first", "COMPUTER_STALE_ELEMENT")
        if not snapshot_id or snapshot_id != self._latest_snapshot.snapshot_id:
            return StaleCheck(False, "the referenced snapshot is no longer current", "COMPUTER_STALE_ELEMENT")
        if ref is None:
            return StaleCheck(True)
        element = self._latest_snapshot.element(str(ref))
        if element is None:
            return StaleCheck(False, f"element #{ref} is not in the current snapshot", "COMPUTER_STALE_ELEMENT")
        if identity and element.identity != identity:
            return StaleCheck(False, f"element #{ref} changed since it was observed", "COMPUTER_STALE_ELEMENT")
        return StaleCheck(True)

    def require_element(self, *, snapshot_id: Optional[str], ref: str, identity: Optional[str] = None) -> Any:
        check = self.validate_handle(snapshot_id=snapshot_id, ref=ref, identity=identity)
        if not check.ok:
            raise StaleElement(check.reason, session_id=self.id, target=str(ref))
        return self._latest_snapshot.element(str(ref)) if self._latest_snapshot else None

    # ── grounding ────────────────────────────────────────────────────────────

    def ground(
        self,
        query: GroundingQuery | dict[str, Any],
        *,
        snapshot: Optional[Snapshot] = None,
        app_profile: Any = None,
        vision_lookup: Any = None,
        allow_coordinates: bool = False,
    ) -> Target:
        snap = snapshot or self._latest_snapshot
        if snap is None:
            from .errors import TargetNotFound  # noqa: PLC0415

            raise TargetNotFound("Eclipse needs an observation before it can find a target.", session_id=self.id)
        if isinstance(query, dict):
            query = GroundingQuery(**query)
        target = self.grounder.ground(
            query, snap, app_profile=app_profile, vision_lookup=vision_lookup,
            allow_coordinates=allow_coordinates,
        )
        if self.telemetry is not None:
            self.telemetry.record_grounding(target.confidence)
        return target

    # ── verification ─────────────────────────────────────────────────────────

    def _semantic_state(self, *, window_id: Optional[str] = None) -> dict[str, Any]:
        """A FRESH, lightweight semantic reading of the target (AX digest + title).

        Verification must not reuse the pre-action snapshot: doing so made every
        action look semantically unchanged and fall back to pixel noise. This
        re-reads the live accessibility tree WITHOUT minting a snapshot id or
        persisting an image.
        """
        ax_digest = ""
        title = ""
        try:
            tree = self.driver.accessibility_tree(window_id)
            ax_digest = ax_digest_of(tree)
        except Exception:  # noqa: BLE001
            ax_digest = ""
        if window_id:
            try:
                window = self.driver.get_window(window_id)
                title = window.title if window else ""
            except Exception:  # noqa: BLE001
                title = ""
        return {"ax_digest": ax_digest, "window_title": title}

    async def capture_state(self, *, window_id: Optional[str] = None) -> ObservationState:
        frame = None
        try:
            frame = await self.driver.capture(window_id=window_id)
        except Exception:  # noqa: BLE001 - a capture failure still yields a state
            frame = None
        focused = self._focused_window_id()
        state = self.verifier.capture(self._latest_snapshot, frame=frame, focused_window=focused)
        # Replace the stale snapshot digest with a FRESH live reading.
        fresh = self._semantic_state(window_id=window_id)
        if fresh["ax_digest"]:
            state.ax_digest = fresh["ax_digest"]
        if fresh["window_title"]:
            state.window_title = fresh["window_title"]
        state.screen_digest = _screen_fingerprint(state)
        return state

    def _read_after(self, before: ObservationState, *, window_id: Optional[str], after_frame: Any) -> ObservationState:
        after = self.verifier.capture(self._latest_snapshot, frame=after_frame, focused_window=self._focused_window_id())
        fresh = self._semantic_state(window_id=window_id)
        if fresh["ax_digest"]:
            after.ax_digest = fresh["ax_digest"]
        if fresh["window_title"]:
            after.window_title = fresh["window_title"]
        after.screen_digest = _screen_fingerprint(after)
        return after

    async def verify_action(
        self, before: ObservationState, *, action: str, expect: Optional[dict[str, Any]] = None,
        window_id: Optional[str] = None, settle_ms: int = 400,
    ) -> Any:
        """Verify an action's effect, SETTLING first.

        A background delivery is a posted message that the target processes
        asynchronously, so an immediate read can miss the effect and produce a
        false 'no change' (which then triggers a needless escalation). We poll
        the semantic state for a short, bounded settle window and stop as soon as
        a change appears.
        """
        import asyncio  # noqa: PLC0415

        after_frame = None
        try:
            after_frame = await self.driver.capture(window_id=window_id)
        except Exception:  # noqa: BLE001
            after_frame = None
        after = self._read_after(before, window_id=window_id, after_frame=after_frame)
        result = self.verifier.verify(before, after, action=action, expect=expect, after_frame=after_frame)

        deadline = time.monotonic() + max(0, settle_ms) / 1000
        while result.status == "uncertain" and time.monotonic() < deadline:
            await asyncio.sleep(0.05)
            after = self._read_after(before, window_id=window_id, after_frame=after_frame)
            result = self.verifier.verify(before, after, action=action, expect=expect, after_frame=after_frame)
            if result.status != "uncertain":
                break

        if self.telemetry is not None:
            self.telemetry.record_verification(1.0 if result.status == "verified" else 0.0)
        return result

    # Dialog-ish window classes/titles. Used only to DETECT an unexpected modal;
    # detection never dismisses or types into it.
    DIALOG_HINTS: tuple[str, ...] = (
        "dialog", "#32770", "messagebox", "popup", "alert", "confirm",
        "error", "warning", "permission", "are you sure", "update available",
        "save as", "open file", "sign in", "password required", "network error",
    )

    def detect_unexpected_dialog(self, *, baseline_window: str = "") -> Optional[dict[str, Any]]:
        """Detect a NEW dialog-ish window that is the current foreground.

        A modal that steals the foreground after an action is exactly the case
        where blind continued typing is dangerous. We report it; the agent (or a
        recovery rung) decides.
        """
        try:
            windows = self.driver.list_windows()
        except Exception:  # noqa: BLE001
            return None
        focused = next((w for w in windows if w.focused), None)
        if focused is None:
            return None
        # A dialog is a DIFFERENT top-level window than the one we were acting on.
        if baseline_window and focused.id == baseline_window:
            return None
        haystack = f"{focused.title} {focused.app}".lower()
        if any(hint in haystack for hint in self.DIALOG_HINTS):
            return {"windowId": focused.id, "title": focused.title, "application": focused.app}
        return None

    def detect_challenge(self, *, extra_text: str = "") -> Optional[dict[str, Any]]:
        """Detect a CAPTCHA / MFA / biometric challenge in the foreground UI.

        Scans the current foreground window title/app and, when supplied, the
        screen's OCR text. Detection never dismisses or types into the challenge —
        it is a stop signal for a person to take over (`computer_takeover`).
        """
        from .security import detect_challenge as _detect  # noqa: PLC0415

        titles: list[str] = []
        foreground_id = ""
        try:
            for window in self.driver.list_windows():
                if window.focused:
                    foreground_id = window.id
                    titles.append(f"{window.title} {window.app}")
        except Exception:  # noqa: BLE001
            pass
        marker = _detect(*titles, extra_text)
        if not marker:
            return None
        return {"marker": marker, "windowId": foreground_id}

    def _focused_window_id(self) -> str:
        try:
            for window in self.driver.list_windows():
                if window.focused:
                    return window.id
        except Exception:  # noqa: BLE001
            pass
        return ""

    # ── focus handling ───────────────────────────────────────────────────────

    def remember_focus(self) -> Optional[str]:
        self.focus_before_action = self._focused_window_id()
        return self.focus_before_action

    async def restore_focus(self) -> dict[str, Any]:
        """Restore the focus the user had before a foreground escalation."""
        if not self.focus_before_action:
            return {"restored": False}
        target = self.focus_before_action
        current = self._focused_window_id()
        if current == target:
            self.focus_before_action = None
            return {"restored": True, "windowId": target}
        try:
            await self.driver.focus_window(target, foreground=True)
            restored = self._focused_window_id() == target
        except Exception:  # noqa: BLE001
            restored = False
        self.focus_before_action = None
        return {"restored": restored, "windowId": target}

    # ── history + recording ──────────────────────────────────────────────────

    def record_action(self, entry: dict[str, Any]) -> None:
        entry.setdefault("at", now_iso())
        self.action_history.append(entry)
        if len(self.action_history) > 500:
            del self.action_history[0]

    def _record_action_db(self, entry: dict[str, Any]) -> None:
        if self.store is None:
            return
        try:
            self.store.save_action({"sessionId": self.id, "runId": self.run_id, **entry})
        except Exception:  # noqa: BLE001
            pass

    async def close(self) -> dict[str, Any]:
        self.release_desktop()
        self._transition(SessionState.TERMINATED)
        try:
            self.recorder.export()
        except Exception:  # noqa: BLE001
            pass
        return {"sessionId": self.id, "closed": True}

    # ── raw input application (used by the core dispatch) ────────────────────

    async def apply_click(
        self, target: Target, *, button: str = "left", count: int = 1,
        delivery_mode: str = "background", window_id: Optional[str] = None,
    ) -> Any:
        point = target.point
        if point is None:
            from .errors import ActionFailed  # noqa: PLC0415

            raise ActionFailed("The target has no position to click.", session_id=self.id)
        return await self.mouse.click(point[0], point[1], button=button, count=count,
                                      delivery_mode=delivery_mode,
                                      window_id=window_id or target.window_id or None)


def _screen_fingerprint(state: Any) -> str:
    """A stable digest folding the semantic content of an ObservationState, so a
    change in AX/title/window is reflected even without a pixel frame."""
    import hashlib  # noqa: PLC0415

    raw = f"{state.window_id}|{state.window_title}|{state.ax_digest}|{state.ocr_digest}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:20]


def _iso(ts: float) -> str:
    from datetime import datetime, timezone  # noqa: PLC0415

    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


__all__ = ["ComputerSession", "SessionState", "StaleCheck"]
