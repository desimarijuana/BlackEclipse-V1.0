"""The Computer Use core — the platform-independent orchestrator.

This is the ONE place the fundamental loop lives:

    OBSERVE → UNDERSTAND → PLAN → GROUND → AUTHORIZE → ACT → OBSERVE → VERIFY
            → (SUCCESS | RECOVER → REPLAN)

It is deliberately transport-agnostic: the tools, the HTTP router and the CLI all
call `ComputerCore`. `authorize()` decides (policy; the caller routes an ASK
through the shared approval store); `act()` performs an ALREADY-AUTHORIZED action
with background-first delivery, post-action capture, verification and recovery.

`dry_run` mode describes the action and changes nothing. A financial mutation is
routed through the `FinanceActionFirewall` BEFORE any UI action —
the core never performs an unrestricted financial mutation.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Optional

from .actions.mouse import point_of
from .errors import (
    ActionFailed,
    ApprovalRequired,
    ComputerError,
    PermissionDenied,
    PolicyBlocked,
    TargetNotFound,
)
from .finance.firewall import FinanceActionFirewall
from .grounding.matching import GroundingQuery
from .models import ActionResult, Bounds, Snapshot, Target
from .policy import PermissionDecision, classify_action
from .recovery import RecoveryEngine
from .session import ComputerSession
from .verification.verifier import ObservationState

# Delivery modes.
BACKGROUND = "background"
FOREGROUND = "foreground"


@dataclass
class ActionOutcome:
    """An internal wrapper: the ActionResult plus the recovery, if any."""

    result: ActionResult
    recovery: Optional[dict[str, Any]] = None

    def to_dict(self) -> dict[str, Any]:
        return {**self.result.to_dict(), "recovery": self.recovery}


class ComputerCore:
    def __init__(self, session: ComputerSession, *, config: Any = None) -> None:
        self.session = session
        self._config = config or session._config
        self.recovery = RecoveryEngine(
            max_attempts=self._config.recovery_max_attempts, enabled=self._config.recovery_enabled,
        )
        self.firewall = FinanceActionFirewall(
            mode=self._config.finance_mode, max_order_value=self._config.finance_max_order_value,
            prohibited_actions=list(self._config.prohibited_actions),
        )

    # ── delivery-mode helpers ────────────────────────────────────────────────

    @property
    def default_delivery(self) -> str:
        return BACKGROUND if self._config.mode == BACKGROUND else FOREGROUND

    def _escalation_allowed(self) -> bool:
        return bool(self.session.capabilities().foreground_input)

    # ── authorization ────────────────────────────────────────────────────────

    def authorize(self, permission: str, *, action: str = "", app: str = "") -> PermissionDecision:
        policy = self.session.policy
        if policy is None:
            # No policy ⇒ fail closed for anything that changes state.
            from .policy import DEFAULT_PERMISSIONS, ALLOW, ASK, DENY  # noqa: PLC0415

            default = DEFAULT_PERMISSIONS.get(permission, DENY)
            return PermissionDecision(
                permission, default, "no policy is attached to this session",
                allowed=default == ALLOW, requires_approval=default == ASK,
                risk=classify_action(action), code="COMPUTER_POLICY_DEFAULT",
            )
        return policy.evaluate(permission, action=action, app=app)

    def require_permission(self, permission: str, *, action: str = "", app: str = "") -> None:
        decision = self.authorize(permission, action=action, app=app)
        if decision.allowed:
            return
        if decision.requires_approval:
            raise ApprovalRequired(decision.reason, action=action or permission, app=app, metadata=decision.to_dict())
        if decision.code in ("COMPUTER_APP_DENIED", "COMPUTER_APP_NOT_ALLOWED", "COMPUTER_ACTION_PROHIBITED"):
            raise PolicyBlocked(decision.reason, action=action or permission, app=app, metadata=decision.to_dict())
        raise PermissionDenied(decision.reason, action=action or permission, app=app, metadata=decision.to_dict())

    def takeover_guard(self) -> None:
        """Refuse an agent action while a person holds the control lease."""
        check = getattr(self.session, "lease_allows_agent", None)
        if callable(check) and not check():
            raise PermissionDenied(
                "A person has taken control of this desktop session.",
                action="act", verdict="blocked",
            )

    # ── observation ──────────────────────────────────────────────────────────

    async def observe(self, *, window_id: Optional[str] = None, mode: Optional[str] = None, persist_image: bool = True) -> Snapshot:
        self.require_permission("observe", action="capture", app=self._app_name(window_id))
        return await self.session.observe(window_id=window_id, mode=mode, persist_image=persist_image)

    # ── the action dispatch ──────────────────────────────────────────────────

    async def act(self, action: str, **params: Any) -> ActionResult:
        """Perform an ALREADY-AUTHORIZED action. Returns a verdict-bearing result."""
        started = time.monotonic()
        # `dry_run` is threaded explicitly; remove it from the passthrough params so
        # the handler does not receive it twice.
        dry_run = self._config.computer_mode == "dry_run" or bool(params.pop("dry_run", False))
        handler = getattr(self, f"_act_{action}", None)
        if handler is None:
            return self._failure(action, "COMPUTER_UNSUPPORTED_ACTION", f"Eclipse doesn't know the action {action!r}.",
                                 started, verdict="abort")
        try:
            self.takeover_guard()
            result = await handler(dry_run=dry_run, **params)
        except ComputerError as exc:
            self.session.record_action({"action": action, "result": "failed", "verdict": exc.verdict, "code": exc.code})
            self.session._record_action_db({"action": action, "result": "failed", "verdict": exc.verdict})
            return ActionResult(
                action=action, success=False, verdict=exc.verdict, state="ACTION_FAILED",
                error=exc.to_dict(), summary=exc.reason,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
        except Exception as exc:  # noqa: BLE001 - an action failure is data
            return self._failure(action, "COMPUTER_ACTION_FAILED", str(exc)[:300], started, verdict="retry")
        result.duration_ms = int((time.monotonic() - started) * 1000)
        if self.session.telemetry is not None:
            self.session.telemetry.record_action(action=action, success=result.success,
                                                 duration_ms=result.duration_ms, verdict=result.verdict)
        return result

    def _failure(self, action: str, code: str, message: str, started: float, *, verdict: str = "retry") -> ActionResult:
        from .errors import ComputerError as CE  # noqa: PLC0415

        error = CE(message, code=code, action=action, verdict=verdict)
        return ActionResult(
            action=action, success=False, verdict=verdict, state="ACTION_FAILED",
            error=error.to_dict(), summary=message,
            duration_ms=int((time.monotonic() - started) * 1000),
        )

    # ── helpers used by the handlers ─────────────────────────────────────────

    def _app_name(self, window_id: Optional[str]) -> str:
        if not window_id:
            return ""
        try:
            window = self.session.driver.get_window(window_id)
            return window.app if window else ""
        except Exception:  # noqa: BLE001
            return ""

    def _resolve_target(self, params: dict[str, Any]) -> Target:
        """Ground an element/coordinates/description request to a Target."""
        snapshot = self.session.latest_snapshot
        if snapshot is None:
            raise TargetNotFound("Eclipse needs an observation before it can act.", session_id=self.session.id)

        element = params.get("element")
        if element is not None:
            check = self.session.validate_handle(
                snapshot_id=params.get("snapshot_id"), ref=str(element),
                identity=params.get("identity"),
            )
            if not check.ok:
                from .errors import StaleElement  # noqa: PLC0415

                raise StaleElement(check.reason, session_id=self.session.id, target=str(element))
            found = snapshot.element(str(element))
            if found is None:
                raise TargetNotFound(f"element #{element} isn't in the current snapshot.", session_id=self.session.id)
            return Target(
                description=found.name or f"#{element}", method="accessibility",
                confidence=1.0, bounds=found.bounds, application=snapshot.application,
                window_id=snapshot.window_id, snapshot_id=snapshot.snapshot_id,
                element_ref=found.ref, role=found.role, name=found.name,
            )

        if params.get("coordinates"):
            bounds = Bounds.from_any(params["coordinates"])
            if bounds is not None:
                return Target(
                    description="coordinate", method="coordinate", confidence=0.3, bounds=bounds,
                    application=snapshot.application, window_id=snapshot.window_id,
                    snapshot_id=snapshot.snapshot_id,
                )

        intent = params.get("target") or params.get("description") or params.get("name") or ""
        app_profile = None
        if snapshot.window_id:
            try:
                window = self.session.driver.get_window(snapshot.window_id)
                app_profile = self.session.adapter_for(
                    app_name=window.app if window else "", title=window.title if window else "",
                )
            except Exception:  # noqa: BLE001
                app_profile = None
        query = GroundingQuery(
            intent=str(intent), name=params.get("name"), role=params.get("role"),
            text=params.get("text"), value=params.get("value"),
        )
        return self.session.ground(query, app_profile=app_profile, allow_coordinates=bool(params.get("allow_coordinates")))

    async def _deliver(self, params: dict[str, Any], *, action: str, permission: str,
                       attempt, window_id: Optional[str] = None, expect: Optional[dict] = None,
                       capture_after: bool = False, foreground_only: bool = False,
                       dry_run: bool = False) -> ActionResult:
        """The shared act path: background attempt → optional foreground escalation →
        verify → capture_after. `attempt` is an async callable taking a delivery mode."""
        if not dry_run and self._config.computer_mode != "dry_run":
            self.require_permission(permission, action=action, app=self._app_name(window_id))
        else:
            # dry_run still checks policy so the described action is accurate.
            decision = self.authorize(permission, action=action, app=self._app_name(window_id))
            return ActionResult(
                action=action, success=True, verdict="success", delivery_mode="dry_run",
                state="ACTION_READY", summary=f"DRY RUN: Eclipse would {action.replace('_', ' ')}.",
                verification={"status": "not_run", "summary": "dry run — nothing was executed"},
                evidence=[{"kind": "dry_run", "detail": decision.to_dict()}],
            )

        before = await self.session.capture_state(window_id=window_id)
        delivery = FOREGROUND if foreground_only else self.default_delivery
        if delivery == FOREGROUND:
            self.session.remember_focus()

        try:
            input_result = await attempt(delivery)
        except ComputerError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise ActionFailed(f"Eclipse couldn't {action.replace('_', ' ')}.",
                               session_id=self.session.id, action=action, metadata={"error": str(exc)[:200]}) from exc

        delivered = getattr(input_result, "delivered", True)
        used_mode = getattr(input_result, "delivery_mode", delivery)

        # Background attempt that did not take? Escalate to foreground ONCE.
        verification = None
        if self._config.verification_enabled:
            verification = await self.session.verify_action(before, action=action, expect=expect, window_id=window_id)
            if used_mode == BACKGROUND and not verification.state_changed and self._escalation_allowed() and not foreground_only:
                self.session.remember_focus()
                try:
                    input_result = await attempt(FOREGROUND)
                    used_mode = FOREGROUND
                    if self.session.telemetry is not None:
                        self.session.telemetry.record_foreground()
                    verification = await self.session.verify_action(before, action=action, expect=expect, window_id=window_id)
                except Exception:  # noqa: BLE001 - keep the background result if escalation fails
                    pass

        success = bool(delivered) and (verification is None or verification.status != "failed")
        verdict = self._verdict_for(verification, success)
        state = "CONFIRMED" if (verification and verification.status == "verified") else "ACTION_EXECUTED"
        if verification is not None and verification.status == "failed":
            state = "STATE_CHANGED"
        snapshot_after = None
        if capture_after:
            try:
                snapshot_after = (await self.session.observe(window_id=window_id)).summary()
            except Exception:  # noqa: BLE001
                snapshot_after = None

        result = ActionResult(
            action=action, success=success, verdict=verdict, delivery_mode=used_mode,
            target=None, evidence=[{"kind": "input", "delivered": delivered}],
            verification=verification.to_dict() if verification else None,
            state=state, observed_change=bool(verification and verification.state_changed),
            summary=self._summary_for(action, verification, used_mode),
            snapshot=snapshot_after,
        )
        self.session.record_action({
            "action": action, "result": "ok" if success else "failed",
            "verdict": verdict, "deliveryMode": used_mode,
        })
        self.session._record_action_db({
            "action": action, "deliveryMode": used_mode, "result": "ok" if success else "failed",
            "verification": (verification.status if verification else ""), "verdict": verdict,
        })
        return result

    def _verdict_for(self, verification: Any, success: bool) -> str:
        if verification is None:
            return "success" if success else "retry"
        if verification.status == "verified":
            return "success"
        if verification.status == "failed":
            return "recapture"
        # uncertain: the input was delivered but no change was observed. That is
        # NOT a success — the agent should re-capture and decide.
        return "success" if (success and verification.state_changed) else "recapture"

    def _summary_for(self, action: str, verification: Any, delivery: str) -> str:
        base = f"{action.replace('_', ' ')} via {delivery} input"
        if verification is None:
            return base + "."
        return f"{base}; {verification.summary}"

    # ── the action handlers ──────────────────────────────────────────────────

    async def _act_capture(self, *, dry_run: bool = False, mode: Optional[str] = None,
                           window_id: Optional[str] = None, capture_after: bool = False, **_: Any) -> ActionResult:
        snapshot = await self.observe(window_id=window_id, mode=mode)
        return ActionResult(
            action="capture", success=True, verdict="success", state="OBSERVED",
            summary=f"Captured {len(snapshot.elements)} element(s) in {snapshot.mode} mode.",
            snapshot=snapshot.summary(), evidence=[{"kind": "snapshot", "id": snapshot.snapshot_id}],
        )

    async def _act_click(self, *, dry_run: bool = False, button: str = "left", count: int = 1,
                         capture_after: bool = False, foreground: bool = False, params: Optional[dict] = None, **kwargs: Any) -> ActionResult:
        params = dict(kwargs)
        target = self._resolve_target(params)
        if dry_run:
            return self._dry("click" if count == 1 else "double_click",
                             f"click {target.description!r} via {button} button")
        wid = target.window_id or params.get("window_id")
        window_id = wid or None
        return await self._deliver(
            params, action="click" if count == 1 else "double_click",
            permission="click",
            attempt=lambda mode: self.session.apply_click(target, button=button, count=count, delivery_mode=mode, window_id=window_id),
            window_id=window_id, capture_after=capture_after, foreground_only=foreground, dry_run=dry_run,
        )

    async def _act_double_click(self, *, dry_run: bool = False, capture_after: bool = False, foreground: bool = False, **kwargs: Any) -> ActionResult:
        return await self._act_click(dry_run=dry_run, count=2, capture_after=capture_after, foreground=foreground, **kwargs)

    async def _act_right_click(self, *, dry_run: bool = False, capture_after: bool = False, foreground: bool = False, **kwargs: Any) -> ActionResult:
        return await self._act_click(dry_run=dry_run, button="right", capture_after=capture_after, foreground=foreground, **kwargs)

    async def _act_middle_click(self, *, dry_run: bool = False, capture_after: bool = False, foreground: bool = False, **kwargs: Any) -> ActionResult:
        return await self._act_click(dry_run=dry_run, button="middle", capture_after=capture_after, foreground=foreground, **kwargs)

    async def _act_mouse_move(self, *, dry_run: bool = False, x: int = 0, y: int = 0, relative: bool = False, **_: Any) -> ActionResult:
        if dry_run:
            return self._dry("mouse_move", f"move the pointer to ({x},{y})")
        self.require_permission("scroll", action="mouse_move")
        if relative:
            await self.session.mouse.move_relative(x, y)
        else:
            await self.session.mouse.move(x, y)
        return ActionResult(action="mouse_move", success=True, verdict="success", delivery_mode="foreground",
                            summary=f"Moved the pointer to ({x},{y}).", state="ACTION_EXECUTED")

    async def _act_mouse_position(self, **_: Any) -> ActionResult:
        pos = self.session.mouse.position()
        return ActionResult(action="mouse_position", success=pos is not None, verdict="success", state="OBSERVED",
                            summary=f"Pointer at ({pos.x},{pos.y})." if pos else "unknown",
                            evidence=[{"kind": "pointer", "position": pos.to_dict() if pos else None}])

    async def _act_scroll(self, *, dry_run: bool = False, dx: int = 0, dy: int = 0,
                          x: Optional[int] = None, y: Optional[int] = None, capture_after: bool = False, **_: Any) -> ActionResult:
        if dry_run:
            return self._dry("scroll", f"scroll dx={dx} dy={dy}")
        self.require_permission("scroll", action="scroll")
        at = (x, y) if x is not None and y is not None else None
        await self.session.mouse.scroll(dx=dx, dy=dy, at=at, delivery_mode="foreground")
        return ActionResult(action="scroll", success=True, verdict="success", delivery_mode="foreground",
                            state="ACTION_EXECUTED", summary=f"Scrolled dx={dx} dy={dy}.")

    async def _act_type(self, *, dry_run: bool = False, text: str = "", capture_after: bool = False,
                        foreground: bool = False, **kwargs: Any) -> ActionResult:
        # Never echo the text back (it may be a secret).
        params = dict(kwargs)
        window_id = params.get("window_id")
        if dry_run:
            return self._dry("type", f"type {len(text)} character(s)")
        return await self._deliver(
            params, action="type", permission="type",
            attempt=lambda mode: self.session.keyboard.type_text(text, delivery_mode=mode, window_id=window_id),
            window_id=window_id, capture_after=capture_after, foreground_only=foreground, dry_run=dry_run,
        )

    async def _act_key(self, *, dry_run: bool = False, key: str = "", capture_after: bool = False,
                       foreground: bool = False, **kwargs: Any) -> ActionResult:
        params = dict(kwargs)
        window_id = params.get("window_id")
        if dry_run:
            return self._dry("key", f"press {key}")
        return await self._deliver(
            params, action="key", permission="key",
            attempt=lambda mode: self.session.keyboard.press(key, delivery_mode=mode, window_id=window_id),
            window_id=window_id, capture_after=capture_after, foreground_only=foreground, dry_run=dry_run,
        )

    async def _act_hotkey(self, *, dry_run: bool = False, combo: str = "", capture_after: bool = False,
                          foreground: bool = False, **kwargs: Any) -> ActionResult:
        params = dict(kwargs)
        window_id = params.get("window_id")
        if dry_run:
            return self._dry("hotkey", f"press {combo}")
        return await self._deliver(
            params, action="hotkey", permission="key",
            attempt=lambda mode: self.session.keyboard.hotkey(combo, delivery_mode=mode, window_id=window_id),
            window_id=window_id, capture_after=capture_after, foreground_only=foreground, dry_run=dry_run,
        )

    async def _act_set_value(self, *, dry_run: bool = False, value: str = "", capture_after: bool = False,
                             foreground: bool = False, **kwargs: Any) -> ActionResult:
        params = dict(kwargs)
        target = self._resolve_target(params)
        window_id = target.window_id or params.get("window_id") or None
        if dry_run:
            return self._dry("set_value", f"set {target.description!r} to {value!r}")
        before = await self.session.capture_state(window_id=window_id)
        self.require_permission("set_value", action="set_value", app=self._app_name(window_id))
        await self.session.value_setter.set_value(
            bounds=target.bounds, value=value, role=target.role,
            window_id=window_id, delivery_mode=self.default_delivery,
        )
        verification = await self.session.verify_action(before, action="set_value", window_id=window_id)
        return ActionResult(
            action="set_value", success=verification.status != "failed", verdict="success" if verification.status == "verified" else "recapture",
            state="CONFIRMED" if verification.status == "verified" else "ACTION_EXECUTED",
            verification=verification.to_dict(), observed_change=verification.state_changed,
            summary=f"Set {target.description!r}; {verification.summary}",
        )

    async def _act_drag(self, *, dry_run: bool = False, capture_after: bool = False,
                        from_coordinates: Any = None, to_coordinates: Any = None,
                        source: Any = None, target_el: Any = None, foreground: bool = True, **_unused: Any) -> ActionResult:
        if self._config.computer_mode == "dry_run":
            return self._dry("drag", "drag from one point to another")
        self.require_permission("drag", action="drag")
        frm = Bounds.from_any(from_coordinates) if isinstance(from_coordinates, (list, tuple, dict)) else None
        to = Bounds.from_any(to_coordinates) if isinstance(to_coordinates, (list, tuple, dict)) else None
        if frm is None or to is None:
            raise ActionFailed("drag needs from_coordinates and to_coordinates.")
        before = await self.session.capture_state()
        await self.session.mouse.drag(*frm.center, *to.center, delivery_mode="foreground")
        verification = await self.session.verify_action(before, action="drag")
        return ActionResult(action="drag", success=True, verdict="success", delivery_mode="foreground",
                            state="ACTION_EXECUTED", verification=verification.to_dict(),
                            summary="Dragged the pointer between the two points.")

    async def _act_wait(self, *, dry_run: bool = False, ms: int = 1000, **_: Any) -> ActionResult:
        import asyncio  # noqa: PLC0415

        await asyncio.sleep(max(0, min(int(ms), 60_000)) / 1000)
        return ActionResult(action="wait", success=True, verdict="success", state="CONFIRMED", summary=f"Waited {ms}ms.")

    # ── read-only introspection actions ──────────────────────────────────────

    async def _act_list_windows(self, **_: Any) -> ActionResult:
        self.require_permission("list")
        windows = self.session.windows.list()
        return ActionResult(
            action="list_windows", success=True, verdict="success", state="OBSERVED",
            summary=f"{len(windows)} window(s).",
            evidence=[{"kind": "windows", "items": [w.to_dict() for w in windows[:50]]}],
        )

    async def _act_list_apps(self, **_: Any) -> ActionResult:
        self.require_permission("list")
        apps = self.session.applications.list()
        return ActionResult(action="list_apps", success=True, verdict="success", state="OBSERVED",
                            summary=f"{len(apps)} application(s).",
                            evidence=[{"kind": "apps", "items": [a.to_dict() for a in apps[:50]]}])

    async def _act_focus_app(self, *, app: str = "", window_id: Optional[str] = None, **_unused: Any) -> ActionResult:
        self.require_permission("window_control", action="window_focus")
        if window_id is None:
            matches = self.session.windows.find(app=app) or self.session.windows.find(title=app)
            if not matches:
                raise TargetNotFound(f"No window for {app!r} is open.", app=app)
            window_id = matches[0].id
        result = await self.session.windows.focus(window_id, foreground=True)
        return ActionResult(action="focus_app", success=True, verdict="success", delivery_mode="foreground",
                            state="ACTION_EXECUTED", summary=f"Focused window {window_id}.",
                            evidence=[{"kind": "focus", **result}])

    def _dry(self, action: str, description: str) -> ActionResult:
        return ActionResult(
            action=action, success=True, verdict="success", delivery_mode="dry_run", state="ACTION_READY",
            summary=f"DRY RUN: Eclipse would {description}.",
            verification={"status": "not_run", "summary": "dry run — nothing was executed"},
        )


__all__ = ["ActionOutcome", "ComputerCore", "BACKGROUND", "FOREGROUND"]
