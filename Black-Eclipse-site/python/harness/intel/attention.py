"""Public-attention velocity from English Wikipedia daily pageviews.

A free, keyless, bot-filtered attention series. The measurement is deliberately
dull: how far the last week's mean sits from the article's own trailing
median, in robust standard deviations. No model, no seasonality model, no
"sentiment score".

Why pageviews: they are published by the Wikimedia Foundation, stable, daily,
and cover nearly every listed company. Why *robust* statistics: article traffic
is spiky and has legitimate event days, so a mean/std z-score is hostage to a
single outlier. Median/MAD answers "is this unusual for this page?".

Honest limits, repeated in the signal spec: curiosity is not buying, page moves
and news spikes pollute the series, and a z-score carries no direction. It is a
prompt to look, never a conclusion.
"""

from __future__ import annotations

import json
import re
import statistics
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional
from urllib.error import HTTPError
from urllib.parse import quote

Fetch = Callable[[str], str]

PAGEVIEW_URL = (
    "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
    "{project}/{access}/{agent}/{article}/daily/{start}/{end}"
)
#: Used only to follow redirects: EDGAR says "Nvidia Corp", the living article
#: is "Nvidia". The pageviews API reports the redirect target's traffic only when
#: asked for the target, so resolution has to happen first.
MEDIAWIKI_API = (
    "https://en.wikipedia.org/w/api.php?action=query&format=json&redirects=1"
    "&titles={titles}"
)
PROJECT = "en.wikipedia"
ACCESS = "all-access"
AGENT = "user"  # excludes the "spider" agent class where the API splits it

#: Corporate suffixes stripped when guessing an article title. Order matters:
#: the longest first so "Inc." does not leave a dangling "Inc".
_SUFFIX_RE = re.compile(
    r"[,.]?\s+(inc|incorporated|corp|corporation|company|co|ltd|limited|plc|llc|lp|"
    r"holdings?|group|technologies|technology|systems|international|industries|"
    r"enterprises|sa|ag|nv|bv|se|spa)\.?$",
    re.IGNORECASE,
)


def pageviews_url(article: str, start: str, end: str, *, project: str = PROJECT) -> str:
    return PAGEVIEW_URL.format(
        project=project,
        access=ACCESS,
        agent=AGENT,
        article=quote(article.replace(" ", "_"), safe=""),
        start=start.replace("-", ""),
        end=end.replace("-", ""),
    )


def article_candidates(company_name: str) -> list[str]:
    """Likely Wikipedia titles for an issuer name, most specific first.

    EDGAR names are often ALL CAPS ("NVIDIA CORP"); the Wikipedia article is
    "Nvidia". We try the exact name, then a title-cased form, then the name with
    a corporate suffix removed, then that form title-cased.
    """
    raw = " ".join(str(company_name or "").split())
    if not raw:
        return []
    out: list[str] = []

    def add(value: str) -> None:
        value = value.strip(" ,.")
        if value and value not in out:
            out.append(value)

    add(raw)
    title = raw.title() if raw.isupper() else raw
    add(title)
    stripped = _SUFFIX_RE.sub("", raw)
    if stripped != raw:
        add(stripped)
        add(stripped.title() if stripped.isupper() else stripped)
    return out


def parse_pageviews(payload: Any) -> list[tuple[str, int]]:
    """`[(YYYY-MM-DD, views)]`, oldest first, from the REST payload."""
    items = (payload or {}).get("items") if isinstance(payload, dict) else None
    out: list[tuple[str, int]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        stamp = str(item.get("timestamp") or "")
        views = item.get("views")
        if len(stamp) < 8 or not isinstance(views, (int, float)):
            continue
        day = f"{stamp[0:4]}-{stamp[4:6]}-{stamp[6:8]}"
        out.append((day, int(views)))
    out.sort(key=lambda row: row[0])
    return out


@dataclass
class AttentionReading:
    article: str
    zscore: float
    ratio: float
    short_mean: float
    baseline_median: float
    baseline_mad: float
    sample_days: int
    short_days: int
    as_of: str
    method: str
    provenance: dict[str, Any]

    @property
    def confidence(self) -> float:
        """Evidence quality: sample size and whether the short window is full."""
        coverage = min(1.0, self.sample_days / 90.0)
        completeness = min(1.0, self.short_days / 7.0)
        return round(0.35 + 0.45 * coverage + 0.2 * completeness, 3)

    def to_dict(self) -> dict[str, Any]:
        return {
            "article": self.article,
            "zscore": round(self.zscore, 3),
            "ratio": round(self.ratio, 3),
            "shortMean": round(self.short_mean, 1),
            "baselineMedian": round(self.baseline_median, 1),
            "baselineMad": round(self.baseline_mad, 1),
            "sampleDays": self.sample_days,
            "shortDays": self.short_days,
            "asOf": self.as_of,
            "method": self.method,
            "provenance": self.provenance,
            "confidence": self.confidence,
        }


def _parse_day(value: str) -> Optional[date]:
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def robust_velocity(
    series: list[tuple[str, int]],
    *,
    as_of: str,
    short_days: int = 7,
    baseline_days: int = 90,
    min_days: int = 30,
) -> Optional[AttentionReading]:
    """Robust z-score of the trailing week against the page's own baseline.

    `series` must be daily (date, views), oldest first. Days the API omits are
    treated as missing, not zero — a zero would deflate the baseline.

    Returns None when there is not enough history: an honest "cannot say",
    which the caller turns into UNAVAILABLE rather than a fabricated number.
    """
    if not series:
        return None
    end = _parse_day(as_of)
    if end is None:
        return None
    short_start = end - timedelta(days=short_days - 1)
    base_start = short_start - timedelta(days=baseline_days)

    short: list[int] = []
    base: list[int] = []
    for day_text, views in series:
        day = _parse_day(day_text)
        if day is None:
            continue
        if short_start <= day <= end:
            short.append(int(views))
        elif base_start <= day < short_start:
            base.append(int(views))

    if len(short) < max(3, short_days - 3) or len(base) < min_days:
        return None

    short_mean = float(statistics.fmean(short))
    median = float(statistics.median(base))
    # A page whose baseline median is zero is a stub/redirect shell, not a
    # readership. Measuring it would produce a real-looking z about nothing.
    if median <= 0 or short_mean <= 0:
        return None
    mad = float(statistics.median([abs(v - median) for v in base])) if base else 0.0
    scale = 1.4826 * mad
    if scale < 1e-9:
        # A flat page (or too few distinct values). Std is also 0 for a constant
        # series, so fall back to a small relative guard: a tripling of a page
        # whose baseline never moves must still register as unusual, not as 0.
        scale = float(statistics.pstdev(base)) if len({*base}) > 1 else 0.0
        if scale < 1e-9:
            scale = max(1.0, 0.05 * median)
    z = 0.0 if scale < 1e-9 else (short_mean - median) / scale
    ratio = (short_mean / median) if median > 0 else 0.0

    return AttentionReading(
        article="",
        zscore=z,
        ratio=ratio,
        short_mean=short_mean,
        baseline_median=median,
        baseline_mad=mad,
        sample_days=len(base) + len(short),
        short_days=len(short),
        as_of=end.isoformat(),
        method=(
            f"mean({short_days}d) vs median({baseline_days}d) / (1.4826*MAD), "
            "Wikipedia daily pageviews"
        ),
        provenance={
            "shortDays": short_days,
            "baselineDays": baseline_days,
            "baselinePoints": len(base),
            "shortPoints": len(short),
        },
    )


def resolve_titles(fetch: Fetch, candidates: list[str]) -> list[str]:
    """Follow Wikipedia redirects/normalisation, preserving candidate order.

    `Apple Inc.` normalises to `Apple Inc`; `Nvidia Corp` redirects to `Nvidia`.
    Both matter, because the pageviews endpoint answers for the title you name —
    a redirect shell reports almost no traffic and would read as "attention
    collapsed". Best-effort: any failure returns [] and the caller falls back to
    the raw candidates.
    """
    if not candidates:
        return []
    titles = "|".join(candidate.replace(" ", "_") for candidate in candidates[:5])
    url = MEDIAWIKI_API.format(titles=quote(titles, safe="|_,."))
    try:
        payload = json.loads(fetch(url))
    except Exception:  # noqa: BLE001 - resolution is an optimisation, never a gate
        return []
    query = (payload or {}).get("query") or {}
    mapping: dict[str, str] = {}
    for row in query.get("normalized") or []:
        if isinstance(row, dict) and row.get("from") and row.get("to"):
            mapping[str(row["from"])] = str(row["to"])
    for row in query.get("redirects") or []:
        if isinstance(row, dict) and row.get("from") and row.get("to"):
            mapping[str(row["from"])] = str(row["to"])
    pages = query.get("pages") or {}
    missing = {
        str(page.get("title")) for page in pages.values()
        if isinstance(page, dict) and "missing" in page
    } if isinstance(pages, dict) else set()

    out: list[str] = []
    for candidate in candidates:
        current = candidate
        for _ in range(4):  # bounded redirect chase; no cycles possible beyond this
            mapped = mapping.get(current.replace("_", " "))
            if not mapped or mapped == current:
                break
            current = mapped
        if current in missing:
            continue
        if current and current not in out:
            out.append(current)
    return out


def fetch_reading(
    fetch: Fetch,
    *,
    company_name: str,
    as_of: str,
    article: Optional[str] = None,
    short_days: int = 7,
    baseline_days: int = 90,
) -> Optional[AttentionReading]:
    """Resolve an article and read its velocity. `None` when nothing is usable.

    Resolution is a bounded, deterministic probe: normalise/redirect the
    candidate titles, then take the FIRST one that yields a usable series with
    real readership. The chosen title is recorded in provenance so a reader can
    audit it.
    """
    end = _parse_day(as_of) or date.today()
    start = end - timedelta(days=short_days + baseline_days + 5)
    candidates = [article] if article else article_candidates(company_name)
    resolved = resolve_titles(fetch, [c for c in candidates if c])
    ordered: list[str] = []
    for title in [*resolved, *candidates]:
        if title and title not in ordered:
            ordered.append(title)

    transport_errors: list[Exception] = []
    for candidate in ordered:
        url = pageviews_url(candidate, start.isoformat(), end.isoformat())
        try:
            payload = fetch(url)
        except HTTPError:
            # A 404 is a probe miss (no such article / no data), not an outage.
            continue
        except Exception as exc:  # noqa: BLE001 - remember, then try the next
            transport_errors.append(exc)
            continue
        try:
            series = parse_pageviews(json.loads(payload))
        except (TypeError, ValueError):
            continue
        reading = robust_velocity(
            series, as_of=end.isoformat(), short_days=short_days,
            baseline_days=baseline_days,
        )
        if reading is None:
            continue
        reading.article = candidate
        reading.provenance["url"] = url
        reading.provenance["article"] = candidate
        return reading
    # Every candidate failed at the transport level: that is an outage, and the
    # caller must be able to say so instead of claiming "no article exists".
    if transport_errors and len(transport_errors) >= len(ordered):
        raise transport_errors[-1]
    return None


__all__ = [
    "AttentionReading", "MEDIAWIKI_API", "PAGEVIEW_URL", "article_candidates",
    "fetch_reading", "pageviews_url", "parse_pageviews", "resolve_titles",
    "robust_velocity",
]
