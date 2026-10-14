"""The scheduling catalogue — the fixed job shapes the agent may create.

Phase 17 (repo-mapped): the agent may put its own recurring work on a schedule,
but only from a CLOSED catalogue of finance job shapes and only when the
operator's master switch (`agent_scheduling_enabled`) is on. A shape references
an EXISTING template from `jobs.templates` — there is no free-form job authoring
and no code/deploy shape, because the agent never schedules code changes on its
own initiative.

The catalogue is DATA: one row per shape. `catalogue_issues()` fails when a row
does not name a real template, requires a parameter the template does not have,
or declares a hard frequency ceiling below the template's own cadence. Nothing
here can enable a job: a created job is ALWAYS saved switched off, and only the
operator turns it on.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from ..jobs.templates import get_template
from .model import DELIVERY_ADAPTERS


@dataclass(frozen=True)
class SchedulableJobShape:
    """One row: a job shape the agent may instantiate, always switched off."""

    id: str                          # stable id the agent asks for
    template_id: str                 # the EXISTING template this instantiates
    label: str                       # plain words (a refusal/reply may name it)
    required_params: tuple[str, ...]  # parameter keys the user's answer must fill
    optional_params: tuple[str, ...]
    max_frequency_per_day: int       # hard ceiling: no shape may run every minute
    delivery: str = "in_app"         # an existing delivery adapter name


# The library. Research/analysis shapes only: the catalogue deliberately has no
# `build-fix-finance-app`, `deploy-app-on-schedule` or `deploy-app-on-webhook`
# row — code and deploy work is never put on a cadence by the agent itself.
SHAPES: dict[str, SchedulableJobShape] = {
    "morning_brief": SchedulableJobShape(
        id="morning_brief", template_id="morning-portfolio-brief",
        label="Morning portfolio brief",
        required_params=("tickers",), optional_params=(),
        max_frequency_per_day=1,
    ),
    "news_digest": SchedulableJobShape(
        id="news_digest", template_id="overnight-news-digest",
        label="Overnight news digest",
        required_params=("tickers",), optional_params=(),
        max_frequency_per_day=1,
    ),
    "filing_watch": SchedulableJobShape(
        id="filing_watch", template_id="filing-watch",
        label="Filing watch",
        required_params=("watchlist",), optional_params=(),
        max_frequency_per_day=1,
    ),
    "earnings_lookahead": SchedulableJobShape(
        id="earnings_lookahead", template_id="earnings-look-ahead",
        label="Earnings look-ahead",
        required_params=("watchlist",), optional_params=(),
        max_frequency_per_day=1,
    ),
    "data_freshness": SchedulableJobShape(
        id="data_freshness", template_id="data-freshness-watchdog",
        label="Data-freshness watchdog",
        required_params=(), optional_params=(),
        max_frequency_per_day=4,
    ),
    "fundamentals_check": SchedulableJobShape(
        id="fundamentals_check", template_id="fundamentals-refresh-check",
        label="Fundamentals refresh check",
        required_params=("watchlist",), optional_params=(),
        max_frequency_per_day=2,
    ),
    "deep_research": SchedulableJobShape(
        id="deep_research", template_id="deep-research-brief",
        label="Deep research brief",
        required_params=("topic",), optional_params=(),
        max_frequency_per_day=1,
    ),
    "competitor_watch": SchedulableJobShape(
        id="competitor_watch", template_id="competitor-watch",
        label="Competitor watch",
        required_params=("company",), optional_params=(),
        max_frequency_per_day=1,
    ),
    "topic_digest": SchedulableJobShape(
        id="topic_digest", template_id="research-topic-digest",
        label="Research topic digest",
        required_params=("topic",), optional_params=(),
        max_frequency_per_day=1,
    ),
}


def get_shape(shape_id: str) -> Optional[SchedulableJobShape]:
    return SHAPES.get(str(shape_id or "").strip())


def list_shapes() -> list[dict[str, Any]]:
    return [shape_public(shape) for shape in SHAPES.values()]


def shape_public(shape: SchedulableJobShape) -> dict[str, Any]:
    template = get_template(shape.template_id)
    return {
        "id": shape.id,
        "label": shape.label,
        "templateId": shape.template_id,
        "description": template.description if template is not None else "",
        "requiredParams": list(shape.required_params),
        "optionalParams": list(shape.optional_params),
        "maxFrequencyPerDay": shape.max_frequency_per_day,
        "delivery": shape.delivery,
        "exampleParams": {
            p.key: p.example for p in (template.parameters if template is not None else [])
        },
    }


def _times_per_day(hour_field: str) -> int:
    """A conservative estimate of a cron hour field's daily firings.

    Used only to CHECK a shape's declared ceiling; an unknown shape counts as a
    full day so a mistake can never widen the ceiling.
    """
    field = (hour_field or "").strip()
    if not field:
        return 24
    if field in ("*", "*/1"):
        return 24
    if "," in field:
        return len([part for part in field.split(",") if part.strip()]) or 24
    if "-" in field:
        bounds = field.split("-", 1)
        try:
            return max(1, int(bounds[1]) - int(bounds[0]) + 1)
        except ValueError:
            return 24
    if "/" in field:
        return 24
    return 1


def shape_frequency_per_day(shape: SchedulableJobShape) -> float:
    """The template's own maximum firings per calendar day."""
    template = get_template(shape.template_id)
    if template is None:
        return 0.0
    if template.kind == "interval" and template.interval_seconds:
        return 86400.0 / max(1, int(template.interval_seconds))
    if template.kind == "cron" and template.cron:
        fields = template.cron.split()
        if len(fields) == 5:
            return float(max(1, _times_per_day(fields[1])))
    return 1.0


def catalogue_issues() -> list[str]:
    """Consistency problems, empty when the catalogue is sound."""
    issues: list[str] = []
    for shape in SHAPES.values():
        template = get_template(shape.template_id)
        if template is None:
            issues.append(f"{shape.id}: unknown template {shape.template_id!r}")
            continue
        param_keys = {p.key for p in template.parameters}
        for key in (*shape.required_params, *shape.optional_params):
            if key not in param_keys:
                issues.append(
                    f"{shape.id}: template {shape.template_id!r} has no parameter {key!r}"
                )
        for param in template.parameters:
            if param.required and param.key not in shape.required_params:
                issues.append(
                    f"{shape.id}: template requires {param.key!r} but the shape does not"
                )
        frequency = shape_frequency_per_day(shape)
        if frequency > float(shape.max_frequency_per_day):
            issues.append(
                f"{shape.id}: template runs {frequency:g}/day above the declared "
                f"ceiling {shape.max_frequency_per_day}"
            )
        if shape.delivery not in DELIVERY_ADAPTERS:
            issues.append(f"{shape.id}: unknown delivery adapter {shape.delivery!r}")
    return issues


__all__ = [
    "SHAPES",
    "SchedulableJobShape",
    "catalogue_issues",
    "get_shape",
    "list_shapes",
    "shape_frequency_per_day",
    "shape_public",
]
