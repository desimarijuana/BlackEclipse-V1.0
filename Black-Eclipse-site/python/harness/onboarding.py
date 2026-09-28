"""Cold-start onboarding (Phase 13).

A **static, read-only** first-run explanation of the memory/skills system plus a
list of optional starter skills already shipped in the bundled library. Nothing
here writes durable memory, enables a skill, or changes policy — it only
explains, so onboarding cannot pollute memory.

Starter content is the bundled skill library (visible provenance `bundled`); it
is removable/resettable through the normal skill lifecycle, and is clearly
distinguished from learned skills.
"""

from __future__ import annotations

from typing import Any, Optional

# The onboarding copy is static and versioned so the UI can show it once and
# detect changes without storing anything.
ONBOARDING_VERSION = 1

ONBOARDING_STEPS: tuple[dict[str, Any], ...] = (
    {
        "id": "facts",
        "title": "Facts (always-available memory)",
        "body": (
            "Small, durable, declarative facts recalled on relevant turns — "
            "preferences, standing conventions, environment facts. Nothing is "
            "stored unless you explicitly ask, or the system applies its "
            "selective learning rules. Automatic records are labeled and can be "
            "reviewed, confirmed, or archived."
        ),
    },
    {
        "id": "history",
        "title": "Session History (searchable, not always-on)",
        "body": (
            "Past conversations and run traces, redacted and searchable on "
            "demand. History is never injected into every prompt, and its "
            "retention is controlled separately from durable memory."
        ),
    },
    {
        "id": "skills",
        "title": "Skills (reusable procedures)",
        "body": (
            "Versioned procedures that load only when relevant. A skill must be "
            "evaluated and promoted by an operator before it runs. Bundled "
            "starter skills are visible with provenance 'bundled'; learned "
            "skills are separate and stay inert until approved."
        ),
    },
    {
        "id": "trust",
        "title": "Trust, privacy, and providers",
        "body": (
            "Project-carried skills stay inert until you explicitly trust the "
            "repo, and change detection quarantines a trusted skill if its "
            "content changes. Memory is local; external memory providers are "
            "opt-in, fenced, labeled unverified, and never promoted to native "
            "memory."
        ),
    },
    {
        "id": "retention",
        "title": "Retention",
        "body": (
            "Durable-memory retention and session-history retention are separate "
            "controls. Explicit facts are never silently expired. A retention "
            "sweep can be previewed before it runs, and never deletes records — "
            "it marks them inert and retained for audit."
        ),
    },
)


def onboarding_content(
    *, starter_skills: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    """Return the static onboarding content + available starter skills.

    `starter_skills` are the bundled library entries (provenance `bundled`),
    supplied by the caller from the live registry. This function reads nothing
    and writes nothing.
    """
    starters = []
    for skill in starter_skills or []:
        starters.append({
            "id": skill.get("id"),
            "name": skill.get("name"),
            "description": skill.get("description"),
            "category": skill.get("category"),
            "provenance": "bundled",
        })
    return {
        "version": ONBOARDING_VERSION,
        "steps": list(ONBOARDING_STEPS),
        "starterSkills": starters,
        "note": (
            "Read-only onboarding. It does not write memory, enable a skill, or "
            "change policy. Starter skills are bundled and removable/resettable "
            "through the normal skill lifecycle."
        ),
    }


__all__ = ["ONBOARDING_STEPS", "ONBOARDING_VERSION", "onboarding_content"]
