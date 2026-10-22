"""Strategy venues — one seam for every DSL Eclipse can run.

A *venue* is a place a strategy can be written in: Pine Script, NinjaScript,
PowerLanguage, EasyLanguage. Each venue has an ENGINE - something that can
actually execute that language. A venue without an engine is not a broken
feature; it is a **named capability gap**, and this module makes that explicit
rather than leaving it to be discovered.

The seam exists so that adding a venue is a registration, not a refactor: a
venue declares whether it can run, what it needs installed, and how to reach
its engine. The Pine venue is the one with an engine today (the isolated
`pine-engine/` program); the other three report exactly why they cannot run.

The honesty rule: a venue never claims to work. `available` is False, and
`reason` says what is missing, until its engine is actually installed and
probed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

#: The venues Eclipse knows about. Adding one is a line here plus its engine.
VENUE_IDS: tuple[str, ...] = ("pine", "ninjascript", "powerlanguage", "easylanguage")


@dataclass
class Venue:
    """One strategy language and whether Eclipse can run it."""

    id: str
    name: str
    language: str
    engine: Optional[str] = None
    #: Why the venue cannot run, when it cannot. None means it can.
    unavailable_reason: Optional[str] = None
    #: How to reach the engine, when there is one.
    runner: Optional[Callable[..., Any]] = None
    #: The file extension of a script in this language.
    extension: str = ""
    notes: str = ""

    @property
    def available(self) -> bool:
        return self.runner is not None and self.unavailable_reason is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "language": self.language,
            "engine": self.engine,
            "available": self.available,
            "reason": self.unavailable_reason,
            "extension": self.extension,
            "notes": self.notes,
        }


def _pine_venue() -> Venue:
    """The Pine venue: an isolated engine, probed rather than assumed."""
    from ..market.series_store import get_series_store  # noqa: F401 - import check
    from .pine import PineRunner

    runner = PineRunner()
    reason = runner.unavailable_reason()
    return Venue(
        id="pine",
        name="Pine Script",
        language="Pine Script (v5/v6)",
        engine="pine-engine (pinets)",
        unavailable_reason=reason,
        runner=runner.run if reason is None else None,
        extension=".pine",
        notes=("Runs in a separate program so the AGPL engine never links into "
                "the app. The bars come from Eclipse, so the script is evaluated "
                "on the data the caller already holds."),
    )


def _unavailable_venue(venue_id: str, name: str, language: str, extension: str,
                        reason: str, notes: str) -> Venue:
    return Venue(id=venue_id, name=name, language=language, engine=None,
                 unavailable_reason=reason, extension=extension, notes=notes)


def build_venues() -> dict[str, Venue]:
    """Every venue, with its real availability."""
    return {
        "pine": _pine_venue(),
        "ninjascript": _unavailable_venue(
            "ninjascript", "NinjaScript", "C# (NinjaTrader)", ".cs",
            "no NinjaScript engine is installed; the venue needs a C# runtime "
            "that can execute a compiled strategy",
            "The same seam would take one: a venue declares its engine and a "
            "runner, and everything above it is unchanged."),
        "powerlanguage": _unavailable_venue(
            "powerlanguage", "PowerLanguage", "PowerLanguage (TradeStation)",
            ".pl",
            "no PowerLanguage engine is installed; the venue needs a runtime "
            "that can execute a TradeStation strategy",
            "Same seam: a venue declares its engine and a runner."),
        "easylanguage": _unavailable_venue(
            "easylanguage", "EasyLanguage", "EasyLanguage (TS2000)",
            ".ts",
            "no EasyLanguage engine is installed; the venue needs a runtime that "
            "can execute a TS2000 strategy",
            "Same seam: a venue declares its engine and a runner."),
    }


def list_venues() -> list[dict[str, Any]]:
    """Every venue and whether it can run right now."""
    return [venue.to_dict() for venue in build_venues().values()]


def get_venue(venue_id: str) -> Venue:
    """One venue, or a named refusal."""
    venues = build_venues()
    venue = venues.get(str(venue_id or "").strip().lower())
    if venue is None:
        raise KeyError(
            f"unknown venue {venue_id!r}; Eclipse knows "
            f"{', '.join(sorted(venues))}")
    return venue


__all__ = ["VENUE_IDS", "Venue", "build_venues", "get_venue", "list_venues"]
