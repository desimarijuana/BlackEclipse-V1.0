"""Source model: classification, entity resolution, ranking, news dedup.

Deterministic, explainable, no model. These functions turn a URL/domain into a
`SourceType`, resolve a company alias into one canonical entity, score a source
for a research type, and detect syndicated news so ten copies of one Reuters
story are not counted as ten independent sources.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional
from urllib.parse import urlparse

from .web_contracts import (
    Authority,
    PRIMARY_SOURCE_TYPES,
    Source,
    SourceType,
    authority_for,
    content_hash,
    source_id,
)

# ── Domain → source type ────────────────────────────────────────────────────────

_GOV_SUFFIXES = (".gov", ".gov.uk", ".gc.ca", ".gov.au", ".mil")
_REGULATOR_HINTS = (
    "sec.gov", "esma.europa.eu", "fca.org.uk", "ftc.gov", "europa.eu", "fdic.gov",
    "cfpb.gov", "finra.org", "occ.gov", "federalreserve.gov", "treasury.gov",
)
_FILING_HOSTS = (
    "sec.gov", "data.sec.gov", "companieshouse.gov.uk", "sedar.com", "mops.twse.com.tw",
    "dart.fss.or.kr", "tdnet.info", "asx.com.au",
)
_IR_HINTS = ("investor", "ir.", "investors.", "ir-", "shareholder", "annualreport")
_ACADEMIC_HINTS = (
    "arxiv.org", "doi.org", "ncbi.nlm.nih.gov", "pubmed", "springer.com", "sciencedirect.com",
    "nature.com", "science.org", "jstor.org", "ssrn.com", "semanticscholar.org", "openalex.org",
    "crossref.org", ".edu",
)
_FINANCIAL_DATA_HINTS = ("bloomberg.com", "reuters.com/markets", "wsj.com", "ft.com", "fool.com", "morningstar.com", "stockanalysis.com", "finance.yahoo.com", "marketwatch.com")
_NEWS_HINTS = ("reuters.com", "apnews.com", "bbc.", "nytimes.com", "cnbc.com", "bloomberg.com", "wsj.com", "ft.com", "theguardian.com", "aljazeera.com", "forbes.com", "businessinsider.com", "techcrunch.com")
_ANALYST_HINTS = ("morganstanley.com", "goldmansachs.com", "jpmorgan.com", "seekingalpha.com", "barrons.com", "zacks.com")
_INDUSTRY_HINTS = ("gartner.com", "mckinsey.com", "idc.com", "cbinsights.com", "statista.com", "deloitte.com", "pwc.com")
_WIKI_HINTS = ("wikipedia.org", "wikiwand.com", "fandom.com", "britannica.com")
# Learning-resource hints. These are checked BEFORE the social/forum/academic
# families so `youtube.com` is a VIDEO and `github.com` a REPOSITORY, not
# "social" — a learning objective ranks them by source-specific criteria.
_VIDEO_HINTS = (
    "youtube.com", "youtu.be", "youtube-nocookie.com", "vimeo.com",
    "ted.com", "bilibili.com",
)
_COURSE_HINTS = (
    "coursera.org", "edx.org", "udacity.com", "khanacademy.org", "ocw.mit.edu",
    "class-central.com", "futurelearn.com", "pluralsight.com", "datacamp.com",
    "brilliant.org", "codecademy.com", "freecodecamp.org", "openstax.org",
    "nptel.ac.in", "swayam.gov.in", "alison.com", "skillshare.com",
)
_REPO_HINTS = (
    "github.com", "gitlab.com", "bitbucket.org", "sourceforge.net", "codeberg.org",
    "huggingface.co", "kaggle.com", "colab.research.google.com",
)
_DOCS_HINTS = (
    "docs.", "/docs", "readthedocs.io", "developer.mozilla.org", "devdocs.io",
    "man7.org", "tutorialspoint.com", "geeksforgeeks.org", "w3schools.com",
    "learn.microsoft.com", "cloud.google.com", "developer.apple.com",
)
_DATASET_HINTS = ("dataset", "data.gov", "ourworldindata.org", "worldbank.org", "imf.org", "eurostat", "datahub.io")
_PODCAST_HINTS = ("podcast", "spotify.com/episode", "anchor.fm", "buzzsprout.com", "libsyn.com")
_SOCIAL_HINTS = ("twitter.com", "x.com", "facebook.com", "linkedin.com", "instagram.com", "tiktok.com", "reddit.com", "threads.net", "mastodon")
_FORUM_HINTS = ("stackexchange.com", "quora.com", "news.ycombinator.com", "discourse", "forum")
_BLOG_HINTS = ("medium.com", "substack.com", "blogspot", "wordpress.com", "dev.to")


def _host(url_or_domain: str) -> str:
    value = (url_or_domain or "").strip().lower()
    if "://" in value:
        try:
            return urlparse(value).netloc.lower().replace("www.", "")
        except Exception:  # noqa: BLE001
            return ""
    return value.replace("www.", "")


def classify_source_type(domain_or_url: str, url: str = "") -> SourceType:
    """Deterministically classify a source. Unknown when nothing matches."""
    host = _host(domain_or_url) or _host(url)
    full = (url or domain_or_url or "").lower()
    if not host:
        return SourceType.UNKNOWN

    if host in _FILING_HOSTS or any(host.endswith(s) for s in _GOV_SUFFIXES):
        # A government domain is GOVERNMENT unless it is a known regulator.
        if any(r in host for r in _REGULATOR_HINTS):
            return SourceType.REGULATOR
        return SourceType.GOVERNMENT
    if any(r in host for r in _REGULATOR_HINTS):
        return SourceType.REGULATOR
    if any(h in full for h in _IR_HINTS):
        return SourceType.INVESTOR_RELATIONS
    if any(w in host for w in _WIKI_HINTS):
        return SourceType.WIKI
    # Learning-resource families come before social/forum/academic so a video,
    # course, repository, doc page or dataset is typed for its own ranking table.
    if any(h in host for h in _VIDEO_HINTS):
        return SourceType.VIDEO
    if any(h in host for h in _COURSE_HINTS):
        return SourceType.COURSE
    if any(h in host for h in _REPO_HINTS):
        return SourceType.REPOSITORY
    if any(h in full for h in _DOCS_HINTS):
        return SourceType.DOCUMENTATION
    if any(h in full for h in _PODCAST_HINTS):
        return SourceType.PODCAST
    if any(h in host for h in _DATASET_HINTS):
        return SourceType.DATASET
    if any(h in host for h in _SOCIAL_HINTS):
        return SourceType.SOCIAL
    if any(h in host for h in _FORUM_HINTS):
        return SourceType.FORUM
    if any(h in host for h in _ACADEMIC_HINTS) or host.endswith(".edu"):
        return SourceType.ACADEMIC
    if any(h in host for h in _ANALYST_HINTS):
        return SourceType.ANALYST
    if any(h in host for h in _INDUSTRY_HINTS):
        return SourceType.INDUSTRY
    if any(h in host for h in _FINANCIAL_DATA_HINTS):
        return SourceType.FINANCIAL_DATA
    if any(h in host for h in _NEWS_HINTS):
        return SourceType.NEWS
    if any(h in host for h in _BLOG_HINTS):
        return SourceType.BLOG
    return SourceType.UNKNOWN


def publisher_for(domain: str) -> str:
    """A human-readable publisher name from a domain (best effort, never invented)."""
    host = _host(domain)
    if not host:
        return ""
    parts = host.split(".")
    core = parts[-2] if len(parts) >= 2 else host
    return core.replace("-", " ").title()


def make_source(
    url: str,
    *,
    title: Optional[str] = None,
    published_at: Optional[str] = None,
    content_hash_value: Optional[str] = None,
    source_family: Optional[str] = None,
) -> Source:
    host = _host(url)
    stype = classify_source_type(host, url)
    from .web_contracts import _now

    return Source(
        sourceId=source_id(url),
        canonicalUrl=url,
        domain=host,
        publisher=publisher_for(host),
        sourceType=stype,
        authority=authority_for(stype, is_primary_filing=stype in (SourceType.OFFICIAL_FILING, SourceType.REGULATOR)),
        retrievedAt=_now(),
        publishedAt=published_at,
        sourceFamily=source_family,
        contentHash=content_hash_value,
        title=title,
    )


# ── Entity resolution ───────────────────────────────────────────────────────────


@dataclass
class Entity:
    entityId: str
    name: str
    ticker: Optional[str] = None
    exchange: Optional[str] = None
    aliases: list[str] | None = None
    officialDomain: Optional[str] = None
    irDomain: Optional[str] = None


# A tiny seed aliasing table so common cases resolve to ONE canonical entity.
# Extending this is data, not code. Canonical identity is deterministic.
_SEED_ENTITIES: list[Entity] = [
    Entity(entityId="e_nvidia", name="NVIDIA Corporation", ticker="NVDA", exchange="NASDAQ",
           aliases=["nvidia", "nvda", "nvidia corporation", "nvidia corp"], officialDomain="nvidia.com",
           irDomain="investor.nvidia.com"),
    Entity(entityId="e_apple", name="Apple Inc.", ticker="AAPL", exchange="NASDAQ",
           aliases=["apple", "aapl", "apple inc"], officialDomain="apple.com", irDomain="investor.apple.com"),
    Entity(entityId="e_microsoft", name="Microsoft Corporation", ticker="MSFT", exchange="NASDAQ",
           aliases=["microsoft", "msft", "microsoft corporation", "microsoft corp"], officialDomain="microsoft.com",
           irDomain="microsoft.com/en-us/investor"),
    Entity(entityId="e_amd", name="Advanced Micro Devices, Inc.", ticker="AMD", exchange="NASDAQ",
           aliases=["amd", "advanced micro devices"], officialDomain="amd.com", irDomain="ir.amd.com"),
    Entity(entityId="e_tesla", name="Tesla, Inc.", ticker="TSLA", exchange="NASDAQ",
           aliases=["tesla", "tsla"], officialDomain="tesla.com", irDomain="ir.tesla.com"),
]

_ALIAS_INDEX: dict[str, str] = {}
for _e in _SEED_ENTITIES:
    _ALIAS_INDEX[_e.name.lower()] = _e.entityId
    if _e.ticker:
        _ALIAS_INDEX[_e.ticker.lower()] = _e.entityId
    for _a in _e.aliases or []:
        _ALIAS_INDEX[_a.lower()] = _e.entityId


def resolve_entity(text: str) -> Optional[Entity]:
    """Resolve a name/ticker/alias to one canonical entity, or None.

    Deterministic: longest alias match wins so "advanced micro devices" beats
    "amd" only when the fuller form is present. Returns None when nothing matches
    — canonical identity is never invented.
    """
    lowered = (text or "").strip().lower()
    if not lowered:
        return None
    best: Optional[Entity] = None
    best_len = 0
    for entity in _SEED_ENTITIES:
        candidates = [entity.name.lower(), (entity.ticker or "").lower(), *(a.lower() for a in entity.aliases or [])]
        for alias in candidates:
            if alias and re.search(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", lowered):
                if len(alias) > best_len:
                    best_len = len(alias)
                    best = entity
    return best


def entity_aliases(entity_id: str) -> list[str]:
    for entity in _SEED_ENTITIES:
        if entity.entityId == entity_id:
            return [entity.name, *(entity.aliases or [])]
    return []


# ── Source ranking ───────────────────────────────────────────────────────────────

# Per research-type tier preferences (lower = better). The financial ordering
# explicitly matches the brief: SEC → regulators → filings → IR → financial data
# → reputable journalism → analyst → general web → social.
_RANK_TABLE: dict[str, tuple[SourceType, ...]] = {
    "financial": (
        SourceType.OFFICIAL_FILING, SourceType.REGULATOR, SourceType.GOVERNMENT,
        SourceType.INVESTOR_RELATIONS, SourceType.FINANCIAL_DATA, SourceType.NEWS,
        SourceType.ANALYST, SourceType.INDUSTRY, SourceType.ACADEMIC, SourceType.COMPANY,
        SourceType.WIKI, SourceType.BLOG, SourceType.FORUM, SourceType.SOCIAL, SourceType.UNKNOWN,
    ),
    "news": (
        SourceType.NEWS, SourceType.REGULATOR, SourceType.GOVERNMENT, SourceType.OFFICIAL_FILING,
        SourceType.COMPANY, SourceType.INDUSTRY, SourceType.ANALYST, SourceType.FINANCIAL_DATA,
        SourceType.WIKI, SourceType.BLOG, SourceType.FORUM, SourceType.SOCIAL, SourceType.UNKNOWN,
    ),
    "academic": (
        SourceType.ACADEMIC, SourceType.GOVERNMENT, SourceType.REGULATOR, SourceType.OFFICIAL_FILING,
        SourceType.INDUSTRY, SourceType.NEWS, SourceType.ANALYST, SourceType.WIKI, SourceType.BLOG,
        SourceType.FORUM, SourceType.SOCIAL, SourceType.UNKNOWN,
    ),
    # Learning ordering: official documentation first for an implementation goal,
    # then established courses, coherent lecture video series, repositories with
    # runnable code, academic theory, datasets, tutorials, then lower-signal web.
    # This is a RELEVANCE ordering for a learning objective, not a claim that one
    # source beats another for every goal; the ranking function weighs it.
    "learning": (
        SourceType.DOCUMENTATION, SourceType.COURSE, SourceType.VIDEO, SourceType.ACADEMIC,
        SourceType.REPOSITORY, SourceType.DATASET, SourceType.TUTORIAL, SourceType.INDUSTRY,
        SourceType.NEWS, SourceType.PODCAST, SourceType.BLOG, SourceType.WIKI, SourceType.FORUM,
        SourceType.SOCIAL, SourceType.UNKNOWN,
    ),
    "default": (
        SourceType.OFFICIAL_FILING, SourceType.GOVERNMENT, SourceType.REGULATOR, SourceType.ACADEMIC,
        SourceType.INVESTOR_RELATIONS, SourceType.COMPANY, SourceType.FINANCIAL_DATA, SourceType.NEWS,
        SourceType.INDUSTRY, SourceType.ANALYST, SourceType.WIKI, SourceType.BLOG, SourceType.FORUM,
        SourceType.SOCIAL, SourceType.UNKNOWN,
    ),
}


def _rank_position(research_type: str, source_type: SourceType) -> int:
    table = _RANK_TABLE.get(research_type, _RANK_TABLE["default"])
    try:
        return table.index(source_type)
    except ValueError:
        return len(table)


def rank_source(
    source: Source,
    *,
    research_type: str = "default",
    relevance: float = 0.0,
    published_at: Optional[str] = None,
    as_of: Optional[str] = None,
) -> dict[str, Any]:
    """Score a source for a research type. Explainable components, no fake precision.

    Returns a dict with component scores and a final `score` in [0, 1]. The score
    is an INTERNAL ordering signal; user-facing output never claims scientific
    precision from it.
    """
    components: dict[str, float] = {}
    table = _RANK_TABLE.get(research_type, _RANK_TABLE["default"])
    size = max(1, len(table))
    components["authority"] = 1.0 - (_rank_position(research_type, source.sourceType) / size)
    components["primary"] = 1.0 if source.authority == Authority.PRIMARY else (0.5 if source.authority == Authority.SECONDARY else 0.0)
    components["relevance"] = max(0.0, min(1.0, relevance))

    # Freshness: newer is better; unknown publication is neutral (0.5), never a
    # fabricated recency. Point-in-time cutoff is a hard filter upstream.
    pub = published_at or source.publishedAt
    components["freshness"] = _freshness_score(pub, as_of=as_of)

    # A source whose content hash exists was actually retrieved.
    components["completeness"] = 1.0 if source.contentHash else 0.4

    weights = {"authority": 0.35, "primary": 0.20, "relevance": 0.20, "freshness": 0.15, "completeness": 0.10}
    score = sum(weights[k] * components[k] for k in weights)
    return {"score": round(score, 4), "components": {k: round(v, 4) for k, v in components.items()}, "researchType": research_type}


def _freshness_score(published_at: Optional[str], *, as_of: Optional[str] = None) -> float:
    if not published_at:
        return 0.5
    from datetime import datetime, timezone

    try:
        text = str(published_at).replace("Z", "+00:00")
        pub = datetime.fromisoformat(text)
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=timezone.utc)
    except ValueError:
        return 0.5
    now = datetime.now(timezone.utc)
    age_days = max(0.0, (now - pub).total_seconds() / 86400.0)
    if age_days <= 1:
        return 1.0
    if age_days <= 7:
        return 0.9
    if age_days <= 30:
        return 0.75
    if age_days <= 365:
        return 0.5
    return 0.25


# ── News deduplication ───────────────────────────────────────────────────────────


@dataclass
class SourceFamily:
    familyId: str
    canonicalTitle: str
    memberUrls: list[str]
    publisher: Optional[str] = None


def _title_fingerprint(title: str) -> str:
    """Normalized title fingerprint for duplicate detection."""
    tokens = re.findall(r"[a-z0-9]{3,}", (title or "").lower())
    stop = {"the", "and", "for", "with", "from", "that", "this", "into", "over", "amid", "says", "said", "will", "after", "new"}
    keep = [t for t in tokens if t not in stop]
    return " ".join(sorted(keep[:12]))


def dedupe_news(items: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[SourceFamily]]:
    """Group syndicated/duplicate news so copies are not independent sources.

    Two articles are the same story when their normalized title fingerprints match
    OR their fetched content hashes match. The FIRST occurrence is canonical; every
    later copy is attached to the same `SourceFamily` and marked `syndicated=True`.
    """
    families: dict[str, SourceFamily] = {}
    out: list[dict[str, Any]] = []
    for item in items:
        title = str(item.get("title") or "")
        content = str(item.get("text") or item.get("contentHash") or "")
        fingerprint = _title_fingerprint(title)
        hash_key = content_hash(content) if content else ""
        key = fingerprint or hash_key
        if key and key in families:
            family = families[key]
            family.memberUrls.append(str(item.get("url") or ""))
            out.append({**item, "syndicated": True, "familyId": family.familyId})
            continue
        # Also merge when the content hash matches an existing family.
        if hash_key:
            for fam_key, fam in families.items():
                if fam_key == hash_key:
                    fam.memberUrls.append(str(item.get("url") or ""))
                    out.append({**item, "syndicated": True, "familyId": fam.familyId})
                    key = None
                    break
        if key is None:
            continue
        family_id = "fam_" + re.sub(r"[^a-z0-9]", "", key)[:16]
        families[key] = SourceFamily(familyId=family_id, canonicalTitle=title, memberUrls=[str(item.get("url") or "")])
        out.append({**item, "syndicated": False, "familyId": family_id})
    return out, list(families.values())


__all__ = [
    "Entity",
    "classify_source_type",
    "publisher_for",
    "make_source",
    "resolve_entity",
    "entity_aliases",
    "rank_source",
    "SourceFamily",
    "dedupe_news",
]
