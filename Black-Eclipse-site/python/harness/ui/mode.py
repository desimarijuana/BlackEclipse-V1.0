"""Two-mode UI generation — deterministic Compose vs Engineer selection (Phase 6).

The agent must choose HOW to satisfy a UI request: **Compose** (arrange, configure
and lay out REGISTERED components over declarative blueprints — no source code) or
**Engineer** (the request needs genuinely new application functionality: a new
component, plugin, route, API, entity or integration — the privileged code path).

This selector is deterministic and model-free on purpose: it is a safety and
routing boundary, not a creative step. It errs toward Compose (the cheaper, safer
mode) and only escalates to Engineer on an explicit new-capability signal, so a
misread can never silently turn a configuration change into a source-code
release.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from .catalog import UiCatalog


class UiMode(str, Enum):
    COMPOSE = "compose"
    ENGINEER = "engineer"
    BOTH = "both"


#: Signals that a request needs NEW application functionality (source code).
_ENGINEER_SIGNALS = (
    "new component", "create a component", "build a component", "custom component",
    "doesn't exist", "does not exist", "not exist", "from scratch",
    "new plugin", "create a plugin", "build a plugin", "plugin",
    "backend", "server-side", "api endpoint", "new api", "endpoint", "route",
    "database", "schema", "migration", "new table", "entity", "persist",
    "worker", "background job", "scheduler", "cron", "webhook",
    "authentication", "oauth", "sign in", "login flow",
    "3d", "webgl", "interactive editor", "new editor", "custom visualization",
    "integration", "connect to",
)

#: Signals that a request is satisfiable by composing existing components.
_COMPOSE_SIGNALS = (
    "add widget", "add a widget", "add card", "add a card", "add a chart",
    "add a table", "add metric", "metric card", "add a metric",
    "remove widget", "delete widget", "remove the", "hide",
    "move", "reorder", "resize", "make it smaller", "make it bigger", "larger",
    "layout", "arrange", "rearrange", "dashboard", "workspace", "page",
    "filter", "configure", "set the", "change the color", "theme", "below",
    "above", "row", "column", "grid", "pin", "duplicate",
)

_NOT_A_UI_REQUEST = (
    "stock", "price", "earnings", "portfolio value", "news about",
    "backtest", "valuation",
)


@dataclass
class ModeDecision:
    mode: UiMode
    reasons: list[str] = field(default_factory=list)
    suggested_tools: list[str] = field(default_factory=list)
    confidence: float = 0.5
    matched_components: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "reasons": self.reasons,
            "suggestedTools": self.suggested_tools,
            "confidence": round(self.confidence, 2),
            "matchedComponents": self.matched_components,
        }


_COMPOSE_TOOLS = ["ui_get_current_page", "ui_get_component_catalog", "ui_add_widget", "ui_move_widget", "ui_preview_change", "ui_save_layout"]
_ENGINEER_TOOLS = ["code_search", "code_edit", "scaffold_kit", "ui_get_component_catalog", "ui_create_page", "ui_add_widget"]


def _hits(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [p for p in phrases if p in text]


def classify_request(text: str, *, catalog: Optional[UiCatalog] = None, existing_components: Optional[list[str]] = None) -> ModeDecision:
    """Classify a natural-language UI request into Compose / Engineer / both."""
    lowered = (text or "").lower().strip()
    if not lowered:
        return ModeDecision(mode=UiMode.COMPOSE, reasons=["empty request defaults to Compose"], confidence=0.2)

    engineer_hits = _hits(lowered, _ENGINEER_SIGNALS)
    compose_hits = _hits(lowered, _COMPOSE_SIGNALS)

    # If the request names a component that ALREADY exists, it is composable —
    # unless it also carries an explicit new-capability signal.
    matched: list[str] = []
    known: set[str] = set(existing_components or [])
    if catalog is not None:
        known.update(s.id for s in catalog.list())
    for component_id in known:
        if re.search(rf"(?<![a-z0-9]){re.escape(component_id.lower())}(?![a-z0-9])", lowered):
            matched.append(component_id)

    if engineer_hits and not compose_hits:
        return ModeDecision(
            mode=UiMode.ENGINEER,
            reasons=[f"new-capability signal(s): {', '.join(engineer_hits[:4])}"],
            suggested_tools=list(_ENGINEER_TOOLS), confidence=0.75, matched_components=matched,
        )
    if engineer_hits and compose_hits:
        return ModeDecision(
            mode=UiMode.BOTH,
            reasons=[
                f"new-capability signal(s): {', '.join(engineer_hits[:4])}",
                f"compose signal(s): {', '.join(compose_hits[:4])}",
            ],
            suggested_tools=list(dict.fromkeys([*_ENGINEER_TOOLS, *_COMPOSE_TOOLS])),
            confidence=0.6, matched_components=matched,
        )
    if compose_hits or matched:
        return ModeDecision(
            mode=UiMode.COMPOSE,
            reasons=(
                [f"compose signal(s): {', '.join(compose_hits[:4])}"]
                if compose_hits else [f"references existing component(s): {', '.join(matched[:4])}"]
            ),
            suggested_tools=list(_COMPOSE_TOOLS), confidence=0.8 if compose_hits else 0.7,
            matched_components=matched,
        )
    # No signal: prefer the cheaper, safer mode.
    return ModeDecision(
        mode=UiMode.COMPOSE,
        reasons=["no new-capability signal; defaulting to Compose (prefer the cheaper mode)"],
        suggested_tools=list(_COMPOSE_TOOLS), confidence=0.3, matched_components=matched,
    )


__all__ = ["ModeDecision", "UiMode", "classify_request"]
