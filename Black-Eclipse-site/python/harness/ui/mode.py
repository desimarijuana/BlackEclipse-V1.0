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
    # A widget the catalog does not have yet is a NEW capability, exactly like a
    # new component: "create a new widget", "build a widget that shows …".
    "new widget", "create a widget", "build a widget", "custom widget", "widget that",
    # Authoring a tool/integration is always the privileged code path.
    "new tool", "create a tool", "build a tool", "custom tool",
    "doesn't exist", "does not exist", "not exist", "from scratch",
    "new plugin", "create a plugin", "build a plugin", "plugin",
    "backend", "server-side", "api endpoint", "new api", "endpoint", "route",
    "database", "schema", "migration", "new table", "entity", "persist",
    "worker", "background job", "scheduler", "cron", "webhook",
    "authentication", "oauth", "sign in", "login flow",
    "3d", "webgl", "interactive editor", "new editor", "custom visualization",
    "integration", "connect to",
    # A request for NEW interaction (user-driven input) needs a component the
    # read-only widget catalog does not have, so it is a new capability — not an
    # arrangement of existing charts. Without these, "a calculator I can drive
    # with sliders" classified as Compose and died with no task (a recorded gap).
    "slider", "sliders", "input field", "text input", "number input",
    "user input", "user-driven", "user driven", "driven with",
    "interactive input", "interactive form", "live input", "adjustable",
    "calculator", "control panel",
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
    # Restyling/rearranging an EXISTING widget is a compose request, not a new
    # capability — the agent changes config/layout rather than writing code.
    "change the design", "redesign", "restyle", "change the style", "change the look",
)

_NOT_A_UI_REQUEST = (
    "stock", "price", "earnings", "portfolio value", "news about",
    "backtest", "valuation",
)

#: Verbs that introduce a NEW thing on the page. Layout/restyle verbs are
#: deliberately absent: moving or restyling an EXISTING widget does not need a
#: catalog witness because the target is the page the user is looking at.
_ADDITIVE_VERBS = (
    "add", "create", "build", "make", "put", "place", "insert", "include",
    "show", "display", "need", "want",
)

#: Nouns that name a UI *shape*, not a capability. "add a widget" is a generic
#: compose request; "add a clock" names a capability the catalog may not have.
_GENERIC_UI_NOUNS = frozenset({
    "widget", "widgets", "card", "cards", "chart", "charts", "table", "tables",
    "metric", "metrics", "panel", "panels", "page", "pages", "dashboard",
    "dashboards", "workspace", "workspaces", "view", "views", "list", "lists",
    "tile", "tiles", "module", "modules", "layout", "layouts", "section",
    "sections", "area", "areas", "part", "parts", "screen", "screens",
    "component", "components",
})

#: Words that carry no capability meaning in a UI request (verbs, articles,
#: prepositions, layout adjectives).
_STOPWORDS = frozenset({
    "the", "a", "an", "to", "on", "in", "of", "for", "my", "me", "and", "or",
    "with", "that", "this", "it", "is", "are", "be", "at", "top", "bottom",
    "left", "right", "up", "down", "please", "can", "you", "i", "we", "our",
    "some", "new", "using", "use", "like", "showing", "shows", "render",
    "renders", "want", "need", "more", "less", "small", "smaller", "big",
    "bigger", "large", "larger", "same", "current", "existing", "better",
    "improve", "fix", "update", "change", "make", "let", "from", "into",
    "over", "under", "below", "above", "between", "all", "any", "each",
    # Actions are never capability nouns.
    "add", "create", "build", "put", "place", "insert", "include", "show",
    "display", "move", "reorder", "resize", "restyle", "redesign",
    "configure", "filter", "hide", "remove", "delete", "arrange", "pin",
    "duplicate", "set", "then", "also",
})

_CLAUSE_SPLIT_RE = re.compile(r"[.!?;\n]+|\bthen\b|\band\b|\bbut\b", re.IGNORECASE)

#: "make me a new page" / "create a dashboard" compose a page; a component
#: request ("add a clock to the dashboard") does not match because a capability
#: noun sits between the verb and "dashboard".
_PAGE_OBJECT_RE = re.compile(
    r"\b(?:new|create|make|build|add)\s+(?:me\s+)?(?:a\s+|an\s+|the\s+)?"
    r"(?:new\s+)?(page|workspace|dashboard)\b",
)
_WORD_RE = re.compile(r"[a-z0-9][a-z0-9-]*")


@dataclass
class ModeDecision:
    mode: UiMode
    reasons: list[str] = field(default_factory=list)
    suggested_tools: list[str] = field(default_factory=list)
    confidence: float = 0.5
    matched_components: list[str] = field(default_factory=list)
    #: True when the request names a capability the catalog cannot satisfy. A
    #: Compose verdict with this flag is a routing defect: the request must be
    #: escalated, never refused as "nothing to engineer".
    capability_gap: bool = False

    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "reasons": self.reasons,
            "suggestedTools": self.suggested_tools,
            "confidence": round(self.confidence, 2),
            "matchedComponents": self.matched_components,
            "capabilityGap": self.capability_gap,
        }


@dataclass
class CapabilityFit:
    """Whether the catalog can satisfy the capability the request names."""

    satisfied: bool
    witness: list[str] = field(default_factory=list)
    capability_gap: bool = False
    reason: str = ""


_COMPOSE_TOOLS = ["ui_get_current_page", "ui_get_component_catalog", "ui_add_widget", "ui_move_widget", "ui_preview_change", "ui_save_layout"]
_ENGINEER_TOOLS = ["code_search", "code_edit", "scaffold_kit", "ui_get_component_catalog", "ui_create_page", "ui_add_widget"]

#: Public aliases so callers (e.g. the engineering escalator) do not import a
#: private name.
COMPOSE_TOOLS: tuple[str, ...] = tuple(_COMPOSE_TOOLS)
ENGINEER_TOOLS: tuple[str, ...] = tuple(_ENGINEER_TOOLS)


def _hits(text: str, phrases: tuple[str, ...]) -> list[str]:
    return [p for p in phrases if p in text]


def _content_tokens(text: str) -> list[str]:
    """The words that name a capability, with UI shape/grammar removed."""
    return [
        token for token in _WORD_RE.findall(text)
        if len(token) > 2
        and token not in _STOPWORDS
        and token not in _GENERIC_UI_NOUNS
    ]


def _is_additive(text: str) -> bool:
    return any(
        re.search(rf"(?<![a-z0-9]){re.escape(verb)}(?![a-z0-9])", text)
        for verb in _ADDITIVE_VERBS
    )


def _matches_token(haystack: str, token: str) -> bool:
    """Whole-word match, plus a conservative plural (trades -> trade)."""
    if re.search(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])", haystack):
        return True
    if token.endswith("s") and len(token) > 4:
        singular = token[:-1]
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(singular)}(?![a-z0-9])", haystack))
    return False


def _catalog_witness(tokens: list[str], catalog: UiCatalog) -> list[str]:
    """Registered component ids whose text matches at least one content token."""
    hits: list[str] = []
    for spec in catalog.list():
        haystack = " ".join([
            spec.id, spec.display_name, spec.description, spec.category,
            *spec.tags,
        ]).lower()
        if any(_matches_token(haystack, token) for token in tokens):
            hits.append(spec.id)
    return hits


def assess_capability(
    text: str,
    *,
    catalog: Optional[UiCatalog] = None,
    additive_only: bool = True,
) -> CapabilityFit:
    """Does the catalog hold a component for the capability this request names?

    Deterministic and model-free. The rule is deliberately narrow so it fixes
    the recorded defect without turning ordinary layout work into engineering:

    * a page/workspace request is composable (an empty page is valid);
    * a request that names no specific capability ("add a widget") is composable;
    * a generic UI noun is not a capability ("add a card" is composable);
    * a request that names a capability (``clock``) and matches no registered
      component is a GAP — and is escalated, never refused;
    * a layout/restyle request needs no witness (its target is the page).

    ``additive_only=False`` is the DIAGNOSTIC view: it looks for a capability
    the request names even when the additive phrasing was missed. The classifier
    never uses it (a layout clause must not become an escalation); the routing
    repair proposer does, to distinguish a vocabulary miss from a catalog gap.
    """
    lowered = (text or "").lower().strip()
    if not lowered:
        return CapabilityFit(True, reason="empty request")
    if catalog is None:
        return CapabilityFit(True, reason="no catalog to check against")
    if _PAGE_OBJECT_RE.search(lowered):
        return CapabilityFit(True, reason="page/workspace composition")

    # Only an ADDITIVE clause can introduce a new capability. A layout clause
    # ("move it", "make it smaller") must never be read as "make a clock".
    tokens: list[str] = []
    if additive_only:
        for clause in _CLAUSE_SPLIT_RE.split(lowered):
            if _is_additive(clause):
                tokens.extend(_content_tokens(clause))
    else:
        tokens = _content_tokens(lowered)
    if not tokens:
        return CapabilityFit(True, reason="no additive capability named")

    witness = _catalog_witness(tokens, catalog)
    if witness:
        return CapabilityFit(
            True, witness, False,
            f"registered component(s) match: {', '.join(witness[:4])}",
        )
    return CapabilityFit(
        False, [], True,
        f"no registered component matches: {', '.join(tokens[:4])}",
    )


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

    fit = assess_capability(lowered, catalog=catalog)

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

    # A specific capability the catalog cannot satisfy is a GAP: escalate. This
    # is the recorded "world clock" defect — a Compose verdict with no witness
    # became an authoritative refusal, and the turn had no tool to author one.
    # It runs AFTER the explicit new-capability signals so an engineer/both
    # verdict keeps its own reason and tool set.
    if fit.capability_gap and not matched:
        return ModeDecision(
            mode=UiMode.ENGINEER,
            reasons=[
                fit.reason,
                *([f"compose signal(s): {', '.join(compose_hits[:4])}"] if compose_hits else []),
            ],
            suggested_tools=list(_ENGINEER_TOOLS), confidence=0.7,
            matched_components=[], capability_gap=True,
        )

    if compose_hits or matched:
        witnesses = list(dict.fromkeys([*matched, *fit.witness]))
        return ModeDecision(
            mode=UiMode.COMPOSE,
            reasons=(
                [f"compose signal(s): {', '.join(compose_hits[:4])}"]
                if compose_hits else [f"references existing component(s): {', '.join(witnesses[:4])}"]
            ),
            suggested_tools=list(_COMPOSE_TOOLS), confidence=0.8 if compose_hits else 0.7,
            matched_components=witnesses,
        )
    # No signal: prefer the cheaper, safer mode.
    return ModeDecision(
        mode=UiMode.COMPOSE,
        reasons=["no new-capability signal; defaulting to Compose (prefer the cheaper mode)"],
        suggested_tools=list(_COMPOSE_TOOLS), confidence=0.3,
        matched_components=list(dict.fromkeys([*matched, *fit.witness])),
    )


__all__ = [
    "CapabilityFit",
    "COMPOSE_TOOLS",
    "ENGINEER_TOOLS",
    "ModeDecision",
    "UiMode",
    "assess_capability",
    "classify_request",
]
