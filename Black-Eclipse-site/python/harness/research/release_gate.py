"""Evidence release gate — the ordinary-run citation-integrity check.

The gated research flow validates its claims before delivering (`research.run`).
An ORDINARY run reasons over tool-retrieved evidence and then composes prose; until
now nothing checked that prose against the evidence the run actually gathered. A
model could therefore cite a URL that was never retrieved and nothing detected it
before the answer was released.

This gate closes that at the existing answer seam (`graph.execute_run`). It is:

  * deterministic — no model call, so it works with any provider (or none);
  * narrow — it inspects only explicit http(s) citations, so an answer that makes
    no citations is never touched and ordinary conversation is never cluttered;
  * honest — it never strips content (suppression would hide a real answer). An
    unretrieved citation is disclosed as unverified, never silently deleted.

"Retrieved" means a source the run actually fetched or consulted (the same
`SourceCollector` provenance the chat Sources panel renders). A link with no such
provenance cannot be confirmed as evidence and is reported as unverified.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional
from urllib.parse import urlparse, urlunparse

# Reuses the SAME deterministic citation parsing as the evaluation citation grader
# (`evaluation/graders/citation.py`); kept local so the runtime never imports the
# evaluation subsystem.
_URL_RE = re.compile(r"https?://[^\s)\]}\"'<>]+")
_MD_LINK_RE = re.compile(r"\[[^\]]+\]\((https?://[^\s)]+)\)")

_PRIVATE_HOST_RE = re.compile(
    r"^(localhost|127\.|10\.|192\.168\.|169\.254\.|0\.0\.0\.0$)"
    r"|^172\.(1[6-9]|2\d|3[01])\."
)


def extract_urls(text: str) -> list[str]:
    """All distinct absolute http(s) URLs in `text`, markdown links first."""
    found = _MD_LINK_RE.findall(text or "")
    found += _URL_RE.findall(text or "")
    out: list[str] = []
    for url in found:
        url = url.rstrip(".,;:!?)\"'")
        if url and url not in out:
            out.append(url)
    return out


def _key(url: str) -> Optional[tuple[str, str]]:
    """(host, path) identity, ignoring scheme query/fragment and `www.`."""
    try:
        parsed = urlparse(url)
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return None
    path = (parsed.path or "").rstrip("/").lower()
    return host, path


def _display(url: str) -> str:
    """A URL safe to persist, emit and show: credentials are never carried.

    A cited URL can embed userinfo (`https://user:token@host/…`). The verdict is
    written to the run blob and emitted to the observability bus, so those
    credentials must not leave the gate. The host/path/query are preserved (a user
    needs them to see WHAT was cited); only the `user:pass@` authority is dropped.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    if not parsed.username and not parsed.password:
        return url
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, host, parsed.path, parsed.params, parsed.query, parsed.fragment))


def _is_checkable(url: str) -> bool:
    """Whether a URL is a real external citation we can meaningfully verify.

    Loopback and private-network hosts are excluded: they name the local app, not
    a research source, and flagging them would be noise.
    """
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    if host.endswith(".local"):
        return False
    return _PRIVATE_HOST_RE.match(host) is None


@dataclass
class CitationIntegrity:
    """The gate's verdict for one answer."""

    status: str  # ok | unverified | no_citations | no_evidence
    checked: int = 0
    verified: int = 0
    domainKnown: int = 0
    unverified: list[str] = field(default_factory=list)
    disclosure: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "checked": self.checked,
            "verified": self.verified,
            "domainKnown": self.domainKnown,
            "unverified": list(self.unverified),
        }

    @property
    def released(self) -> bool:
        """True when the answer may be released with no disclosure added."""
        return self.status in ("ok", "no_citations")


def _disclosure(unverified: list[str]) -> str:
    listed = ", ".join(unverified)
    return (
        "Evidence note: the following cited link(s) were not retrieved during this "
        f"run, so they are not backed by Eclipse evidence: {listed}. "
        "Treat them as unverified."
    )


def enforce_evidence_answer(
    answer: str,
    collector: Any,
    *,
    user_text: str = "",
    allow_urls: tuple[str, ...] = (),
) -> CitationIntegrity:
    """Check `answer`'s citations against the run's retrieved sources.

    Returns a `CitationIntegrity`; `disclosure` is set ONLY when a cited link has
    no provenance in this run. Never raises for a malformed URL and never mutates
    `answer` — the caller appends the disclosure.
    """
    urls = [u for u in extract_urls(answer) if _is_checkable(u)]
    if not urls:
        return CitationIntegrity(status="no_citations")

    known_keys: set[tuple[str, str]] = set()
    known_hosts: set[str] = set()

    def _remember(url: str) -> None:
        key = _key(url)
        if key is None:
            return
        known_hosts.add(key[0])
        if key[1]:
            known_keys.add(key)

    for url in _known_urls(collector):
        _remember(url)
    # A URL the user themselves supplied in the question is admissible even if the
    # run did not (re)fetch it: the user is the source of the pointer.
    for url in extract_urls(user_text):
        _remember(url)
    for url in allow_urls:
        _remember(url)

    if not known_keys and not known_hosts:
        # The answer cites sources but the run retrieved nothing at all: every
        # citation is unverifiable.
        shown = [_display(u) for u in urls]
        return CitationIntegrity(
            status="no_evidence", checked=len(urls), unverified=shown,
            disclosure=_disclosure(shown),
        )

    verified: list[str] = []
    domain_known: list[str] = []
    unverified: list[str] = []
    for url in urls:
        key = _key(url)
        if key is not None and key in known_keys:
            verified.append(_display(url))
        elif key is not None and key[0] in known_hosts:
            domain_known.append(_display(url))
        else:
            unverified.append(_display(url))

    status = "unverified" if unverified else "ok"
    return CitationIntegrity(
        status=status,
        checked=len(urls),
        verified=len(verified),
        domainKnown=len(domain_known),
        unverified=unverified,
        disclosure=_disclosure(unverified) if unverified else None,
    )


def _known_urls(collector: Any) -> set[str]:
    """Every URL the run actually retrieved or consulted (best-effort)."""
    if collector is None:
        return set()
    getter = getattr(collector, "known_urls", None)
    if callable(getter):
        try:
            return set(getter())
        except Exception:  # noqa: BLE001 - provenance is best-effort
            return set()
    return set()


async def apply(
    answer: str,
    collector: Any,
    *,
    emitter: Any = None,
    user_text: str = "",
) -> tuple[str, Optional[dict[str, Any]]]:
    """Run the gate over `answer`; append any disclosure and emit the verdict.

    Returns `(answer, verdict_dict_or_None)`. Never raises: enforcement at the
    answer seam is additive and must never fail a run. A no-citation answer is
    returned byte-for-byte unchanged.
    """
    try:
        verdict = enforce_evidence_answer(answer, collector, user_text=user_text)
    except Exception:  # noqa: BLE001 - never fatal
        return answer, None
    blob = verdict.to_dict()
    if verdict.disclosure:
        answer = f"{answer}\n\n{verdict.disclosure}"
    if verdict.status != "no_citations" and emitter is not None:
        try:
            await emitter.emit("evidence.release_gate", blob)
        except Exception:  # noqa: BLE001 - emission is best-effort
            pass
    return answer, blob


def attach(research_blob: Optional[dict[str, Any]], verdict: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Attach the citation-integrity verdict to a run's research blob.

    Returns the blob unchanged when there is no verdict or the answer made no
    citations. Creates a minimal `collected` blob when a verdict exists but the
    run otherwise collected nothing — an unverified citation with zero retrieved
    evidence is itself the signal the Sources panel must show.
    """
    if not verdict or verdict.get("status") == "no_citations":
        return research_blob
    blob = dict(research_blob or {})
    metadata = dict(blob.get("metadata") or {})
    metadata["citationIntegrity"] = verdict
    blob["metadata"] = metadata
    blob.setdefault("status", "collected")
    blob.setdefault("collected", True)
    return blob


__all__ = [
    "CitationIntegrity",
    "extract_urls",
    "enforce_evidence_answer",
    "apply",
    "attach",
]
