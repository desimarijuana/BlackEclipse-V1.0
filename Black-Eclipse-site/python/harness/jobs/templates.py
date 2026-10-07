"""The finance job library — TEMPLATES (data), never definitions.

Every template ships **disabled**: the operator picks one, answers "which
tickers?" / "which folder?", and their job is built. A template is DATA; it holds
no executable code and grants nothing. Instantiating one produces an ordinary
`JobDefinition` that then passes through the same save-time guardrails.

The seven templates mirror the phase file §6.9. Cadences are the documented
defaults; the operator may change them in the editor (in human language — the cron
string is data, never a field a non-expert authors).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..persistence import now_iso
from .model import JobDefinition, JobDelivery, JobKind, JobTarget
from .store import new_job_id


@dataclass(frozen=True)
class TemplateParameter:
    """One thing the user answers to parameterize a template."""

    key: str
    label: str
    required: bool = True
    example: str = ""


@dataclass(frozen=True)
class JobTemplate:
    """A one-click, parameterizable job. Always instantiated disabled."""

    id: str
    name: str
    description: str
    kind: JobKind
    target: dict[str, Any]
    cron: Optional[str] = None
    interval_seconds: Optional[int] = None
    on_missed: str = "skip"
    parameters: list[TemplateParameter] = field(default_factory=list)

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "kind": self.kind,
            "cron": self.cron,
            "intervalSeconds": self.interval_seconds,
            "onMissed": self.on_missed,
            "parameters": [
                {"key": p.key, "label": p.label, "required": p.required, "example": p.example}
                for p in self.parameters
            ],
        }


# The library. All user-facing copy is plain (no mechanism word from
# policy.PLAIN_LANGUAGE_DENYLIST).
JOB_TEMPLATES: tuple[JobTemplate, ...] = (
    JobTemplate(
        id="morning-portfolio-brief",
        name="Morning portfolio brief",
        description="A short read on your holdings each weekday morning: what moved, what's worth a look.",
        kind="cron",
        cron="30 7 * * 1-5",
        target={
            "kind": "skill",
            "skill_id": "research.planning",
            "objective": "Give me a short morning brief on my holdings: {tickers}. Cover what moved and what's worth a look today.",
        },
        parameters=[TemplateParameter("tickers", "Which holdings?", example="AAPL, MSFT, VOO")],
    ),
    JobTemplate(
        id="overnight-news-digest",
        name="Overnight news digest",
        description="A digest of overnight news about your holdings, ready before the market opens.",
        kind="cron",
        cron="0 7 * * 1-5",
        target={
            "kind": "objective",
            "objective": "Summarize overnight news about these holdings: {tickers}. Note anything that could move them today.",
        },
        parameters=[TemplateParameter("tickers", "Which holdings?", example="AAPL, MSFT, VOO")],
    ),
    JobTemplate(
        id="filing-watch",
        name="Filing watch",
        description="Watch for new regulatory filings for a list of companies and flag what changed.",
        kind="cron",
        cron="0 18 * * 1-5",
        target={
            "kind": "skill",
            "skill_id": "research.source-verification",
            "objective": "Check for new filings for {watchlist} and flag anything material that changed.",
        },
        parameters=[TemplateParameter("watchlist", "Which companies?", example="AAPL, MSFT, TSLA")],
    ),
    JobTemplate(
        id="earnings-look-ahead",
        name="Earnings look-ahead",
        description="Next week's earnings for your watchlist, with the date and what to expect.",
        kind="cron",
        cron="0 8 * * 1",
        target={
            "kind": "objective",
            "objective": "List earnings in the next 14 days for {watchlist}, with dates and a one-line preview each.",
        },
        parameters=[TemplateParameter("watchlist", "Which companies?", example="AAPL, MSFT, TSLA")],
    ),
    JobTemplate(
        id="data-freshness-watchdog",
        name="Data-freshness watchdog",
        description="Check every few hours that our data sources are healthy and tell you when one isn't.",
        kind="interval",
        interval_seconds=6 * 3600,
        target={
            "kind": "objective",
            "objective": "Check the health of our data sources and report any that are stale or unavailable.",
        },
    ),
    JobTemplate(
        id="fundamentals-refresh-check",
        name="Fundamentals refresh check",
        description="Check twice a day that fundamentals data is current and usable for your watchlist.",
        kind="interval",
        interval_seconds=12 * 3600,
        target={
            "kind": "skill",
            "skill_id": "quality.financial-data-quality",
            "objective": "Review whether fundamentals data for {watchlist} is current and usable.",
        },
        parameters=[TemplateParameter("watchlist", "Which companies?", example="AAPL, MSFT, TSLA")],
    ),
    JobTemplate(
        id="build-fix-finance-app",
        name="Build or fix a finance app",
        description="Have Eclipse build or repair a small finance tool in a folder you choose. You start it when you want.",
        kind="manual",
        target={
            "kind": "objective",
            "objective": "{task}",
            "autonomy": "edit_verify",
            # A template cannot know the operator's folder; the editor fills it.
            "workspace_root": "{folder}",
        },
        parameters=[
            TemplateParameter("task", "What should it build or fix?", example="a simple cash-flow dashboard"),
            TemplateParameter("folder", "Which folder?", example="C:\\work\\my-finance-tools"),
        ],
    ),
    JobTemplate(
        id="deploy-app-on-schedule",
        name="Deploy an app on a schedule",
        description=(
            "Ship the application in a folder you choose to a host you choose, on a "
            "cadence. Eclipse prepares, builds, deploys and checks it each time, and "
            "tells you if it didn't come up. You approve it once, when you set it up."
        ),
        kind="cron",
        cron="0 9 * * 1-5",
        target={
            "kind": "objective",
            "objective": (
                "Deploy the application at {folder} to {provider}. Prepare and build it "
                "first, deploy it, then check that it is healthy and report the result."
            ),
            # Deploying crosses the local boundary, so the job runs with the profile
            # that can perform an approved external action. The run is STILL subject
            # to the same per-action authorization as a manual deploy.
            "autonomy": "approve_external",
            "workspace_root": "{folder}",
        },
        parameters=[
            TemplateParameter("folder", "Which application folder?", example="C:\\work\\my-api"),
            TemplateParameter("provider", "Where should it go?", example="vercel"),
        ],
    ),
    JobTemplate(
        id="deploy-app-on-webhook",
        name="Deploy an app when a webhook fires",
        description=(
            "Ship the application in a folder you choose whenever a deploy hook is "
            "called — a good fit for a CI job or a manual button. Eclipse prepares, "
            "builds, deploys and checks it, and reports what happened."
        ),
        kind="webhook",
        target={
            "kind": "objective",
            "objective": (
                "Deploy the application at {folder} to {provider}. Prepare and build it "
                "first, deploy it, then check that it is healthy and report the result."
            ),
            "autonomy": "approve_external",
            "workspace_root": "{folder}",
        },
        parameters=[
            TemplateParameter("folder", "Which application folder?", example="C:\\work\\my-api"),
            TemplateParameter("provider", "Where should it go?", example="vercel"),
        ],
    ),
)


def list_templates() -> list[dict[str, Any]]:
    return [t.public() for t in JOB_TEMPLATES]


def get_template(template_id: str) -> Optional[JobTemplate]:
    return next((t for t in JOB_TEMPLATES if t.id == template_id), None)


def _substitute(text: Optional[str], params: dict[str, Any]) -> Optional[str]:
    if text is None:
        return None
    out = text
    for key, value in (params or {}).items():
        out = out.replace("{" + key + "}", str(value))
    return out


def instantiate(
    template_id: str, params: Optional[dict[str, Any]] = None, *, name: Optional[str] = None,
) -> JobDefinition:
    """Build a DISABLED `JobDefinition` from a template + the user's answers.

    Substitution happens here, so a template is pure data. The result is NOT yet
    persisted — the caller passes it through `guardrails.validate_job` first.
    """
    template = get_template(template_id)
    if template is None:
        raise ValueError(f"unknown job template {template_id!r}")
    params = params or {}
    target_raw = dict(template.target)
    for key in ("objective", "workspace_root"):
        if key in target_raw:
            target_raw[key] = _substitute(target_raw.get(key), params)
    now = now_iso()
    return JobDefinition(
        id=new_job_id(),
        name=(name or template.name)[:120],
        kind=template.kind,
        cron=template.cron,
        interval_seconds=template.interval_seconds,
        on_missed=template.on_missed,  # type: ignore[arg-type]
        target=JobTarget(**target_raw),
        delivery=JobDelivery(),
        enabled=False,  # discovery is not activation
        created_at=now,
        updated_at=now,
    )


__all__ = [
    "JOB_TEMPLATES",
    "JobTemplate",
    "TemplateParameter",
    "get_template",
    "instantiate",
    "list_templates",
]
