"""The `browser_*` toolset — the agent-facing browser capability.

Every browser tool is registered on the SAME `ToolRegistry` as finance, code,
terminal and git tools, so validation, permission, timeout, effect authorization
and the event stream apply unchanged. Handlers resolve the process-wide
`BrowserManager` from the runtime singleton; a missing manager is an honest
UNAVAILABLE, never a fake browser.

Security is layered and structural (shared helpers live in `tool_support.py`):
  * the browser POLICY ENGINE checks the permission AND the domain before a
    sensitive action; an ASK routes through the SAME single-use approval store the
    rest of the harness uses;
  * page content is UNTRUSTED — every observation is wrapped by `wrap_untrusted`;
  * a destructive-looking click (delete/pay/send) is elevated to ASK;
  * CDP commands are confined to a closed domain set.

The admin tools (sessions/profiles/vault/device) live in `tool_admin.py`.
"""

from __future__ import annotations

import logging
from typing import Any

from ..tools import ToolContext, ToolDefinition, ToolRegistry
from . import config as config_mod
from . import execution as exec_mod
from .errors import BrowserError
from .policy import wrap_untrusted
from .schemas import INPUT_SCHEMAS, TOOL_META
from .tool_admin import ADMIN_HANDLERS
from .tool_support import (
    emit,
    guard_external_submission,
    injection_note,
    manager,
    ok,
    opt_timeout,
    refusal,
    require_permission,
    resolve_upload_paths,
    session_of,
    unavailable,
)

log = logging.getLogger("harness.browser.tools")


# ── Lifecycle / navigation ───────────────────────────────────────────────────


async def _launch(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    mgr = manager()
    if mgr is None:
        return unavailable()
    from .tool_support import domain_policy_from  # noqa: PLC0415

    viewport = args.get("viewport") if isinstance(args.get("viewport"), dict) else None
    policy = mgr.build_policy(
        permissions=args.get("permissions") if isinstance(args.get("permissions"), dict) else None,
        domains=domain_policy_from(args),
    )
    try:
        session = await mgr.create_session(
            provider=args.get("provider"), url=args.get("url"),
            headless=args.get("headless"), profile_id=args.get("profile"),
            persistent=bool(args.get("persistent")),
            agent_id=getattr(ctx, "agent_id", None), task_id=getattr(ctx, "run_id", None),
            run_id=getattr(ctx, "run_id", None), policy=policy, viewport=viewport,
        )
    except BrowserError as exc:
        await emit(ctx, "browser.launch.failed", exc.to_dict())
        return refusal(exc, "browser_launch")
    await emit(ctx, "browser.launched", {
        "sessionId": session.id, "provider": session.provider.id, "url": session.current_url(),
    })
    text = (
        f"Browser session {session.id} is ready ({session.provider.label}). "
        f"Current page: {session.current_url() or '(blank)'}. "
        "Call browser_snapshot to see the page before acting."
    )
    return ok("launch", text, {"sessionId": session.id, "session": session.snapshot_summary()})


async def _close(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    result = await manager().destroy_session(session.id)
    await emit(ctx, "browser.closed", {"sessionId": session.id})
    return ok("close", f"Browser session {session.id} is closed.", result)


async def _status(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    summary = session.snapshot_summary()
    text = (
        f"Session {session.id}: {summary['state']}, page {summary['url'] or '(blank)'}. "
        f"{len(summary['tabs'])} tab(s)."
    )
    return ok("status", text, {"session": summary})


async def _navigate(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    url = str(args["url"])
    allowed, gate = await require_permission(ctx, session, "navigate", url=url, tool="browser_navigate")
    if not allowed:
        return gate  # type: ignore[return-value]
    try:
        result = await session.navigate(url, wait_until=args.get("wait_until") or "domcontentloaded", timeout=opt_timeout(args))
    except BrowserError as exc:
        await emit(ctx, "browser.navigate.failed", {"sessionId": session.id, **exc.to_dict()})
        return refusal(exc, "browser_navigate")
    await emit(ctx, "browser.navigated", {"sessionId": session.id, "url": result["url"]})
    text = f"Opened {result['url']} — {result.get('title') or '(no title)'}. Call browser_snapshot to see it."
    return ok("navigate", text, result)


def _make_simple_nav(method: str, tool: str, verb: str):
    async def handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
        session, error = session_of(args)
        if error:
            return error
        try:
            result = await getattr(session, method)(timeout=opt_timeout(args))
        except BrowserError as exc:
            return refusal(exc, tool)
        return ok(tool, f"{verb}: {result.get('url', session.current_url())}.", result)
    return handler


async def _stop(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    result = await session.stop()
    return ok("stop", "Stopped loading the page.", result)


# ── Observation ──────────────────────────────────────────────────────────────


async def _snapshot(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        snapshot = await session.snapshot(persist=bool(args.get("persist", True)))
    except BrowserError as exc:
        return refusal(exc, "browser_snapshot")
    note = injection_note(snapshot.full_text)
    header = (
        f"Page: {snapshot.title or '(no title)'} — {snapshot.url}\n"
        f"{len(snapshot.elements)} element(s), {len(snapshot.interactive)} interactive. "
        "Reference elements as @eN.\n"
    )
    if snapshot.truncated and snapshot.full_path:
        header += f"[full snapshot saved to {snapshot.full_path}]\n"
    if note:
        header += f"[{note}]\n"
    body = wrap_untrusted(snapshot.text, source=snapshot.url or "page")
    await emit(ctx, "browser.snapshot", {**snapshot.summary(), "sessionId": session.id, "injection": bool(note)})
    data = {
        "sessionId": session.id, "url": snapshot.url, "title": snapshot.title,
        "interactive": snapshot.interactive, "elementCount": len(snapshot.elements),
        "truncated": snapshot.truncated, "fullPath": snapshot.full_path,
        "injectionDetected": bool(note),
    }
    return ok("snapshot", header + "\n" + body, data)


async def _extract(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        data = await session.extract()
    except BrowserError as exc:
        return refusal(exc, "browser_extract")
    text = wrap_untrusted(
        f"Title: {data.get('title')}\nURL: {data.get('url')}\n\n" + str(data.get("text", ""))[:8000],
        source=data.get("url") or "page",
    )
    return ok("extract", text, {k: v for k, v in data.items() if k != "text"} | {"textChars": len(str(data.get("text", "")))})


async def _screenshot(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        path = await session.screenshot(full_page=bool(args.get("full_page")))
    except Exception as exc:  # noqa: BLE001
        return refusal(BrowserError("Eclipse couldn't capture the page.", action="screenshot", metadata={"error": str(exc)[:200]}), "browser_screenshot")
    await emit(ctx, "browser.screenshot", {"sessionId": session.id, "path": path})
    return ok("screenshot", f"Screenshot saved to {path}.", {"path": path, "url": session.current_url()})


async def _vision(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    shot = None
    if args.get("screenshot", True):
        try:
            shot = await session.screenshot()
        except Exception:  # noqa: BLE001
            shot = None
    visual = await session.visual_map(screenshot=shot)
    text = visual.note
    if visual.elements:
        lines = [f"{e.ref} {e.role} \"{e.name}\" at ({e.box['x']},{e.box['y']})" for e in visual.elements[:40]]
        text += "\n" + wrap_untrusted("\n".join(lines), source=visual.url or "page")
    await emit(ctx, "browser.vision", {"sessionId": session.id, "elements": len(visual.elements), "screenshot": shot})
    return ok("vision", text, visual.to_dict())


async def _visual_find(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    text = str(args["text"])
    page = session.page()
    try:
        locator = page.get_by_text(text, exact=False)
        box = await locator.first.bounding_box()
        count = await locator.count()
    except Exception as exc:  # noqa: BLE001
        return refusal(BrowserError("Eclipse couldn't find that text on the page.", action="visual_find", metadata={"error": str(exc)[:200]}), "browser_visual_find")
    if not box:
        return ("Eclipse didn't find that text on screen.", {"status": "not_found", "text": text})
    return ok("visual_find", f"Found \"{text}\" at ({round(box['x'])},{round(box['y'])}) — {count} match(es).", {"box": box, "count": count, "text": text})


async def _visual_click(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    text = str(args["text"])
    destructive = guard_external_submission(text, session)
    if destructive is not None:
        allowed, gate = await require_permission(ctx, session, "external_submission", detail=text, tool="browser_visual_click")
        if not allowed:
            return gate  # type: ignore[return-value]
    try:
        result = await session.click({"text": text})
    except BrowserError as exc:
        return refusal(exc, "browser_visual_click")
    return ok("visual_click", f"Clicked \"{text}\".", result)


def _make_simple_get(method: str, tool: str):
    async def handler(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
        session, error = session_of(args)
        if error:
            return error
        value = await getattr(session, method)()
        if isinstance(value, list):
            text = wrap_untrusted("\n".join(str(v) for v in value[:40]), source=session.current_url())
            return ok(tool, f"{len(value)} item(s).\n{text}", {"items": value, "count": len(value)})
        text = wrap_untrusted(str(value)[:8000], source=session.current_url())
        return ok(tool, text, {"chars": len(str(value))})
    return handler


async def _get_dom(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    html = await session.get_dom(selector=args.get("selector"))
    text = wrap_untrusted(html[:12000], source=session.current_url())
    return ok("get_dom", text, {"chars": len(html), "selector": args.get("selector")})


# ── Interaction ──────────────────────────────────────────────────────────────


async def _click(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    target = args.get("target")
    label = target if isinstance(target, str) else ""
    destructive = guard_external_submission(label, session)
    if destructive is not None:
        allowed, gate = await require_permission(ctx, session, "external_submission", detail=label, tool="browser_click")
        if not allowed:
            return gate  # type: ignore[return-value]
    try:
        result = await session.click(
            target, expect=args.get("expect"), button=args.get("button") or "left",
            click_count=2 if args.get("double") else 1, timeout=opt_timeout(args),
        )
    except BrowserError as exc:
        await emit(ctx, "browser.action.failed", {"sessionId": session.id, "action": "click", **exc.to_dict()})
        return refusal(exc, "browser_click")
    await emit(ctx, "browser.clicked", {
        "sessionId": session.id, "strategy": result["resolution"]["strategy"],
        "stateChanged": result["state_changed"],
    })
    text = (
        f"Clicked using {result['resolution']['strategy']} "
        f"(confidence {result['resolution']['confidence']:.2f}). "
        f"{result['verification']['summary']}"
    )
    return ok("click", text, result)


async def _type(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    raw_text = str(args["text"])
    from .vault import is_credential_reference  # noqa: PLC0415

    is_ref = is_credential_reference(raw_text)
    text_value = raw_text
    if is_ref:
        allowed, gate = await require_permission(ctx, session, "credentials", detail="vault fill", tool="browser_type")
        if not allowed:
            return gate  # type: ignore[return-value]
        secret = await manager().vault.resolve(raw_text)
        if secret is None:
            return refusal(BrowserError("Eclipse couldn't unlock that saved credential.", action="type", code="BROWSER_AUTHENTICATION_FAILED"), "browser_type")
        text_value = secret
    try:
        result = await session.type_text(
            args.get("target"), text_value, submit=bool(args.get("submit")),
            clear=bool(args.get("clear", True)), expect=args.get("expect"), timeout=opt_timeout(args),
        )
    except BrowserError as exc:
        return refusal(exc, "browser_type")
    await emit(ctx, "browser.typed", {"sessionId": session.id, "chars": result["chars"]})
    shown = "(a saved credential)" if is_ref else f"{result['chars']} characters"
    return ok("type", f"Typed {shown}; {result['verification']['summary']}", result)


async def _select(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.select(args.get("target"), args.get("value"), timeout=opt_timeout(args))
    except BrowserError as exc:
        return refusal(exc, "browser_select")
    return ok("select", f"Selected {result.get('selected')}.", result)


async def _check(args: dict[str, Any], ctx: ToolContext, checked: bool = True) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.check(args.get("target"), checked=checked, timeout=opt_timeout(args))
    except BrowserError as exc:
        return refusal(exc, "browser_check")
    return ok("check", f"{'Checked' if checked else 'Unchecked'} the control.", result)


async def _press(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.press(str(args["key"]), args.get("target"), timeout=opt_timeout(args))
    except BrowserError as exc:
        return refusal(exc, "browser_press")
    return ok("press", f"Pressed {args['key']}.", result)


async def _hover(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.hover(args.get("target"), timeout=opt_timeout(args))
    except BrowserError as exc:
        return refusal(exc, "browser_hover")
    return ok("hover", "Hovered over the element.", result)


async def _scroll(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.scroll(dy=int(args.get("dy") or 600), dx=int(args.get("dx") or 0), selector=args.get("selector"))
    except BrowserError as exc:
        return refusal(exc, "browser_scroll")
    return ok("scroll", "Scrolled the page.", result)


async def _drag(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.drag(args.get("source"), args.get("target"), timeout=opt_timeout(args))
    except BrowserError as exc:
        return refusal(exc, "browser_drag")
    return ok("drag", "Dragged the element.", result)


# ── Waiting ──────────────────────────────────────────────────────────────────


async def _wait(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    result = await session.wait(ms=int(args.get("ms") or 1000))
    return ok("wait", f"Waited {result['waited']}ms.", result)


async def _wait_for_element(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.wait_for_selector(args.get("target"), state=args.get("state") or "visible", timeout=opt_timeout(args))
    except BrowserError as exc:
        return refusal(exc, "browser_wait_for_element")
    return ok("wait_for_element", "The element is present.", result)


async def _wait_for_text(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.wait_for_text(str(args["text"]), timeout=opt_timeout(args))
    except BrowserError as exc:
        return refusal(exc, "browser_wait_for_text")
    return ok("wait_for_text", f"\"{args['text']}\" appeared.", result)


async def _wait_for_url(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.wait_for_url(str(args["pattern"]), timeout=opt_timeout(args))
    except BrowserError as exc:
        return refusal(exc, "browser_wait_for_url")
    return ok("wait_for_url", f"The page is at {result['url']}.", result)


async def _wait_for_load_state(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.wait_for_load_state(args.get("state") or "load", timeout=opt_timeout(args))
    except BrowserError as exc:
        return refusal(exc, "browser_wait_for_load_state")
    return ok("wait_for_load_state", f"Page reached {result['state']}.", result)


async def _wait_for_navigation(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.wait_for_navigation(timeout=opt_timeout(args))
    except BrowserError as exc:
        return refusal(exc, "browser_wait_for_navigation")
    return ok("wait_for_navigation", "Navigation completed.", result)


async def _wait_for_network(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.wait_for_network(timeout=opt_timeout(args))
    except BrowserError as exc:
        return refusal(exc, "browser_wait_for_network")
    return ok("wait_for_network", "Network settled.", result)


async def _wait_for_popup(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.wait_for_popup(timeout=opt_timeout(args))
    except BrowserError as exc:
        return refusal(exc, "browser_wait_for_popup")
    return ok("wait_for_popup", f"A new window opened ({result['tabId']}).", result)


async def _wait_for_download(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.wait_for_download(timeout=opt_timeout(args))
    except BrowserError as exc:
        return refusal(exc, "browser_wait_for_download")
    return ok("wait_for_download", f"Downloaded to {result.get('path')}.", result)


# ── Tabs / windows ───────────────────────────────────────────────────────────


async def _tabs(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    tabs = session.tabs_list()
    text = "\n".join(f"{t['id']} {t['url']} {'(active)' if t['active'] else ''}" for t in tabs) or "No tabs."
    return ok("tabs", text, {"tabs": tabs, "activeTab": session.active_tab})


async def _new_tab(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    result = await session.new_tab(args.get("url"))
    return ok("new_tab", f"Opened tab {result['id']}.", result)


async def _switch_tab(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.switch_tab(str(args["tab_id"]))
    except BrowserError as exc:
        return refusal(exc, "browser_switch_tab")
    return ok("switch_tab", f"Switched to {args['tab_id']}.", result)


async def _close_tab(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    result = await session.close_tab(args.get("tab_id"))
    return ok("close_tab", f"Closed tab {result['closed']}.", result)


# ── Files ────────────────────────────────────────────────────────────────────


async def _download(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    allowed, gate = await require_permission(ctx, session, "download", url=session.current_url(), tool="browser_download")
    if not allowed:
        return gate  # type: ignore[return-value]
    try:
        result = await session.download(args.get("target"), timeout=opt_timeout(args))
    except BrowserError as exc:
        return refusal(exc, "browser_download")
    await emit(ctx, "browser.downloaded", {"sessionId": session.id, "path": result.get("path"), "size": result.get("size")})
    return ok("download", f"Downloaded {result.get('filename')} to {result.get('path')}.", result)


async def _upload(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    allowed, gate = await require_permission(ctx, session, "upload", url=session.current_url(), detail=str(args.get("files")), tool="browser_upload")
    if not allowed:
        return gate  # type: ignore[return-value]
    files = [str(f) for f in (args.get("files") or [])]
    resolved = resolve_upload_paths(ctx, files)
    if resolved is None:
        return refusal(BrowserError("Those files aren't inside the task's own folder.", action="upload", code="BROWSER_UPLOAD_OUTSIDE_WORKSPACE"), "browser_upload")
    try:
        result = await session.upload(args.get("target"), resolved, timeout=opt_timeout(args))
    except BrowserError as exc:
        return refusal(exc, "browser_upload")
    return ok("upload", f"Uploaded {result['count']} file(s).", result)


# ── Debugging ────────────────────────────────────────────────────────────────


async def _console(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    entries = session.console_log(level=args.get("level"), limit=int(args.get("limit") or 200))
    text = wrap_untrusted("\n".join(f"[{e['type']}] {e['text']}" for e in entries), source="page console") or "No console messages."
    return ok("console", text, {"entries": entries, "count": len(entries)})


async def _network(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    entries = session.network_log(kind=args.get("kind"), limit=int(args.get("limit") or 200))
    text = wrap_untrusted("\n".join(f"{e.get('method', '')} {e.get('status', e.get('kind', ''))} {e.get('url', '')}" for e in entries), source="page network") or "No network activity."
    return ok("network", text, {"entries": entries, "count": len(entries)})


async def _errors(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    entries = session.error_log(limit=int(args.get("limit") or 100))
    text = wrap_untrusted("\n".join(f"{e['message']}" for e in entries), source="page errors") or "No page errors."
    return ok("errors", text, {"errors": entries, "count": len(entries)})


async def _evaluate(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    allowed, gate = await require_permission(ctx, session, "evaluate_js", url=session.current_url(), detail=str(args.get("expression"))[:100], tool="browser_evaluate")
    if not allowed:
        return gate  # type: ignore[return-value]
    try:
        result = await session.evaluate(str(args["expression"]), arg=args.get("arg"))
    except BrowserError as exc:
        return refusal(exc, "browser_evaluate")
    return ok("evaluate", wrap_untrusted(str(result)[:4000], source="script result"), {"result": result})


async def _cdp(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    method = str(args["method"])
    domain = method.split(".", 1)[0]
    if domain == "Network":
        allowed, gate = await require_permission(ctx, session, "network_inspection", tool="browser_cdp")
        if not allowed:
            return gate  # type: ignore[return-value]
    elif domain == "Runtime":
        allowed, gate = await require_permission(ctx, session, "evaluate_js", tool="browser_cdp")
        if not allowed:
            return gate  # type: ignore[return-value]
    try:
        result = await session.cdp(method, args.get("params") if isinstance(args.get("params"), dict) else None)
    except BrowserError as exc:
        return refusal(exc, "browser_cdp")
    return ok("cdp", f"Sent {method}.", {"method": method, "result": result})


async def _exec(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    mgr = manager()
    allowed, gate = await require_permission(ctx, session, "evaluate_js", url=session.current_url(), tool="browser_exec")
    if not allowed:
        return gate  # type: ignore[return-value]
    try:
        steps = exec_mod.parse_program(args.get("program"))
    except BrowserError as exc:
        return refusal(exc, "browser_exec")
    result = await exec_mod.run_program(
        session, steps,
        max_steps=int(args.get("max_steps") or mgr.config.max_steps),
        timeout_s=int(args.get("timeout") or mgr.config.max_execution_seconds),
        cancel=getattr(ctx, "_cancel_event", None),
        trace=session.trace,
    )
    await emit(ctx, "browser.exec", {"sessionId": session.id, "steps": result.steps_run, "success": result.success})
    if not result.success:
        return refusal({
            "code": (result.error or {}).get("code", "BROWSER_EXECUTION_FAILED"),
            "message": (result.error or {}).get("message", "The program stopped."),
            **result.to_dict(),
        }, "browser_exec")
    summary = "\n".join(f"- {r['op']}: {'ok' if r.get('ok') else r.get('error')}" for r in result.results)
    return ok("exec", f"Ran {result.steps_run} browser step(s).\n{summary}", result.to_dict())


async def _dialog(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.dialog(str(args["action"]), text=args.get("text"))
    except BrowserError as exc:
        return refusal(exc, "browser_dialog")
    if not result.get("handled"):
        return ok("dialog", "No dialog was waiting.", {"pending": False})
    return ok("dialog", f"Handled the page dialog ({result['action']}).", result)


# ── Storage / permissions / interception ─────────────────────────────────────


async def _cookies(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    action = args.get("action") or "list"
    try:
        if action == "list":
            allowed, gate = await require_permission(ctx, session, "read_cookies", tool="browser_cookies")
            if not allowed:
                return gate  # type: ignore[return-value]
            cookies = await session.cookies(args.get("urls") if isinstance(args.get("urls"), list) else None)
            safe = [{"name": c.get("name"), "domain": c.get("domain"), "path": c.get("path"),
                     "secure": c.get("secure"), "httpOnly": c.get("httpOnly"), "value": "«redacted»"} for c in cookies]
            return ok("cookies", f"{len(safe)} cookie(s). Values hidden.", {"cookies": safe, "count": len(safe)})
        if action == "set":
            allowed, gate = await require_permission(ctx, session, "write_cookies", tool="browser_cookies")
            if not allowed:
                return gate  # type: ignore[return-value]
            cookie = args.get("cookie")
            if not isinstance(cookie, dict):
                return refusal(BrowserError("A cookie object is required.", action="cookies", code="BROWSER_INVALID_INPUT"), "browser_cookies")
            await session.set_cookie(cookie)
            return ok("cookies", "Cookie set.", {"set": 1})
        allowed, gate = await require_permission(ctx, session, "write_cookies", tool="browser_cookies")
        if not allowed:
            return gate  # type: ignore[return-value]
        await session.clear_cookies()
        return ok("cookies", "Cookies cleared.", {"cleared": True})
    except BrowserError as exc:
        return refusal(exc, "browser_cookies")


async def _storage(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    data = await session.storage()
    text = wrap_untrusted(f"localStorage: {len(data.get('local', {}))} key(s); sessionStorage: {len(data.get('session', {}))} key(s).", source="storage")
    return ok("storage", text, {"keys": {"local": list(data.get("local", {}))[:50], "session": list(data.get("session", {}))[:50]}})


async def _permissions(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    try:
        result = await session.permissions(
            grant=args.get("grant") if isinstance(args.get("grant"), list) else None,
            revoke=bool(args.get("revoke")),
        )
    except BrowserError as exc:
        return refusal(exc, "browser_permissions")
    return ok("permissions", f"Granted: {result['granted'] or 'none'}.", result)


async def _intercept(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    session, error = session_of(args)
    if error:
        return error
    allowed, gate = await require_permission(ctx, session, "network_inspection", url=session.current_url(), tool="browser_intercept")
    if not allowed:
        return gate  # type: ignore[return-value]
    action = str(args["action"])
    page = session.page()
    try:
        if action == "block":
            await page.route(str(args.get("url_pattern") or "**/*"), lambda route: route.abort())
        elif action == "headers":
            headers = args.get("headers") if isinstance(args.get("headers"), dict) else {}
            await page.set_extra_http_headers({str(k): str(v) for k, v in headers.items()})
        elif action == "throttle":
            cdp = await page.context.new_cdp_session(page)
            await cdp.send("Network.emulateNetworkConditions", {
                "offline": False, "latency": int(args.get("latency_ms") or 200),
                "downloadThroughput": int((args.get("throughput_kbps") or 1024) * 128),
                "uploadThroughput": int((args.get("throughput_kbps") or 1024) * 128),
            })
        elif action == "offline":
            await page.context.set_offline(True)
        elif action == "clear":
            await page.unroute("**/*")
            await page.context.set_offline(False)
    except Exception as exc:  # noqa: BLE001
        return refusal(BrowserError("Eclipse couldn't change how the page loads.", code="BROWSER_SESSION_ERROR", action="intercept", metadata={"error": str(exc)[:200]}), "browser_intercept")
    return ok("intercept", f"Network control applied ({action}).", {"action": action})


# ── Handler table ────────────────────────────────────────────────────────────

_HANDLERS: dict[str, Any] = {
    "browser_launch": _launch,
    "browser_close": _close,
    "browser_status": _status,
    "browser_navigate": _navigate,
    "browser_stop": _stop,
    "browser_back": _make_simple_nav("go_back", "browser_back", "Went back"),
    "browser_forward": _make_simple_nav("go_forward", "browser_forward", "Went forward"),
    "browser_refresh": _make_simple_nav("reload", "browser_refresh", "Refreshed"),
    "browser_snapshot": _snapshot,
    "browser_extract": _extract,
    "browser_screenshot": _screenshot,
    "browser_vision": _vision,
    "browser_visual_find": _visual_find,
    "browser_visual_click": _visual_click,
    "browser_get_images": _make_simple_get("get_images", "browser_get_images"),
    "browser_get_text": _make_simple_get("get_text", "browser_get_text"),
    "browser_get_links": _make_simple_get("get_links", "browser_get_links"),
    "browser_get_forms": _make_simple_get("get_forms", "browser_get_forms"),
    "browser_get_accessibility_tree": _make_simple_get("get_accessibility_tree", "browser_get_accessibility_tree"),
    "browser_get_dom": _get_dom,
    "browser_click": _click,
    "browser_type": _type,
    "browser_fill": _type,
    "browser_select": _select,
    "browser_check": lambda a, c: _check(a, c, checked=True),
    "browser_uncheck": lambda a, c: _check(a, c, checked=False),
    "browser_press": _press,
    "browser_hover": _hover,
    "browser_scroll": _scroll,
    "browser_drag": _drag,
    "browser_wait": _wait,
    "browser_wait_for_element": _wait_for_element,
    "browser_wait_for_text": _wait_for_text,
    "browser_wait_for_url": _wait_for_url,
    "browser_wait_for_load_state": _wait_for_load_state,
    "browser_wait_for_navigation": _wait_for_navigation,
    "browser_wait_for_network": _wait_for_network,
    "browser_wait_for_popup": _wait_for_popup,
    "browser_wait_for_download": _wait_for_download,
    "browser_tabs": _tabs,
    "browser_new_tab": _new_tab,
    "browser_switch_tab": _switch_tab,
    "browser_close_tab": _close_tab,
    "browser_new_window": _new_tab,
    "browser_switch_window": _switch_tab,
    "browser_download": _download,
    "browser_upload": _upload,
    "browser_console": _console,
    "browser_network": _network,
    "browser_errors": _errors,
    "browser_evaluate": _evaluate,
    "browser_cdp": _cdp,
    "browser_exec": _exec,
    "browser_dialog": _dialog,
    "browser_cookies": _cookies,
    "browser_storage": _storage,
    "browser_permissions": _permissions,
    "browser_intercept": _intercept,
    **ADMIN_HANDLERS,
}


# `browser_fill` shares `_type` but must ignore the `submit` flag when absent.
async def _fill(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    return await _type({**args, "clear": args.get("clear", True)}, ctx)


_HANDLERS["browser_fill"] = _fill


def register_browser_tools(registry: ToolRegistry) -> list[str]:
    """Register the browser toolset. Returns the names added.

    Disabled when the operator turns the capability off, so the model is never
    told about a tool the runtime will refuse.
    """
    if not config_mod.browser_enabled():
        return []
    added: list[str] = []
    for name, schema in INPUT_SCHEMAS.items():
        handler = _HANDLERS.get(name)
        if handler is None:
            continue
        meta = TOOL_META.get(name, {})
        definition = ToolDefinition(
            name=name,
            description=str(meta.get("desc") or name),
            input_schema=schema,
            handler=handler,
            permission="read" if not meta.get("effect") else "external_action",
            risk=str(meta.get("risk") or "low"),
            timeout_ms=int(meta.get("timeout") or 30_000),
            effect=meta.get("effect"),
        )
        if registry.get(name) is not None:
            continue
        registry.register(definition)
        added.append(name)
    return added


__all__ = ["register_browser_tools"]
