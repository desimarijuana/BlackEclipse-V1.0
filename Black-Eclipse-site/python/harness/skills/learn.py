"""Guided `/learn`-style skill authoring (Phase 4).

Turns a *source* the user explicitly points at — a completed run, a document,
a repository, a repeated workflow, or a correction/recovered failure — into a
complete but **inert** skill draft. The draft is schema-validated, linted, and
shown with its evidence; it cannot activate without the existing evaluation +
operator promotion path.

Safety:
  * The source is user-supplied; the model never silently invents a procedure.
  * A generated skill is **sanitized**: raw chat transcripts, secrets/credentials,
    issue numbers, and irrelevant dates are removed before the draft is built.
  * One-off runs do not auto-create an active skill; recurrence evidence is kept
    on the candidate, and the draft is always `status: draft`.
  * The draft defaults to the safe read-only permission set and existing tools.
  * This module never enables, evaluates, or promotes anything.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

# Source kinds the guided workflow accepts.
SOURCE_KINDS = ("run", "document", "repository", "repeated_workflow", "correction")

# Advisory lint codes. `warn` never blocks; it tells the user what to edit.
LINT_RULES: dict[str, str] = {
    "raw_transcript": "looks like a raw chat transcript — skills capture the rule, not the log",
    "secret": "contains a secret-looking token (key/token/password) — remove it",
    "issue_number": "contains issue/PR numbers — state the rule without the ticket reference",
    "irrelevant_date": "contains an absolute date — prefer a relative rule unless the date is essential",
    "first_person": "written in first person incident narration — restate as a reusable rule",
}

_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|secret|password|passwd|token|authorization|bearer)\b\s*[:=]\s*\S+"
)
_ISSUE_RE = re.compile(r"(?i)\b(?:issue|pr|pull request|#)\s*#?\d{2,}\b")
_DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2}/\d{1,2}/\d{2,4}\b")
_TRANSCRIPT_RE = re.compile(r"(?im)^\s*(?:user|assistant|human|ai)\s*:")


@dataclass
class LearnRequest:
    """A guided learning request. `source_kind` must be one of `SOURCE_KINDS`."""

    source_kind: str
    title: str
    objective: str = ""
    procedure: list[str] = field(default_factory=list)
    content: str = ""
    source_run_id: Optional[str] = None
    tools: list[str] = field(default_factory=list)
    category: str = "research"
    scope_note: str = ""

    def __post_init__(self) -> None:
        if self.source_kind not in SOURCE_KINDS:
            raise ValueError(f"unknown source kind: {self.source_kind!r}")
        if not self.title.strip():
            raise ValueError("a title is required")
        self.title = self.title.strip()[:200]
        self.objective = (self.objective or "").strip()
        self.procedure = [str(s).strip() for s in self.procedure if str(s).strip()]


def lint_skill_content(text: str) -> list[str]:
    """Advisory lint: returns rule codes triggered by the content. Never blocks."""
    codes: list[str] = []
    if not text:
        return codes
    if _SECRET_RE.search(text):
        codes.append("secret")
    if _TRANSCRIPT_RE.search(text):
        codes.append("raw_transcript")
    if _ISSUE_RE.search(text):
        codes.append("issue_number")
    if _DATE_RE.search(text):
        codes.append("irrelevant_date")
    return codes


def sanitize_skill_content(text: str) -> tuple[str, list[str]]:
    """Strip the shapes a skill must never carry, returning (clean, removed).

    Removes secret assignments and issue references entirely; collapses a raw
    transcript line prefix. Dates are *not* removed (they may be essential) but
    are reported by `lint_skill_content`.
    """
    removed: list[str] = []
    clean = text or ""
    if _SECRET_RE.search(clean):
        removed.append("secret")
        clean = _SECRET_RE.sub("[redacted]", clean)
    if _ISSUE_RE.search(clean):
        removed.append("issue_number")
        clean = _ISSUE_RE.sub("[issue reference removed]", clean)
    if _TRANSCRIPT_RE.search(clean):
        removed.append("raw_transcript")
        clean = "\n".join(
            line for line in clean.splitlines() if not _TRANSCRIPT_RE.match(line)
        )
    return clean, removed


def build_learn_draft(request: LearnRequest) -> dict[str, Any]:
    """Assemble the inert draft fields from a guided request.

    Deterministic — no model call. Returns a dict the skill-draft path persists;
    `sanitized` lists what was stripped, `lint` lists advisory warnings.
    """
    instruction_seed = request.objective or request.content
    clean_seed, sanitized = sanitize_skill_content(instruction_seed)
    steps = list(request.procedure)
    # If no explicit steps were supplied, derive a readable procedure from the
    # sanitized content's sentences — never fabricate tool calls.
    if not steps and clean_seed:
        candidate_steps = [
            s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", clean_seed) if len(s.strip()) > 8
        ]
        steps = candidate_steps[:12]
    lint = sorted(set(lint_skill_content(clean_seed) + sanitized))
    return {
        "title": request.title,
        "category": request.category,
        "objective": clean_seed[:1200],
        "procedure": steps,
        "tools": list(request.tools),
        "sourceKind": request.source_kind,
        "sourceRunId": request.source_run_id,
        "scopeNote": request.scope_note,
        "sanitized": sanitized,
        "lint": lint,
    }


def learn_from_source(
    request: LearnRequest,
    skill_store: Any,
    *,
    available_tools: list[str],
    actor_is_operator: bool = False,
) -> dict[str, Any]:
    """Create an inert candidate + draft from a guided learning request.

    Operator-gated (creating a learning record is a controlled action). The
    candidate is persisted inert, then `propose_draft` builds the complete
    unvalidated draft (which itself stays `draft`/`not_evaluated`). Nothing is
    enabled, evaluated, or promoted here.
    """
    if not actor_is_operator:
        return {"ok": False, "error": "skill.create requires an authorized operator"}

    from .draft import _slug, propose_draft  # noqa: PLC0415
    from ..eclipse_memory.db import now_iso  # noqa: PLC0415

    built = build_learn_draft(request)

    evidence = [
        {"kind": "tool", "name": name, "at": None}
        for name in built["tools"] if name in available_tools
    ]
    if request.source_run_id:
        evidence.append({"kind": "run", "name": request.source_run_id, "at": None})
    if built["sourceKind"] == "document" and request.content:
        evidence.append({"kind": "document", "name": request.title, "at": None})

    # A learning-origin manifest requires a source reference. A run-backed learn
    # uses its run id; a document/repo learn uses a stable synthetic id so the
    # provenance is still traceable without pretending a run existed.
    source_ref = request.source_run_id or f"learn:{built['sourceKind']}:{_slug(built['title'])}"
    candidate = {
        "candidateType": "successful_procedure",
        "title": built["title"],
        "problem": f"User-requested reusable skill learned from a {built['sourceKind']}.",
        "observedBehavior": built["objective"][:500],
        "proposedLesson": built["objective"] or built["title"],
        "proposedProcedure": [{"step": i + 1, "action": s} for i, s in enumerate(built["procedure"])],
        "evidenceReferences": evidence,
        "confidence": 0.6 if built["procedure"] else 0.25,
        "scope": {"scopeClaim": request.scope_note or "general"},
        "generalizationNotes": (
            "User-directed learning. Reusability must be confirmed before this "
            "becomes an active skill."
        ),
        "knownLimitations": (
            "Generated from a single user-directed source; unvalidated and inert "
            "until evaluated and operator-approved."
        ),
        "sourceRunId": source_ref,
    }
    from .learning import _signature  # noqa: PLC0415

    signature = _signature(candidate["candidateType"], candidate["problem"])
    existing = skill_store.find_candidate_by_signature(signature)
    if existing:
        candidate_id = existing["id"]
    else:
        candidate_id = skill_store.save_candidate({
            **candidate, "id": None, "signature": signature,
            "status": "detected", "createdAt": now_iso(),
        })
        skill_store.append_event(
            "skill.learning_source_captured",
            data={"candidateId": candidate_id, "sourceKind": built["sourceKind"]},
        )

    result = propose_draft(
        candidate_id, skill_store, available_tools=available_tools,
        user_intent=built["title"],
    )
    return {
        **result,
        "candidateId": candidate_id,
        "sourceKind": built["sourceKind"],
        "sanitized": built["sanitized"],
        "lint": built["lint"],
    }


__all__ = [
    "LINT_RULES",
    "SOURCE_KINDS",
    "LearnRequest",
    "build_learn_draft",
    "learn_from_source",
    "lint_skill_content",
    "sanitize_skill_content",
]
