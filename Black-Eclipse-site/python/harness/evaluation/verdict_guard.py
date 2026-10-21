"""Verdict-leak tripwire for evidence served to models or stored as lessons.

The proposer is deliberately starved of ground truth. A tree that contains the
grader's own output can never afterwards be served as evidence, so the tripwire
fires on the read boundary and the rule is to find the leaking read path, not to
widen the marker list.

Use this on any evidence bundle, candidate text or lesson that is about to
(a) be served to a proposal/learning model or (b) be persisted as a reusable
lesson. It keeps evaluation outcomes and expected answers out of the
self-improvement loop, so a lesson can never be a transcription of the answer
key.
"""

from __future__ import annotations

from pathlib import Path

VERDICT_MARKERS: tuple[str, ...] = (
    "pass_rate",
    "passRate",
    "weighted_composite",
    "weightedComposite",
    "critical_dimensions",
    "criticalDimensions",
    "expected_output",
    "expectedOutput",
    "expected_state",
    "expectedState",
    "EvaluationScore",
    "hallucination_rate",
    "safety_score",
)

_CONTENT_SUFFIXES = frozenset(
    {
        ".md",
        ".txt",
        ".json",
        ".jsonl",
        ".csv",
        ".tsv",
        ".yaml",
        ".yml",
        ".html",
        ".htm",
        ".log",
        ".py",
        ".js",
        ".ts",
        ".sh",
        ".xml",
        ".ini",
        ".toml",
        ".patch",
        ".diff",
        "",
    }
)


class VerdictLeakError(ValueError):
    """Raised when evaluation verdicts would enter model context or a lesson."""


def find_marker_in_text(text: str, *, markers: tuple[str, ...] = VERDICT_MARKERS) -> str | None:
    """The first verdict marker present in ``text``, or None."""
    for marker in markers:
        if marker in text:
            return marker
    return None


def find_verdict_leaks(root: Path | str, *, markers: tuple[str, ...] = VERDICT_MARKERS) -> list[str]:
    """Every (relative path, marker) hit under ``root``; empty when clean."""
    root = Path(root)
    hits: list[str] = []
    if not root.is_dir():
        return hits
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        for marker in markers:
            if marker in rel:
                hits.append(f"{rel}: marker {marker!r} in its name")
        if path.suffix.lower() not in _CONTENT_SUFFIXES:
            continue
        try:
            body = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        marker = find_marker_in_text(body, markers=markers)
        if marker is not None:
            offset = body.index(marker)
            hits.append(
                f"{rel}: marker {marker!r} at offset {offset} "
                f"({body[max(0, offset - 40) : offset + 80]!r})"
            )
    return hits


def assert_no_verdict_leaks(root: Path | str, *, markers: tuple[str, ...] = VERDICT_MARKERS) -> None:
    """Refuse a directory containing evaluation verdicts, by file name and content."""
    hits = find_verdict_leaks(root, markers=markers)
    if hits:
        raise VerdictLeakError(
            "evaluation verdict would enter model context or a lesson: "
            + "; ".join(hits[:6])
            + ". This is a leak, not a false positive to widen around -- find the "
            "read path that produced it."
        )


def assert_text_has_no_verdict_leaks(
    text: str, *, label: str = "text", markers: tuple[str, ...] = VERDICT_MARKERS
) -> None:
    """The same tripwire for a single string (a lesson body, a candidate note)."""
    marker = find_marker_in_text(text, markers=markers)
    if marker is not None:
        raise VerdictLeakError(
            f"evaluation verdict would enter model context or a lesson: {label} "
            f"contains marker {marker!r}. This is a leak, not a false positive to "
            f"widen around -- find the read path that produced it."
        )


__all__ = [
    "VERDICT_MARKERS",
    "VerdictLeakError",
    "assert_no_verdict_leaks",
    "assert_text_has_no_verdict_leaks",
    "find_marker_in_text",
    "find_verdict_leaks",
]
