"""Action verification — action → observe → verify.

A click must not blindly report success. Before an action the runtime captures a
light bounded `PageState`; after it, the verifier checks what the caller expected
(URL change, navigation, an element appearing/disappearing, text appearing, a
dialog, a download, or any page-state change) and returns a structured result.

The verifier is provider-agnostic: it works on any object exposing `url()` and
`title()`, plus the session's snapshot engine — so it is identical for local
Chromium, CDP, or a cloud provider.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class PageState:
    url: str = ""
    title: str = ""
    text_len: int = 0
    element_count: int = 0
    text_digest: str = ""
    dialog_pending: bool = False

    def fingerprint(self) -> str:
        raw = f"{self.url}|{self.title}|{self.text_len}|{self.element_count}|{self.text_digest}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class ActionVerification:
    success: bool
    action: str
    state_changed: bool
    checks: list[dict[str, Any]] = field(default_factory=list)
    evidence: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "action": self.action,
            "state_changed": self.state_changed,
            "checks": self.checks,
            "evidence": self.evidence,
            "summary": self.summary,
            "warnings": self.warnings,
        }


class Verifier:
    """Captures before/after page state and verifies an action."""

    async def capture(self, page: Any, snapshot_engine: Any = None, *, dialog_pending: bool = False) -> PageState:
        url = ""
        title = ""
        try:
            url = page.url
        except Exception:  # noqa: BLE001
            pass
        try:
            title = await page.title()
        except Exception:  # noqa: BLE001
            pass
        text_len = 0
        element_count = 0
        digest = ""
        if snapshot_engine is not None:
            snapshot = snapshot_engine.latest
            if snapshot is not None:
                text_len = snapshot.chars
                element_count = len(snapshot.elements)
                digest = hashlib.sha256(snapshot.full_text.encode("utf-8")).hexdigest()[:16]
        return PageState(
            url=url, title=title, text_len=text_len, element_count=element_count,
            text_digest=digest, dialog_pending=dialog_pending,
        )

    async def verify(
        self,
        page: Any,
        before: PageState,
        *,
        action: str,
        expect: Optional[dict[str, Any]] = None,
        snapshot_engine: Any = None,
        after: Optional[PageState] = None,
        dialog_pending: bool = False,
        download_started: bool = False,
    ) -> ActionVerification:
        """Verify an action against the page's new state."""
        expect = expect or {}
        result = ActionVerification(success=True, action=action, state_changed=False)
        new = after or await self.capture(page, snapshot_engine, dialog_pending=dialog_pending)

        url_changed = new.url != before.url
        digest_changed = new.text_digest != before.text_digest
        state_changed = url_changed or digest_changed or new.element_count != before.element_count \
            or new.text_len != before.text_len or new.dialog_pending != before.dialog_pending
        result.state_changed = state_changed

        # Default check: an action that changed nothing is reported honestly.
        result.checks.append({"name": "state_changed", "passed": state_changed, "value": state_changed})
        result.evidence.append({"kind": "url", "before": before.url, "after": new.url})

        if expect.get("url") is not None:
            passed = new.url == expect["url"]
            result.checks.append({"name": "url_equals", "passed": passed, "expected": expect["url"], "actual": new.url})
            if not passed:
                result.success = False
        if expect.get("urlContains"):
            needle = str(expect["urlContains"])
            passed = needle in (new.url or "")
            result.checks.append({"name": "url_contains", "passed": passed, "expected": needle, "actual": new.url})
            if not passed:
                result.success = False
        if expect.get("urlChanged") is True:
            result.checks.append({"name": "url_changed", "passed": url_changed, "actual": new.url})
            if not url_changed:
                result.success = False
        if expect.get("titleContains"):
            needle = str(expect["titleContains"])
            passed = needle.lower() in (new.title or "").lower()
            result.checks.append({"name": "title_contains", "passed": passed, "expected": needle, "actual": new.title})
            if not passed:
                result.success = False
        if expect.get("elementAppears"):
            found = await self._target_present(page, expect["elementAppears"], snapshot_engine)
            result.checks.append({"name": "element_appears", "passed": found, "target": expect["elementAppears"]})
            if not found:
                result.success = False
        if expect.get("elementDisappears"):
            found = await self._target_present(page, expect["elementDisappears"], snapshot_engine)
            result.checks.append({"name": "element_disappears", "passed": not found, "target": expect["elementDisappears"]})
            if found:
                result.success = False
        if expect.get("textAppears"):
            needle = str(expect["textAppears"])
            found = False
            try:
                found = await page.get_by_text(needle, exact=False).count() > 0
            except Exception:  # noqa: BLE001
                found = False
            result.checks.append({"name": "text_appears", "passed": found, "expected": needle})
            if not found:
                result.success = False
        if expect.get("dialogAppeared") is True:
            result.checks.append({"name": "dialog_appeared", "passed": bool(new.dialog_pending)})
            if not new.dialog_pending:
                result.success = False
        if expect.get("downloadStarted") is True:
            result.checks.append({"name": "download_started", "passed": bool(download_started)})
            if not download_started:
                result.success = False
        if expect.get("stateChanged") is True:
            result.checks.append({"name": "state_changed_required", "passed": state_changed})
            if not state_changed:
                result.success = False

        if not result.success:
            failed = [c["name"] for c in result.checks if not c.get("passed")]
            result.warnings.append("Some expected effects did not occur: " + ", ".join(failed))
            result.summary = "The action ran but the page may not have changed as expected."
        elif state_changed:
            result.summary = "The page changed after the action."
        else:
            result.summary = "The action ran; the page shows no visible change."
        return result

    async def _target_present(self, page: Any, target: Any, snapshot_engine: Any) -> bool:
        from .resolver import Resolver, Target  # noqa: PLC0415

        parsed = Target.parse(target)
        resolver = Resolver(snapshot_engine)
        found = resolver._locator_for(page, parsed)  # noqa: SLF001 - shared resolution
        if found is None:
            return False
        try:
            return await found[0].count() >= 1
        except Exception:  # noqa: BLE001
            return False


__all__ = ["ActionVerification", "PageState", "Verifier"]
