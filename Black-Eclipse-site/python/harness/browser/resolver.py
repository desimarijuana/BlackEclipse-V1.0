"""The locator / element-resolution engine.

Resolves an agent's target — a stable snapshot reference (`@e4`), an
accessibility role+name, a label, text, placeholder, test id, CSS, XPath, or
coordinates — to a live Playwright locator, in a PREFERRED order. The runtime
re-resolves a stale element instead of blindly failing.

Preferred order (highest confidence first):

    snapshot reference → accessibility role/name → label → text → placeholder
    → test id → CSS → XPath → coordinates (visual fallback)

Each resolution reports the strategy used and a confidence, so the resolver can
fuse DOM and vision evidence and the trace can show WHY an element was chosen.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from .errors import BrowserElementNotFoundError

# Strategy confidence weights (used by the vision fusion in `vision.py`).
STRATEGY_CONFIDENCE: dict[str, float] = {
    "ref": 0.97,
    "role_name": 0.93,
    "label": 0.90,
    "testid": 0.90,
    "placeholder": 0.85,
    "text": 0.80,
    "css": 0.75,
    "xpath": 0.70,
    "coordinates": 0.55,
    "vision": 0.60,
}


@dataclass
class Target:
    """A parsed target specification."""

    ref: Optional[str] = None
    role: Optional[str] = None
    name: Optional[str] = None
    text: Optional[str] = None
    label: Optional[str] = None
    placeholder: Optional[str] = None
    testid: Optional[str] = None
    css: Optional[str] = None
    xpath: Optional[str] = None
    alt: Optional[str] = None
    title: Optional[str] = None
    coordinates: Optional[tuple[float, float]] = None
    exact: bool = False

    @classmethod
    def parse(cls, raw: Any) -> "Target":
        """Parse a string or object target. A bare `@eN` is a ref; a bare string
        with no `@` is treated as visible text."""
        if raw is None:
            return cls()
        if isinstance(raw, str):
            text = raw.strip()
            if text.startswith("@e"):
                return cls(ref=text)
            if text.startswith("ref="):
                return cls(ref="@" + text[4:].lstrip("@"))
            return cls(text=text)
        if isinstance(raw, dict):
            coords = raw.get("coordinates")
            coordinates: Optional[tuple[float, float]] = None
            if isinstance(coords, dict) and "x" in coords and "y" in coords:
                coordinates = (float(coords["x"]), float(coords["y"]))
            elif isinstance(coords, (list, tuple)) and len(coords) == 2:
                coordinates = (float(coords[0]), float(coords[1]))
            return cls(
                ref=raw.get("ref"),
                role=raw.get("role"),
                name=raw.get("name"),
                text=raw.get("text"),
                label=raw.get("label"),
                placeholder=raw.get("placeholder"),
                testid=raw.get("testid") or raw.get("testId"),
                css=raw.get("css") or raw.get("selector"),
                xpath=raw.get("xpath"),
                alt=raw.get("alt"),
                title=raw.get("title"),
                coordinates=coordinates,
                exact=bool(raw.get("exact")),
            )
        return cls()

    def describe(self) -> str:
        parts = []
        for key in ("ref", "role", "name", "label", "text", "placeholder", "testid", "css", "xpath", "alt", "title"):
            value = getattr(self, key)
            if value:
                parts.append(f"{key}={value!r}")
        if self.coordinates:
            parts.append(f"coordinates={self.coordinates}")
        return ", ".join(parts) or "(empty target)"


@dataclass
class Resolution:
    """A resolved locator plus how it was found."""

    locator: Any
    strategy: str
    confidence: float
    target: Target
    count: int = 1
    re_resolved: bool = False
    meta: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "strategy": self.strategy,
            "confidence": self.confidence,
            "target": self.target.describe(),
            "count": self.count,
            "reResolved": self.re_resolved,
            **self.meta,
        }


class Resolver:
    """Resolves targets to Playwright locators against a live page."""

    def __init__(self, snapshot_engine: Any) -> None:
        self._snapshots = snapshot_engine

    def _locator_for(self, page: Any, target: Target) -> Optional[tuple[Any, str, float]]:
        """Return `(locator, strategy, confidence)` for the FIRST strategy that
        names the element, or None when the target carries no usable selector."""
        if target.ref:
            element = self._snapshots.resolve_ref(target.ref) if self._snapshots else None
            if element is not None and element.aria_ref:
                return page.locator(f"aria-ref={element.aria_ref}"), "ref", STRATEGY_CONFIDENCE["ref"]
            # A ref from a previous generation whose element is unknown: fall
            # through to whatever else the target carries, if anything.
        if target.role and target.name:
            return page.get_by_role(target.role, name=target.name, exact=target.exact), "role_name", STRATEGY_CONFIDENCE["role_name"]
        if target.label:
            return page.get_by_label(target.label, exact=target.exact), "label", STRATEGY_CONFIDENCE["label"]
        if target.testid:
            return page.get_by_test_id(target.testid), "testid", STRATEGY_CONFIDENCE["testid"]
        if target.placeholder:
            return page.get_by_placeholder(target.placeholder, exact=target.exact), "placeholder", STRATEGY_CONFIDENCE["placeholder"]
        if target.alt:
            return page.get_by_alt_text(target.alt, exact=target.exact), "text", STRATEGY_CONFIDENCE["text"]
        if target.title:
            return page.get_by_title(target.title, exact=target.exact), "text", STRATEGY_CONFIDENCE["text"]
        if target.text:
            return page.get_by_text(target.text, exact=target.exact), "text", STRATEGY_CONFIDENCE["text"]
        if target.css:
            return page.locator(target.css), "css", STRATEGY_CONFIDENCE["css"]
        if target.xpath:
            return page.locator(f"xpath={target.xpath}"), "xpath", STRATEGY_CONFIDENCE["xpath"]
        return None

    def resolve(self, page: Any, target: Target) -> Resolution:
        """Resolve a target, re-snapshotting once when a ref is stale."""
        found = self._locator_for(page, target)
        if found is None:
            raise BrowserElementNotFoundError(
                f"Eclipse couldn't find that element ({target.describe()}).",
                action="resolve",
            )
        locator, strategy, confidence = found
        return Resolution(locator=locator, strategy=strategy, confidence=confidence, target=target)

    async def resolve_verified(self, page: Any, target: Target, *, refresh_snapshot: Any = None) -> Resolution:
        """Resolve and confirm the locator matches at least one element.

        When a `@eN` ref does not resolve (the page changed), a fresh snapshot is
        taken and the element is re-resolved by its role+name — the recovery
        strategy for a stale reference. Raises when nothing matches.
        """
        resolution = self.resolve(page, target)
        try:
            count = await resolution.locator.count()
        except Exception as exc:  # noqa: BLE001 - an invalid selector is a not-found
            raise BrowserElementNotFoundError(
                f"Eclipse couldn't use that selector ({target.describe()}).",
                action="resolve", metadata={"error": str(exc)[:200]},
            ) from exc
        if count >= 1:
            resolution.count = count
            return resolution
        # Stale/missing: re-snapshot once and retry by role+name from the element.
        if target.ref and refresh_snapshot is not None:
            snapshot = await refresh_snapshot()
            element = snapshot.element(target.ref)
            if element is not None and element.role and element.name:
                retry = Target(role=element.role, name=element.name, exact=False)
                retry_locator, retry_strategy, retry_conf = self._locator_for(page, retry)
                if retry_locator is not None:
                    retry_count = await retry_locator.count()
                    if retry_count >= 1:
                        return Resolution(
                            locator=retry_locator, strategy=retry_strategy,
                            confidence=retry_conf * 0.95, target=target, count=retry_count,
                            re_resolved=True,
                            meta={"reResolvedFrom": target.ref, "role": element.role, "name": element.name},
                        )
        raise BrowserElementNotFoundError(
            f"Eclipse couldn't find that element on the page ({target.describe()}).",
            action="resolve", metadata={"strategy": resolution.strategy},
        )

    def candidates(self, page: Any, target: Target, limit: int = 20) -> list[Any]:
        """The locators a target matches (for `browser_find`/ambiguity reporting)."""
        found = self._locator_for(page, target)
        if found is None:
            return []
        locator = found[0]
        try:
            count = locator.count()
        except Exception:  # noqa: BLE001
            return []
        return [locator.nth(i) for i in range(min(count, limit))]


__all__ = ["Resolution", "Resolver", "STRATEGY_CONFIDENCE", "Target"]
