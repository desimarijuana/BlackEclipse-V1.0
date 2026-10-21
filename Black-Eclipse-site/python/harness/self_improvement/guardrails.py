"""Deterministic guardrails a live surface may enforce on a run.

A guardrail is a rule the RUNTIME checks, not a rule the model is told. A
violation fails the run with a named code and the answer is not shipped as a
completed result. Nothing here consults a model, and nothing here is a
permission: a guardrail can only reject an answer, never grant one.

The citation rule reuses the evaluator's own citation parser, so a guardrail
and the citation grader agree on what a citation IS.
"""

from __future__ import annotations

from typing import Any, Optional

GUARDRAILS: tuple[str, ...] = ("require_tool_before_answer", "require_citation")


def evaluate_guardrails(
    guardrails: Any,
    *,
    output: str = "",
    tool_calls: int = 0,
    max_answer_chars: Optional[int] = None,
) -> list[dict[str, Any]]:
    """The violations of `guardrails` for one finished answer (empty = none)."""
    violations: list[dict[str, Any]] = []
    names = [str(name) for name in (guardrails or ()) if str(name)]
    for name in names:
        if name == "require_tool_before_answer":
            if int(tool_calls or 0) < 1:
                violations.append({
                    "code": "GUARDRAIL_TOOL_REQUIRED",
                    "guardrail": name,
                    "detail": "the answer was produced without a tool call",
                })
        elif name == "require_citation":
            from ..evaluation.graders.citation import extract_citations  # noqa: PLC0415

            if not extract_citations(output or ""):
                violations.append({
                    "code": "GUARDRAIL_CITATION_MISSING",
                    "guardrail": name,
                    "detail": "the answer carries no citation",
                })
    if max_answer_chars is not None and int(max_answer_chars) > 0:
        length = len(output or "")
        if length > int(max_answer_chars):
            violations.append({
                "code": "GUARDRAIL_ANSWER_TOO_LONG",
                "guardrail": "max_answer_chars",
                "detail": (
                    f"the answer is {length} characters "
                    f"(limit {int(max_answer_chars)})"
                ),
            })
    return violations


def guardrail_error(violations: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """The run error for a guardrail violation (None when there is none)."""
    if not violations:
        return None
    first = violations[0]
    names = ", ".join(
        str(violation.get("guardrail") or "") for violation in violations
    )
    return {
        "code": str(first.get("code") or "GUARDRAIL_VIOLATION"),
        "message": str(first.get("detail") or "the answer broke a surface guardrail"),
        "detail": f"guardrail(s): {names}" if names else None,
    }


__all__ = [
    "GUARDRAILS",
    "evaluate_guardrails",
    "guardrail_error",
]
