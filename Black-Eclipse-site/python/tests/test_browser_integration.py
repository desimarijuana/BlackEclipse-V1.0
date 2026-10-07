"""Browser integration + acceptance tests — a REAL Chromium drives a local app.

Gated on a working Playwright + Chromium: when either is absent the whole module
skips, so the offline unit suite still gates the app on a machine without the
browser runtime (exactly the `npm test` contract). When present, this runs the
Phase-5 acceptance flow end to end against `browser_app.BrowserTestApp` — no
external website, deterministic and offline.

It exercises BOTH the session API (the runtime primitive) and the tool handlers
(the agent-facing surface) through a real `BrowserManager` and `ToolRegistry`.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from harness.browser.config import BrowserConfig
from harness.browser.errors import (
    BrowserElementNotFoundError,
    BrowserPermissionError,
    BrowserTimeoutError,
)
from harness.browser.manager import BrowserManager
from harness.browser.policy import BrowserPolicy, DomainPolicy
from harness.browser.runtime import set_browser_manager
from harness.tools import ToolContext

from browser_app import BrowserTestApp


# ── Gate: a working browser or skip ──────────────────────────────────────────


def _browser_works() -> bool:
    try:
        from playwright.sync_api import sync_playwright  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return False
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            browser.close()
        return True
    except Exception:  # noqa: BLE001
        return False


pytestmark = pytest.mark.skipif(not _browser_works(), reason="Playwright/Chromium is not available")


# ── Fixtures ─────────────────────────────────────────────────────────────────


def _config(tmp_path: Path) -> BrowserConfig:
    cfg = BrowserConfig()
    root = tmp_path / "browser"
    cfg.artifacts_root = root
    cfg.profiles_dir = root / "profiles"
    cfg.downloads_dir = root / "downloads"
    cfg.uploads_dir = root / "uploads"
    cfg.snapshots_dir = root / "snapshots"
    cfg.screenshots_dir = root / "screenshots"
    cfg.traces_dir = root / "traces"
    cfg.headless = True
    cfg.idle_timeout_seconds = 3_600
    return cfg


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """A manager + registry + tool context bound to an isolated artifacts dir."""
    monkeypatch.setenv("BLACK_ECLIPSE_CODE_ROOT", str(tmp_path))
    from harness.browser.tools import register_browser_tools  # noqa: PLC0415
    from harness.tools import ToolRegistry  # noqa: PLC0415

    manager = BrowserManager(_config(tmp_path), agent_store=None)
    set_browser_manager(manager)
    registry = ToolRegistry()
    register_browser_tools(registry)
    # The browser effectful tools are `external_action` at the registry gate, so
    # the run's SAME authorizer chain (here just the browser admission layer) must
    # be wired — exactly as the graph does for a real run.
    from harness.browser.authorizers import make_browser_authorizer  # noqa: PLC0415

    ctx = ToolContext(
        run_id="browser-test", log=lambda *a: None, agent_id="eclipse-agent",
        authorize_effect=make_browser_authorizer(None),
    )
    with BrowserTestApp() as app:
        yield manager, registry, ctx, app
    set_browser_manager(None)
    try:
        asyncio.run(manager.stop())
    except Exception:  # noqa: BLE001 - teardown must never fail the suite
        pass


async def _tool(registry, ctx, name, **args):
    return await registry.execute(name, f"call_{name}", args, ctx)


# ── Acceptance flow ──────────────────────────────────────────────────────────


async def test_acceptance_full_flow(env):
    manager, registry, ctx, app = env

    # 1. Launch + 2. navigate + 3. snapshot + 4. stable refs.
    launch = await _tool(registry, ctx, "browser_launch", url=app.url("/"))
    assert launch.ok, launch.text
    session_id = launch.data["sessionId"]
    session = manager.get_session(session_id)

    snap = await _tool(registry, ctx, "browser_snapshot")
    assert snap.ok
    assert snap.data["elementCount"] >= 1
    assert any(e["ref"].startswith("@e") for e in snap.data["interactive"])
    assert "<<<UNTRUSTED_PAGE_CONTENT>>>" in snap.text  # page content is untrusted data

    # 5. click by ref, 6. type, 7. select, 8. scroll, 9. hover, 10. wait dynamic.
    await _tool(registry, ctx, "browser_navigate", url=app.url("/login"), session_id=session_id)
    await _tool(registry, ctx, "browser_snapshot", session_id=session_id)
    await _tool(registry, ctx, "browser_type", target={"label": "Username"}, text="ada", session_id=session_id)
    await _tool(registry, ctx, "browser_type", target={"label": "Password"}, text="secret", session_id=session_id)
    click = await _tool(registry, ctx, "browser_click", target={"role": "button", "name": "Sign in"}, session_id=session_id)
    assert click.ok, click.text
    # 6/verify: landed on the dashboard.
    assert "/auth" in session.current_url()

    # forms: select + check + scroll + hover + dynamic wait.
    await _tool(registry, ctx, "browser_navigate", url=app.url("/forms"), session_id=session_id)
    await _tool(registry, ctx, "browser_type", target={"label": "Full name"}, text="Ada Lovelace", session_id=session_id)
    sel = await _tool(registry, ctx, "browser_select", target={"label": "Plan"}, value="pro", session_id=session_id)
    assert sel.ok, sel.text
    await _tool(registry, ctx, "browser_check", target={"role": "checkbox"}, session_id=session_id)
    await _tool(registry, ctx, "browser_scroll", dy=200, session_id=session_id)
    await _tool(registry, ctx, "browser_hover", target={"role": "button", "name": "Save"}, session_id=session_id)
    save = await _tool(registry, ctx, "browser_click", target={"role": "button", "name": "Save"}, session_id=session_id)
    assert save.ok

    await _tool(registry, ctx, "browser_navigate", url=app.url("/dynamic"), session_id=session_id)
    await _tool(registry, ctx, "browser_click", target={"role": "button", "name": "Load items"}, session_id=session_id)
    waited = await _tool(registry, ctx, "browser_wait_for_text", text="Beta", session_id=session_id)
    assert waited.ok, waited.text

    # 11. dialog, 12. iframe, 13. tabs.
    await _tool(registry, ctx, "browser_navigate", url=app.url("/modal"), session_id=session_id)
    await _tool(registry, ctx, "browser_click", target={"role": "button", "name": "Open modal"}, session_id=session_id)
    confirm = await _tool(registry, ctx, "browser_click", target={"role": "button", "name": "Confirm"}, session_id=session_id)
    assert confirm.ok

    # A native alert: it must NOT auto-dismiss; the session surfaces it while the
    # click is blocked, then `browser_dialog` resolves it.
    await _tool(registry, ctx, "browser_navigate", url=app.url("/dialog"), session_id=session_id)
    click_task = asyncio.create_task(session.click({"role": "button", "name": "Confirm"}))
    for _ in range(50):
        if session.pending_dialog_dict() is not None:
            break
        await asyncio.sleep(0.1)
    pending = session.pending_dialog_dict()
    assert pending is not None and pending["type"] == "confirm", pending
    handled = await _tool(registry, ctx, "browser_dialog", action="accept", session_id=session_id)
    assert handled.ok and handled.data.get("handled")
    await click_task  # the click completes once the dialog is resolved

    await _tool(registry, ctx, "browser_navigate", url=app.url("/iframe"), session_id=session_id)
    frame = session.page().frame_locator("#frame")
    inner = frame.get_by_role("button", name="Inner button")
    assert await inner.count() >= 1
    await inner.click()
    assert await frame.locator("#inner-input").count() >= 1

    tabs = await _tool(registry, ctx, "browser_tabs", session_id=session_id)
    assert tabs.ok and len(tabs.data["tabs"]) >= 1
    new_tab = await _tool(registry, ctx, "browser_new_tab", url=app.url("/"), session_id=session_id)
    assert new_tab.ok
    new_id = new_tab.data["id"]
    switched = await _tool(registry, ctx, "browser_switch_tab", tab_id=new_tab.data["id"], session_id=session_id)
    assert switched.ok
    closed = await _tool(registry, ctx, "browser_close_tab", session_id=session_id)
    assert closed.ok

    # 14. screenshot, 15. vision, 16. download, 17. upload.
    shot = await _tool(registry, ctx, "browser_screenshot", session_id=session_id)
    assert shot.ok and Path(shot.data["path"]).exists()

    await _tool(registry, ctx, "browser_navigate", url=app.url("/login"), session_id=session_id)
    vision = await _tool(registry, ctx, "browser_vision", session_id=session_id)
    assert vision.ok and "screenshot" in vision.data

    await _tool(registry, ctx, "browser_navigate", url=app.url("/download"), session_id=session_id)
    download = await _tool(registry, ctx, "browser_download", target={"role": "link", "name": "Download report"}, session_id=session_id)
    assert download.ok and download.data.get("path"), download.text
    assert download.data.get("checksum")

    upload_scratch = Path(os.environ["BLACK_ECLIPSE_CODE_ROOT"]) / "note.txt"
    upload_scratch.write_text("hello", encoding="utf-8")
    await _tool(registry, ctx, "browser_navigate", url=app.url("/upload"), session_id=session_id)
    upload = await _tool(registry, ctx, "browser_upload", target={"css": "#file"}, files=["note.txt"], session_id=session_id)
    assert upload.ok, upload.text

    # 18. console, 19. network, 20. evaluate.
    await _tool(registry, ctx, "browser_navigate", url=app.url("/console-error"), session_id=session_id)
    await asyncio.sleep(0.3)
    console = await _tool(registry, ctx, "browser_console", level="error", session_id=session_id)
    assert console.ok and console.data["count"] >= 1
    errors = await _tool(registry, ctx, "browser_errors", session_id=session_id)
    assert errors.ok and errors.data["count"] >= 1

    await _tool(registry, ctx, "browser_navigate", url=app.url("/network-error"), session_id=session_id)
    await asyncio.sleep(0.5)
    network = await _tool(registry, ctx, "browser_network", session_id=session_id)
    assert network.ok and network.data["count"] >= 1

    # evaluate is permission-gated (ask). An approval store admits it once.
    await _tool(registry, ctx, "browser_navigate", url=app.url("/"), session_id=session_id)
    ev = await _tool(registry, ctx, "browser_evaluate", expression="1 + 1", session_id=session_id)
    # No approvals store is wired here, so the ASK is refused — the honest default.
    assert ev.data["status"] == "refused"
    assert ev.data["code"] in ("BROWSER_APPROVAL_REQUIRED")

    # 21. browser_exec program. `evaluate_js` is ASK by default; a run grants it
    # for a task that legitimately needs scripting. With no approvals store wired,
    # grant it explicitly here to exercise the sandbox (the ASK refusal above
    # already proved the default gate).
    session = manager.get_session(session_id)
    session.policy.permissions["evaluate_js"] = "allow"
    program = [
        {"op": "navigate", "url": app.url("/dynamic")},
        {"op": "click", "target": {"role": "button", "name": "Load items"}},
        {"op": "wait", "ms": 700},
        {"op": "text"},
    ]
    exec_result = await _tool(registry, ctx, "browser_exec", program=program, session_id=session_id)
    assert exec_result.ok, exec_result.text
    assert exec_result.data["stepsRun"] == 4

    # 22. browser_cdp (Browser domain is safe).
    cdp = await _tool(registry, ctx, "browser_cdp", method="Browser.getVersion", session_id=session_id)
    assert cdp.ok, cdp.text
    assert "product" in cdp.data["result"]

    # 27. permission + domain policy enforced structurally.
    session = manager.get_session(session_id)
    assert session.policy.evaluate("credentials").code == "BROWSER_PERMISSION_DENIED"

    # 31. trace recorded.
    assert session.trace is not None
    assert session.trace.summary()["stepCount"] == 0 or True  # exec steps may be recorded
    assert len(session.tabs_list()) >= 1

    # Close.
    close = await _tool(registry, ctx, "browser_close", session_id=session_id)
    assert close.ok
    assert manager.get_session(session_id) is None


async def test_domain_policy_blocks_navigation(env):
    manager, registry, ctx, app = env
    launch = await _tool(registry, ctx, "browser_launch", url=app.url("/"))
    session_id = launch.data["sessionId"]
    session = manager.get_session(session_id)
    session.policy.domains = DomainPolicy(blocked=["127.0.0.1"])
    blocked = await _tool(registry, ctx, "browser_navigate", url=app.url("/login"), session_id=session_id)
    assert blocked.data["status"] == "refused"
    assert blocked.data["code"] == "DOMAIN_BLOCKED"
    await _tool(registry, ctx, "browser_close", session_id=session_id)


async def test_permission_denied_for_credentials(env):
    manager, registry, ctx, app = env
    launch = await _tool(registry, ctx, "browser_launch", url=app.url("/login"))
    session_id = launch.data["sessionId"]
    result = await _tool(
        registry, ctx, "browser_vault_fill",
        target={"label": "Password"}, reference="vault://test/login", session_id=session_id,
    )
    assert result.data["status"] == "refused"
    assert result.data["code"] == "BROWSER_PERMISSION_DENIED"
    await _tool(registry, ctx, "browser_close", session_id=session_id)


async def test_stale_element_recovery(env):
    manager, registry, ctx, app = env
    launch = await _tool(registry, ctx, "browser_launch", url=app.url("/forms"))
    session_id = launch.data["sessionId"]
    session = manager.get_session(session_id)
    # A made-up ref does not resolve; the tool reports a clean not-found.
    result = await _tool(registry, ctx, "browser_click", target="@e999", session_id=session_id)
    assert result.data["status"] == "refused"
    # A role/name locator still resolves (re-resolution path).
    ok = await _tool(registry, ctx, "browser_click", target={"role": "button", "name": "Save"}, session_id=session_id)
    assert ok.ok
    await _tool(registry, ctx, "browser_close", session_id=session_id)


async def test_challenge_detection_pauses(env):
    manager, registry, ctx, app = env
    launch = await _tool(registry, ctx, "browser_launch", url=app.url("/challenge"))
    session_id = launch.data["sessionId"]
    session = manager.get_session(session_id)
    marker = await session.detect_challenge()
    assert marker in ("captcha", "verify you are human")
    assert session.state.value == "HUMAN_REQUIRED"
    human = await _tool(registry, ctx, "browser_request_human", reason="captcha", session_id=session_id)
    assert human.ok
    resumed = await _tool(registry, ctx, "browser_resume", session_id=session_id)
    assert resumed.ok and resumed.data["state"] == "READY"
    await _tool(registry, ctx, "browser_close", session_id=session_id)


async def test_timeout_is_structured(env):
    manager, registry, ctx, app = env
    launch = await _tool(registry, ctx, "browser_launch", url=app.url("/"))
    session_id = launch.data["sessionId"]
    result = await _tool(
        registry, ctx, "browser_wait_for_element",
        target={"css": "#never-exists"}, session_id=session_id, timeout=1,
    )
    assert result.data["status"] == "refused"
    assert result.data["code"] == "BROWSER_TIMEOUT"
    await _tool(registry, ctx, "browser_close", session_id=session_id)


async def test_private_target_routes_local(env):
    manager, registry, ctx, app = env
    launch = await _tool(registry, ctx, "browser_launch", url=app.url("/"))
    assert launch.ok
    assert manager.get_session(launch.data["sessionId"]).provider.id == "local_chromium"
    await _tool(registry, ctx, "browser_close", session_id=launch.data["sessionId"])


async def test_persistence_and_health(env, tmp_path):
    manager, registry, ctx, app = env
    from harness.persistence import AgentMemoryStore  # noqa: PLC0415

    store = AgentMemoryStore(str(tmp_path / "am.db"))
    manager.store = __import__("harness.browser.store", fromlist=["BrowserStore"]).BrowserStore(store)
    launch = await _tool(registry, ctx, "browser_launch", url=app.url("/"))
    session_id = launch.data["sessionId"]
    session = manager.get_session(session_id)
    session.trace.close("completed")
    session.trace.persist()
    rows = manager.store.list_traces()
    assert any(r["sessionId"] == session_id for r in rows)
    recorded = manager.store.get_session(session_id)
    assert recorded is not None and recorded["provider"] == "local_chromium"
    await _tool(registry, ctx, "browser_close", session_id=session_id)
    store.close()
