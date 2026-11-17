"""SEC EDGAR intelligence: insider transactions, activist stakes, filing cadence.

EDGAR is the one public market dataset with no key, no licence and no rate
surprise (10 requests/second, a descriptive `User-Agent`). It is also the only
source that tells you what an officer did with *their own money*.

The design is deliberately split:

  * **parsing is pure** — XML/JSON text in, typed records out. No network, no
    clock. Every parser here is tested against a real filing's shape.
  * **fetching is injected** — `fetch(url) -> str`. The service passes a
    throttled urllib implementation; tests pass a fixture map.

What we deliberately EXCLUDE from "insider buying", because including it is how
most screens end up measuring nothing:

  * code `A` (grant/award) and `M` (option exercise) — compensation, not conviction;
  * code `F` and `C` (tax withholding / conversion) — mechanical;
  * any transaction flagged as a Rule 10b5-1 plan — scheduled, not discretionary.

That exclusion is the whole point: an unplanned open-market purchase by an
officer is a different event from a director's automatic sale.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

Fetch = Callable[[str], str]

COMPANY_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVE_DIR_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json"
ARCHIVE_FILE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{name}"

#: Forms that carry a discretionary transaction view.
FORM_INSIDER = "4"
FORM_LATE_INSIDER = "5"
FORM_ACTIVIST = ("13D", "13D/A", "SC 13D", "SC 13D/A")

#: Codes we treat as an unplanned, discretionary, open-market action.
DISCRETIONARY_BUY = "P"
DISCRETIONARY_SELL = "S"

#: Codes that are compensation or mechanical, never conviction.
NOISE_CODES = frozenset({"A", "M", "F", "C", "G", "D", "J", "L", "U", "V", "W", "X", "Z"})

_PLAN_RE = re.compile(r"10b\s*[-‑–]?\s*5\s*[-‑–]?\s*1", re.IGNORECASE)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def _element(node: ET.Element, path: str) -> Optional[ET.Element]:
    for child in node.iter():
        if _local(child.tag) == path:
            return child
    return None


def _text(node: ET.Element, path: str) -> str:
    """Read a field's text, namespace-tolerant, unwrapping EDGAR's `<value>`.

    Real filings nest scalars one level (`<transactionShares><value>2399
    </value></transactionShares>`), while a handful of fields are direct text
    (`<transactionCode>S</transactionCode>`). Both shapes resolve here.
    """
    element = _element(node, path)
    if element is None:
        return ""
    for child in element:
        if _local(child.tag) == "value":
            return (child.text or "").strip()
    return (element.text or "").strip()


def _num(node: ET.Element, path: str) -> Optional[float]:
    raw = _text(node, path)
    if not raw:
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _children(node: ET.Element, name: str) -> Iterable[ET.Element]:
    for child in node:
        if _local(child.tag) == name:
            yield child


def _bool(node: ET.Element, path: str) -> bool:
    return _text(node, path).lower() in ("1", "true", "yes")


# ── Entity resolution ───────────────────────────────────────────────────────

def parse_company_tickers(payload: Any) -> dict[str, dict[str, str]]:
    """`{TICKER: {"cik": "0000320193", "name": "Apple Inc."}}` from SEC's map."""
    out: dict[str, dict[str, str]] = {}
    if not isinstance(payload, dict):
        return out
    for row in payload.values():
        if not isinstance(row, dict):
            continue
        ticker = str(row.get("ticker") or "").strip().upper()
        cik = str(row.get("cik_str") or "").strip()
        if not ticker or not cik:
            continue
        out[ticker] = {
            "cik": cik.zfill(10),
            "name": str(row.get("title") or "").strip(),
        }
    return out


# ── Filings list ────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Filing:
    form: str
    filed: str  # YYYY-MM-DD
    accession: str
    primary_document: str = ""

    @property
    def accession_dir(self) -> str:
        return self.accession.replace("-", "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "form": self.form, "filed": self.filed,
            "accession": self.accession,
            "primaryDocument": self.primary_document,
        }


def parse_submissions(payload: Any) -> list[Filing]:
    """Flatten `filings.recent` into filings, newest first, plus older shards.

    Only the `recent` block is read: it holds the last ~1000 filings, far more
    than any short-window screen needs, and reading the paginated `files` shards
    would multiply requests for no analytical gain.
    """
    if not isinstance(payload, dict):
        return []
    block = (payload.get("filings") or {}).get("recent") or {}
    forms = block.get("form") or []
    dates = block.get("filingDate") or []
    accessions = block.get("accessionNumber") or []
    docs = block.get("primaryDocument") or []
    out: list[Filing] = []
    for index, form in enumerate(forms):
        if index >= len(dates) or index >= len(accessions):
            break
        out.append(Filing(
            form=str(form or "").strip(),
            filed=str(dates[index] or "").strip(),
            accession=str(accessions[index] or "").strip(),
            primary_document=str(docs[index] or "").strip() if index < len(docs) else "",
        ))
    return out


def filings_since(filings: Iterable[Filing], since: str, forms: Optional[Iterable[str]] = None) -> list[Filing]:
    """Filings on/after `since` (ISO dates compare lexically), newest first."""
    wanted = {f.upper() for f in forms} if forms else None
    out = []
    for filing in filings:
        if not filing.filed or filing.filed < since:
            continue
        if wanted is not None and filing.form.upper() not in wanted:
            continue
        out.append(filing)
    return out


def count_filings(filings: Iterable[Filing], start: str, end: str) -> int:
    return sum(1 for f in filings if start <= (f.filed or "") < end)


# ── Form 4 ──────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class InsiderTrade:
    owner: str
    is_officer: bool
    is_director: bool
    is_ten_percent: bool
    title: str
    code: str
    shares: float
    price: Optional[float]
    acquired: bool
    traded_on: str
    planned: bool  # Rule 10b5-1 / pre-scheduled
    accession: str = ""
    form: str = "4"

    @property
    def dollars(self) -> Optional[float]:
        if self.price is None or self.shares <= 0:
            return None
        return self.shares * self.price

    @property
    def discretionary_buy(self) -> bool:
        return self.code == DISCRETIONARY_BUY and self.acquired and not self.planned

    @property
    def discretionary_sell(self) -> bool:
        return self.code == DISCRETIONARY_SELL and not self.acquired and not self.planned

    def to_dict(self) -> dict[str, Any]:
        return {
            "owner": self.owner, "officer": self.is_officer,
            "director": self.is_director, "tenPercent": self.is_ten_percent,
            "title": self.title, "code": self.code, "shares": self.shares,
            "price": self.price, "dollars": self.dollars,
            "acquired": self.acquired, "tradedOn": self.traded_on,
            "planned": self.planned, "accession": self.accession, "form": self.form,
        }


def _footnote_texts(root: ET.Element) -> dict[str, str]:
    out: dict[str, str] = {}
    for node in root.iter():
        if _local(node.tag) == "footnote":
            ident = node.get("id") or ""
            text = " ".join((node.itertext() or [])).strip()
            if ident:
                out[ident] = text
    return out


def _is_planned(root: ET.Element, footnotes: dict[str, str]) -> bool:
    """A plan flag OR a footnote naming Rule 10b5-1.

    EDGAR's `aff10b5One` covers the filing; the footnote catches issuers that
    leave the flag false while describing the plan in text.
    """
    if _bool(root, "aff10b5One"):
        return True
    return any(_PLAN_RE.search(text or "") for text in footnotes.values())


def parse_form4(xml_text: str, *, accession: str = "") -> list[InsiderTrade]:
    """Parse one ownership document into its non-derivative transactions.

    Returns [] (not an error) for a filing that carries no transaction rows —
    a legitimate Form 4 amendment shape. Raise only on malformed XML.
    """
    raw = (xml_text or "").lstrip("\ufeff").strip()
    if not raw:
        return []
    root = ET.fromstring(raw)
    form = _text(root, "documentType") or "4"
    planned = _is_planned(root, _footnote_texts(root))

    owners: list[dict[str, Any]] = []
    for owner in _children(root, "reportingOwner"):
        relationship = next(_children(owner, "reportingOwnerRelationship"), None)
        owners.append({
            "name": _text(owner, "rptOwnerName") or "unknown",
            "officer": _bool(relationship, "isOfficer") if relationship is not None else False,
            "director": _bool(relationship, "isDirector") if relationship is not None else False,
            "ten": _bool(relationship, "isTenPercentOwner") if relationship is not None else False,
            "title": _text(relationship, "officerTitle") if relationship is not None else "",
        })
    if not owners:
        owners = [{"name": "unknown", "officer": False, "director": False, "ten": False, "title": ""}]

    trades: list[InsiderTrade] = []
    for table in _children(root, "nonDerivativeTable"):
        for tx in _children(table, "nonDerivativeTransaction"):
            code = _text(tx, "transactionCode").upper()
            if not code:
                continue
            shares = _num(tx, "transactionShares")
            if shares is None or shares <= 0:
                continue
            price = _num(tx, "transactionPricePerShare")
            disposed = _text(tx, "transactionAcquiredDisposedCode").upper()
            acquired = disposed == "A" or not disposed
            traded_on = _text(tx, "transactionDate")
            for owner in owners:
                trades.append(InsiderTrade(
                    owner=owner["name"],
                    is_officer=bool(owner["officer"]),
                    is_director=bool(owner["director"]),
                    is_ten_percent=bool(owner["ten"]),
                    title=str(owner["title"] or ""),
                    code=code,
                    shares=float(shares),
                    price=price,
                    acquired=acquired,
                    traded_on=traded_on,
                    planned=planned and code in (DISCRETIONARY_BUY, DISCRETIONARY_SELL),
                    accession=accession,
                    form=form,
                ))
    return trades


def xml_document_name(items: list[dict[str, Any]], primary_document: str = "") -> Optional[str]:
    """Pick the ownership XML from a filing index (prefer the raw over the XSL)."""
    names = [str(item.get("name") or "") for item in items if isinstance(item, dict)]
    xml = [n for n in names if n.lower().endswith(".xml")]
    plain = [n for n in xml if not n.lower().startswith("xsl")]
    if primary_document:
        base = primary_document.split("/")[-1]
        if base.lower().endswith(".xml") and base in plain:
            return base
    for preferred in ("form4.xml", "doc4.xml", "primary_doc.xml"):
        for name in plain:
            if name.lower() == preferred:
                return name
    if plain:
        return plain[0]
    return xml[0] if xml else None


# ── Summary ─────────────────────────────────────────────────────────────────

@dataclass
class InsiderSummary:
    """The deterministic read of a window of Form 4s for one issuer."""

    window_days: int
    buy_usd: float = 0.0
    sell_usd: float = 0.0
    buyers: list[str] = field(default_factory=list)
    sellers: list[str] = field(default_factory=list)
    officer_buyers: list[str] = field(default_factory=list)
    buys: list[dict[str, Any]] = field(default_factory=list)
    sells: list[dict[str, Any]] = field(default_factory=list)
    filings_scanned: int = 0
    planned_excluded: int = 0
    noise_excluded: int = 0
    unpriced_buys: int = 0
    last_buy: Optional[str] = None
    last_sell: Optional[str] = None

    @property
    def net_usd(self) -> float:
        return self.buy_usd - self.sell_usd

    @property
    def buyer_count(self) -> int:
        return len(self.buyers)

    @property
    def cluster(self) -> bool:
        """Two or more distinct people buying opportunistically."""
        return len(self.buyers) >= 2

    @property
    def has_any(self) -> bool:
        return bool(self.buys or self.sells)

    def to_dict(self) -> dict[str, Any]:
        return {
            "windowDays": self.window_days,
            "buyUsd": round(self.buy_usd, 2),
            "sellUsd": round(self.sell_usd, 2),
            "netUsd": round(self.net_usd, 2),
            "buyers": list(self.buyers),
            "sellers": list(self.sellers),
            "officerBuyers": list(self.officer_buyers),
            "buyCount": len(self.buys),
            "sellCount": len(self.sells),
            "filingsScanned": self.filings_scanned,
            "plannedExcluded": self.planned_excluded,
            "noiseExcluded": self.noise_excluded,
            "unpricedBuys": self.unpriced_buys,
            "lastBuy": self.last_buy,
            "lastSell": self.last_sell,
            "cluster": self.cluster,
        }


def summarize(trades: Iterable[InsiderTrade], *, window_days: int = 90) -> InsiderSummary:
    summary = InsiderSummary(window_days=int(window_days))
    seen_filings: set[str] = set()
    buyers: list[str] = []
    sellers: list[str] = []
    officers: list[str] = []
    for trade in trades:
        if trade.accession:
            seen_filings.add(trade.accession)
        if trade.planned:
            summary.planned_excluded += 1
            continue
        if trade.code in NOISE_CODES or not (trade.discretionary_buy or trade.discretionary_sell):
            summary.noise_excluded += 1
            continue
        row = trade.to_dict()
        if trade.discretionary_buy:
            dollars = trade.dollars
            if dollars is None:
                summary.unpriced_buys += 1
                continue
            summary.buy_usd += dollars
            summary.buys.append(row)
            if trade.owner not in buyers:
                buyers.append(trade.owner)
            if (trade.is_officer or trade.is_director) and trade.owner not in officers:
                officers.append(trade.owner)
            if not summary.last_buy or trade.traded_on > summary.last_buy:
                summary.last_buy = trade.traded_on
        elif trade.discretionary_sell:
            dollars = trade.dollars or 0.0
            summary.sell_usd += dollars
            summary.sells.append(row)
            if trade.owner not in sellers:
                sellers.append(trade.owner)
            if not summary.last_sell or trade.traded_on > summary.last_sell:
                summary.last_sell = trade.traded_on
    summary.buyers = buyers
    summary.sellers = sellers
    summary.officer_buyers = officers
    summary.filings_scanned = len(seen_filings)
    return summary


__all__ = [
    "COMPANY_TICKERS_URL", "DISCRETIONARY_BUY", "DISCRETIONARY_SELL", "Fetch",
    "Filing", "FORM_ACTIVIST", "FORM_INSIDER", "FORM_LATE_INSIDER", "InsiderSummary",
    "InsiderTrade", "NOISE_CODES", "SUBMISSIONS_URL", "ARCHIVE_DIR_URL",
    "ARCHIVE_FILE_URL", "count_filings", "filings_since", "parse_company_tickers",
    "parse_form4", "parse_submissions", "summarize", "xml_document_name",
]
