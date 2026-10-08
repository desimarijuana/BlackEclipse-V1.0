"""Browser-workflow grader.

Deterministic state assertions over the browser trajectory: navigation, the final
URL, page identity, clicks/form input, downloads and multi-step workflow state.
Browser events come from the real Browser Runtime; when a task has no browser
evidence the result is UNKNOWN.
"""

from __future__ import annotations

from typing import Any

from . import GradeContext, Grader, GraderResult


class BrowserGrader(Grader):
    name = "browser"

    def grade(self, ctx: GradeContext) -> GraderResult:
        spec = dict(self.config.get("browser") or getattr(ctx.task, "metadata", {}).get("browser") or {})
        if not spec:
            return GraderResult.unmeasured_result(self.name, "task declares no browser assertions")

        browser_events = [e for e in getattr(ctx.trajectory, "events", []) if e.type.startswith("browser.")]
        if not browser_events and not ctx.env_state.get("browser"):
            return GraderResult.unmeasured_result(self.name, "no browser evidence in trajectory or state")

        # Collect a flat view: event payloads + environment browser state.
        observed: dict[str, Any] = {"events": [e.data for e in browser_events]}
        if isinstance(ctx.env_state, dict) and ctx.env_state.get("browser"):
            observed["state"] = ctx.env_state["browser"]

        failures: list[str] = []

        expected_url = spec.get("expected_url")
        if expected_url:
            got = _last_url(browser_events)
            if not got or not str(got).startswith(str(expected_url)):
                failures.append(f"final url {got!r} does not match {expected_url!r}")

        includes = spec.get("expected_page_contains") or []
        text = " ".join(
            str((e.data or {}).get("text") or (e.data or {}).get("title") or "") for e in browser_events
        ) + " " + (ctx.final_output or "")
        for needle in includes:
            if needle not in text:
                failures.append(f"page did not contain {needle!r}")

        expected_actions = spec.get("expected_actions") or []
        actions = [
            (e.data or {}).get("action") or (e.data or {}).get("op")
            for e in browser_events
        ]
        for action in expected_actions:
            if action not in actions:
                failures.append(f"browser action missing: {action}")

        final_state = spec.get("final_state") or {}
        if final_state and isinstance(observed.get("state"), dict):
            for key, want in final_state.items():
                if observed["state"].get(key) != want:
                    failures.append(f"final state {key}={observed['state'].get(key)!r} != {want!r}")

        passed = not failures
        return GraderResult(self.name, 1.0 if passed else 0.0, passed,
                            details={"observed": observed}, failures=failures)


def _last_url(events: list[Any]) -> Any:
    url = None
    for event in events:
        data = event.data or {}
        url = data.get("url") or data.get("finalUrl") or url
    return url
