"""Cross-engine coordination — one routing policy for the three research surfaces (Phase 10.3).

Eclipse has three surfaces that can obtain information or act:

  * the **web-research engine** (`web_search`/`web_extract`/… — search finds
    pointers, a fetch turns a page into evidence, claims are verified);
  * the **browser** (`browser_*` — interactive, login-gated, form-driven pages
    that a plain fetch cannot reach);
  * the **computer-use engine** (`computer_*` — native desktop apps, terminals,
    and a screen/accessibility state that lives outside a browser).

They share ONE evidence store (the run's `source_sink` / the research
`EvidenceStore`) — there is deliberately no second provenance shape. This module
is the single documented hand-off rule: given a task, which surface should answer
it, and why. It is deterministic and explainable, so the choice is observable and
testable rather than buried in prompt wording.

The rule of thumb, in order:

    search finds → browser reads behind a login → computer-use reads a desktop app

A browser-extracted value is a CANDIDATE, never a verified fact: it can enter a
verified claim only through the engine's one legal path (`claim_verify`) — see
`browser/bridge.py`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# The three surfaces.
WEB = "web_research"
BROWSER = "browser"
COMPUTER = "computer_use"

_SURFACE_LABELS = {
    WEB: "the web-research engine",
    BROWSER: "the browser",
    COMPUTER: "computer-use",
}


@dataclass
class SurfaceRequest:
    """A description of the information/action a caller needs."""

    question: str = ""
    url: Optional[str] = None
    # The page needs interaction (a form, a login, a click-through) to reveal the
    # content, so a plain fetch is insufficient.
    interactive: bool = False
    # The content sits behind a sign-in.
    login_gated: bool = False
    # The information lives in a native desktop application or a terminal, not a
    # web page at all.
    native_app: bool = False
    # The page is JavaScript-rendered / canvas / otherwise not extractable as text.
    javascript_heavy: bool = False
    # The caller explicitly names the surface (honoured when it can serve the task).
    surface: Optional[str] = None


@dataclass
class Routing:
    surface: str
    rationale: str
    alternatives: list[str] = field(default_factory=list)
    evidence_path: str = "engine"  # "engine" | "browser_candidate"

    def to_dict(self) -> dict[str, Any]:
        return {
            "surface": self.surface,
            "surfaceLabel": _SURFACE_LABELS.get(self.surface, self.surface),
            "rationale": self.rationale,
            "alternatives": self.alternatives,
            "evidencePath": self.evidence_path,
        }


def route(request: SurfaceRequest) -> Routing:
    """Deterministically choose the surface that should answer/act.

    Native desktop first (only computer-use can reach it), then an interactive or
    login-gated page (only the browser can drive it), then the web-research engine
    as the default. A browser-read value is marked a candidate, not verified.
    """
    alternatives: list[str] = []

    # 1. A native app / terminal can only be reached by computer-use.
    if request.native_app:
        alternatives = [BROWSER, WEB]
        return Routing(
            surface=COMPUTER,
            rationale="The information lives in a desktop application, so computer-use must read it from the screen.",
            alternatives=alternatives,
        )

    # 2. A page that needs interaction or a login can only be driven by the browser.
    if request.interactive or request.login_gated:
        reason = "behind a sign-in" if request.login_gated else "needs interaction (a form, click-through or tabs)"
        return Routing(
            surface=BROWSER,
            rationale=(
                f"The page {reason}, so the browser must open and read it. The value it reads is a "
                "CANDIDATE; verify it through the research engine before treating it as a fact."
            ),
            alternatives=[WEB],
            evidence_path="browser_candidate",
        )

    # 3. JavaScript-heavy / canvas content is best rendered by the browser.
    if request.javascript_heavy:
        return Routing(
            surface=BROWSER,
            rationale=(
                "The page is JavaScript-rendered, so a plain fetch may miss it; the browser renders it. "
                "The value is a CANDIDATE until verified by the research engine."
            ),
            alternatives=[WEB],
            evidence_path="browser_candidate",
        )

    # 4. Default: the web-research engine (search finds, fetch extracts, claims verify).
    return Routing(
        surface=WEB,
        rationale="This is an ordinary web question, so the web-research engine searches, extracts and verifies.",
        alternatives=[BROWSER],
    )


def routing_policy() -> dict[str, Any]:
    """The documented routing policy, machine-readable (for docs/health)."""
    return {
        "summary": "search finds → browser reads behind a login → computer-use reads a desktop app",
        "surfaces": {
            WEB: "Search/extract/verify. Search results are pointers; a fetched page is evidence; claims are verified deterministically.",
            BROWSER: "Interactive, login-gated or JS-rendered pages. A browser-derived value is a candidate, verified only through the engine.",
            COMPUTER: "Native desktop apps and terminals. Screen/accessibility state is its own provenance, recorded on the same source sink.",
        },
        "evidence": "One store (the run's source_sink / EvidenceStore). No surface keeps a second provenance shape.",
        "verification": "Only the research engine's `claim_verify` can turn a candidate value into a verified claim.",
    }


__all__ = [
    "BROWSER",
    "COMPUTER",
    "Routing",
    "SurfaceRequest",
    "WEB",
    "route",
    "routing_policy",
]
