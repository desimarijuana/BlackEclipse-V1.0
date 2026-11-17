"""Intel orchestration: fetch → measure → score → persist.

The service owns the ONLY network calls in the intel package. Every collector
is injectable (`fetch`) and every clock is injectable (`today`), so the whole
pipeline can be exercised end-to-end from fixtures with no sockets.

Two behaviours are load-bearing:

  * **A hard deadline.** A scan runs inside a chat tool call, which has a
    bounded budget. When the deadline passes the scan returns the entities it
    finished and marks the rest `partial` — it never silently truncates.
  * **Per-signal unavailability.** "EDGAR returned nothing", "no Wikipedia
    article above the history floor" and "the fetch failed" are distinct
    reported reasons, because they mean different things to a reader.
"""

from __future__ import annotations

import asyncio
import gzip
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Iterable, Optional
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from . import attention, engine, sec
from .contracts import (
    ACTIVIST_STAKE,
    ATTENTION_VELOCITY,
    FILING_HEAT,
    INSIDER_CONVICTION,
    Observation,
    signal_catalog,
)
from .store import IntelStore

log = logging.getLogger("harness.intel")

_DEFAULT_UA = "BlackEclipse-Intel/1.0 (research@blackeclipse.local)"
_TICKERS_TTL_SECONDS = 3600.0
_tickers_cache: dict[str, Any] = {"at": 0.0, "map": {}}
_tickers_lock = threading.Lock()


def default_user_agent() -> str:
    """SEC wants a descriptive UA with contact info; operators can override."""
    return os.environ.get("BE_EDGAR_USER_AGENT", "").strip() or _DEFAULT_UA


def urllib_fetch(*, timeout: float = 20.0, min_interval: float = 0.12) -> sec.Fetch:
    """A polite, throttled GET. EDGAR's ceiling is 10 req/s; we stay under it."""
    state = {"last": 0.0}
    lock = threading.Lock()

    def fetch(url: str) -> str:
        with lock:
            gap = time.monotonic() - state["last"]
            if gap < min_interval:
                time.sleep(min_interval - gap)
            state["last"] = time.monotonic()
        request = Request(url, headers={
            "User-Agent": default_user_agent(),
            "Accept": "application/json, application/xml, text/xml, */*",
            "Accept-Encoding": "gzip",
        })
        with urlopen(request, timeout=timeout) as response:  # noqa: S310 - https only by construction
            raw = response.read()
            if (response.headers.get("Content-Encoding") or "").lower() == "gzip":
                raw = gzip.decompress(raw)
        return raw.decode("utf-8", "replace")

    return fetch


@dataclass
class ScanBudget:
    deadline: float
    total_seconds: float

    @property
    def remaining(self) -> float:
        return self.deadline - time.monotonic()

    def expired(self) -> bool:
        return self.remaining <= 0.0


class IntelService:
    """The one entry point: `scan`, `entity`, `cards`, `catalog`."""

    def __init__(
        self,
        store: Any,
        *,
        fetch: Optional[sec.Fetch] = None,
        today: Optional[Callable[[], date]] = None,
    ) -> None:
        self.store = IntelStore(store)
        self._fetch = fetch or urllib_fetch()
        self._today = today or date.today

    # ── Read-only surface ───────────────────────────────────────────────────
    def catalog(self) -> dict[str, Any]:
        return {
            "signals": signal_catalog(),
            "sources": [
                {
                    "id": "sec-edgar",
                    "name": "SEC EDGAR",
                    "auth": "none (descriptive User-Agent required)",
                    "rateLimit": "10 requests/second",
                    "forms": ["4", "5", "13D", "13G", "8-K"],
                },
                {
                    "id": "wikipedia",
                    "name": "Wikimedia Pageviews REST API",
                    "auth": "none",
                    "rateLimit": "polite use; ~100 req/s ceiling",
                },
            ],
            "scoring": {
                "weights": engine.WEIGHTS,
                "gates": engine.GATES,
                "horizons": engine.HORIZONS,
                "note": (
                    "Priority is a 0-1 triage order for a research queue. It is not a "
                    "probability and not an expected return."
                ),
            },
        }

    def entity(self, owner_id: str, ticker: str) -> dict[str, Any]:
        entity = str(ticker or "").strip().upper()
        if not entity:
            raise ValueError("ticker is required")
        latest = self.store.latest_per_signal(owner_id, entity)
        series = {
            signal: self.store.series(owner_id, entity, signal, limit=90)
            for signal in {row["signal"] for row in latest}
        }
        return {
            "entity": entity,
            "observations": latest,
            "series": series,
            "ref": self.store.get_ref(owner_id, entity),
        }

    def cards(self, owner_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """The most recent stored card per entity, newest first."""
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for row in self.store.list_scans(owner_id, limit=max(limit * 4, 40)):
            entity = str(row.get("entity") or "")
            if entity in seen:
                continue
            seen.add(entity)
            payload = row.get("payload") or {}
            if payload:
                out.append(payload)
            if len(out) >= limit:
                break
        return engine_rank(out, limit)

    # ── Scan ────────────────────────────────────────────────────────────────
    async def scan(
        self,
        owner_id: str,
        entities: Iterable[str],
        *,
        as_of: Optional[str] = None,
        window_days: int = 90,
        max_entities: int = 4,
        max_filings: int = 8,
        deadline_seconds: float = 20.0,
        price_context: Optional[dict[str, dict[str, Any]]] = None,
    ) -> dict[str, Any]:
        wanted = [str(e or "").strip().upper() for e in entities if str(e or "").strip()]
        wanted = list(dict.fromkeys(wanted))[: max(1, int(max_entities))]
        if not wanted:
            raise ValueError("at least one ticker is required")
        started = time.monotonic()
        budget = ScanBudget(time.monotonic() + max(2.0, float(deadline_seconds)),
                            max(2.0, float(deadline_seconds)))
        return await asyncio.to_thread(
            self._scan_sync, owner_id, wanted, as_of, int(window_days),
            int(max_filings), budget, price_context or {}, started,
        )

    def _scan_sync(
        self,
        owner_id: str,
        entities: list[str],
        as_of: Optional[str],
        window_days: int,
        max_filings: int,
        budget: ScanBudget,
        price_context: dict[str, dict[str, Any]],
        started: float,
    ) -> dict[str, Any]:
        as_of_date = self._as_of(as_of)
        as_of_text = as_of_date.isoformat()
        results: list[dict[str, Any]] = []
        cards: list[dict[str, Any]] = []
        skipped: list[str] = []

        for entity in entities:
            if budget.expired():
                skipped.append(entity)
                continue
            try:
                result = self._scan_entity(
                    owner_id, entity, as_of_date, window_days, max_filings,
                    budget, price_context.get(entity) or price_context.get(entity.lower()),
                )
            except Exception as exc:  # noqa: BLE001 - one entity must not sink the scan
                log.warning("intel scan failed for %s", entity, exc_info=True)
                result = {
                    "entity": entity, "status": "error",
                    "reason": f"{type(exc).__name__}: {exc}",
                    "observations": [], "missing": {}, "card": None,
                }
            results.append(result)
            if result.get("card"):
                cards.append(result["card"])

        return {
            "asOf": as_of_text,
            "windowDays": window_days,
            "entities": results,
            "cards": engine_rank(cards, 20),
            "scanned": len([r for r in results if r.get("status") == "ok"]),
            "skipped": skipped,
            "partial": bool(skipped),
            "elapsedMs": int((time.monotonic() - started) * 1000),
            "note": (
                "Priority is a triage order, not a probability or an expected return. "
                "A missing signal means it could not be measured, never that it was zero."
            ),
        }

    def _scan_entity(
        self,
        owner_id: str,
        entity: str,
        as_of: date,
        window_days: int,
        max_filings: int,
        budget: ScanBudget,
        price_context: Optional[dict[str, Any]],
    ) -> dict[str, Any]:
        observations: list[Observation] = []
        missing: dict[str, str] = {}
        notes: list[str] = []

        ref = self._resolve(owner_id, entity)
        if not ref or not ref.get("cik"):
            return {
                "entity": entity, "status": "unavailable",
                "reason": f"{entity} is not in SEC's ticker→CIK map",
                "observations": [], "missing": {s: "unresolved entity" for s in (
                    INSIDER_CONVICTION, ACTIVIST_STAKE, FILING_HEAT)},
                "card": None,
            }
        cik = str(ref["cik"]).zfill(10)
        name = str(ref.get("name") or "")

        filings: list[sec.Filing] = []
        try:
            payload = json.loads(self._fetch(sec.SUBMISSIONS_URL.format(cik=cik)))
            filings = sec.parse_submissions(payload)
        except Exception as exc:  # noqa: BLE001 - EDGAR being down is UNAVAILABLE
            for signal in (INSIDER_CONVICTION, ACTIVIST_STAKE, FILING_HEAT):
                missing[signal] = f"EDGAR submissions unavailable ({type(exc).__name__})"

        if filings:
            since = (as_of - timedelta(days=window_days)).isoformat()
            observation, reason = self._insider_observation(
                entity, cik, filings, since=since, budget=budget,
                max_filings=max_filings, as_of=as_of, window_days=window_days,
            )
            if observation is not None:
                observations.append(observation)
            else:
                missing[INSIDER_CONVICTION] = reason or "no Form 4 in the window"

            activist = sec.filings_since(filings, since, sec.FORM_ACTIVIST)
            observations.append(Observation(
                entity=entity, signal=ACTIVIST_STAKE, as_of=as_of.isoformat(),
                value=float(len(activist)), unit="count", window_days=window_days,
                confidence=0.85, source="sec-edgar",
                method=f"count of Schedule 13D filings in the trailing {window_days}d",
                detail={"filings": [f.to_dict() for f in activist[:10]]},
                provenance={"cik": cik, "since": since},
            ))

            heat, reason = self._filing_heat(entity, filings, as_of=as_of, window_days=window_days)
            if heat is not None:
                observations.append(heat)
            else:
                missing[FILING_HEAT] = reason or "insufficient filing history"
        else:
            missing[INSIDER_CONVICTION] = "no EDGAR filings list available"

        try:
            reading = attention.fetch_reading(
                self._fetch, company_name=name or entity, as_of=as_of.isoformat(),
                article=(ref or {}).get("article") or None,
            )
        except Exception as exc:  # noqa: BLE001
            reading = None
            missing[ATTENTION_VELOCITY] = f"pageview fetch failed ({type(exc).__name__})"
        if reading is not None:
            observations.append(Observation(
                entity=entity, signal=ATTENTION_VELOCITY, as_of=as_of.isoformat(),
                value=float(reading.zscore), unit="zscore", window_days=window_days,
                confidence=reading.confidence, source="wikipedia",
                method=reading.method, detail=reading.to_dict(),
                provenance={**reading.provenance, "article": reading.article},
                note=(
                    f"Wikipedia article '{reading.article}' is the attention proxy; "
                    "curiosity is not buying."
                ),
            ))
            if reading.article and ref is not None and reading.article != ref.get("article"):
                self.store.put_ref(owner_id, entity, cik=cik, name=name, article=reading.article)
        elif ATTENTION_VELOCITY not in missing:
            missing[ATTENTION_VELOCITY] = (
                "no English Wikipedia article with 30+ days of pageview history"
            )

        days_since_buy = window_days
        for observation in observations:
            if observation.signal == INSIDER_CONVICTION:
                last_buy = str((observation.detail or {}).get("lastBuy") or "")
                if last_buy:
                    try:
                        days_since_buy = max(
                            0, (as_of - datetime.strptime(last_buy, "%Y-%m-%d").date()).days
                        )
                    except ValueError:
                        pass

        payloads = [observation.to_dict() for observation in observations]
        self.store.write_observations(owner_id, payloads)

        card = engine.build_opportunity(
            entity, payloads, as_of=as_of.isoformat(),
            price_context=price_context, days_since_last_buy=days_since_buy,
        )
        created = datetime.now(timezone.utc).isoformat(timespec="seconds")
        if card is not None:
            self.store.write_scan(owner_id, card.to_dict(), as_of=as_of.isoformat(), created_at=created)

        return {
            "entity": entity,
            "status": "ok",
            "name": name,
            "cik": cik,
            "observations": payloads,
            "missing": missing,
            "notes": notes,
            "card": card.to_dict() if card else None,
        }

    # ── Collectors ──────────────────────────────────────────────────────────
    def _insider_observation(
        self,
        entity: str,
        cik: str,
        filings: list[sec.Filing],
        *,
        since: str,
        budget: ScanBudget,
        max_filings: int,
        as_of: date,
        window_days: int,
    ) -> tuple[Optional[Observation], str]:
        targets = sec.filings_since(
            filings, since, [sec.FORM_INSIDER, sec.FORM_LATE_INSIDER]
        )[: max(1, int(max_filings))]
        if not targets:
            return None, "no Form 4/5 filings in the window"

        path_cik = cik.lstrip("0") or "0"
        trades: list[sec.InsiderTrade] = []
        failures = 0

        def read_one(filing: sec.Filing) -> Optional[list[sec.InsiderTrade]]:
            """Raw document directly, then the index as a fallback.

            Returns None when the document could NOT be read; an empty list is a
            genuine "this filing carries no non-derivative transaction", which is
            not a failure.
            """
            if budget.expired():
                return None
            guess = (filing.primary_document or "").split("/")[-1]
            candidates: list[str] = []
            if guess.lower().endswith(".xml") and not guess.lower().startswith("xsl"):
                candidates.append(guess)
            try:
                if not candidates:
                    index = json.loads(self._fetch(
                        sec.ARCHIVE_DIR_URL.format(cik=path_cik, accession=filing.accession_dir)
                    ))
                    items = (index.get("directory") or {}).get("item") or []
                    document = sec.xml_document_name(items, filing.primary_document)
                    if document:
                        candidates.append(document)
                for name in candidates:
                    xml = self._fetch(sec.ARCHIVE_FILE_URL.format(
                        cik=path_cik, accession=filing.accession_dir, name=name,
                    ))
                    return sec.parse_form4(xml, accession=filing.accession)
            except Exception:  # noqa: BLE001 - one bad filing is a skipped row
                return None
            return []

        # Bounded fan-out: EDGAR allows 10 req/s and the throttle enforces it, so
        # four in-flight reads cut wall-clock without exceeding the courtesy cap.
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=4) as pool:
            for found in pool.map(read_one, targets):
                if found is None:
                    failures += 1
                else:
                    trades.extend(found)

        summary = sec.summarize(trades, window_days=window_days)
        if not summary.has_any and summary.filings_scanned == 0 and failures >= len(targets):
            return None, "EDGAR Form 4 documents could not be read"

        coverage = 0.5 + 0.05 * min(summary.filings_scanned, 8)
        confidence = min(0.9, coverage) * (1.0 - (failures / max(len(targets), 1)) * 0.5)
        note = ""
        if summary.planned_excluded:
            note = (
                f"{summary.planned_excluded} planned (Rule 10b5-1) or noise-code "
                "transaction(s) were excluded from conviction."
            )
        return Observation(
            entity=entity,
            signal=INSIDER_CONVICTION, as_of=as_of.isoformat(),
            value=round(summary.net_usd, 2), unit="usd", window_days=window_days,
            confidence=round(max(0.2, confidence), 3), source="sec-edgar",
            method=(
                "sum of Form 4 open-market purchases (code P) minus unplanned sales "
                "(code S); 10b5-1 plans, grants, option exercises and tax withholding excluded"
            ),
            detail=summary.to_dict(),
            provenance={
                "filings": len(targets), "failures": failures,
                "accessions": [f.accession for f in targets[:12]],
                "since": since,
            },
            direction_hint="bullish" if summary.net_usd > 0 else "watch",
            note=note,
        ), ""

    def _filing_heat(
        self, entity: str, filings: list[sec.Filing], *, as_of: date, window_days: int,
    ) -> tuple[Optional[Observation], str]:
        end = as_of.isoformat()
        start30 = (as_of - timedelta(days=30)).isoformat()
        prior_start = (as_of - timedelta(days=210)).isoformat()
        recent = sec.count_filings(filings, start30, end)
        prior = sec.count_filings(filings, prior_start, start30)
        prior_per_30 = prior / 6.0
        if prior == 0 and recent == 0:
            return None, "no filings in either window"
        ratio = recent / max(prior_per_30, 0.5)
        return Observation(
            entity=entity, signal=FILING_HEAT, as_of=end,
            value=round(ratio, 3), unit="ratio", window_days=30,
            confidence=0.7 if prior >= 6 else 0.5, source="sec-edgar",
            method="filings in the last 30d ÷ (filings in the prior 180d ÷ 6)",
            detail={"recent30": recent, "prior180": prior, "priorPer30": round(prior_per_30, 2)},
            provenance={"asOf": end},
            note="Proxy season and 10-K exhibit filing inflate the count seasonally." if prior < 6 else "",
        ), ""

    # ── Helpers ─────────────────────────────────────────────────────────────
    def _as_of(self, value: Optional[str]) -> date:
        if value:
            try:
                return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
            except ValueError:
                pass
        return self._today()

    def _tickers(self) -> dict[str, dict[str, str]]:
        now = time.monotonic()
        with _tickers_lock:
            if _tickers_cache["map"] and now - float(_tickers_cache["at"]) < _TICKERS_TTL_SECONDS:
                return _tickers_cache["map"]  # type: ignore[return-value]
        payload = json.loads(self._fetch(sec.COMPANY_TICKERS_URL))
        mapping = sec.parse_company_tickers(payload)
        with _tickers_lock:
            _tickers_cache["map"] = mapping
            _tickers_cache["at"] = now
        return mapping

    def _resolve(self, owner_id: str, entity: str) -> Optional[dict[str, Any]]:
        cached = self.store.get_ref(owner_id, entity)
        if cached and cached.get("cik"):
            return cached
        try:
            row = self._tickers().get(entity)
        except Exception:  # noqa: BLE001 - an unreachable EDGAR is UNAVAILABLE
            log.warning("company ticker map unavailable", exc_info=True)
            return cached
        if not row:
            return cached
        self.store.put_ref(owner_id, entity, cik=row["cik"], name=row["name"])
        return {"ticker": entity, "cik": row["cik"], "name": row["name"],
                "article": (cached or {}).get("article") or ""}


# ── Module helpers ──────────────────────────────────────────────────────────

def engine_rank(cards: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    ordered = sorted(cards, key=lambda c: (-float(c.get("priority") or 0), str(c.get("entity") or "")))
    return ordered[: max(1, int(limit))]


__all__ = ["IntelService", "ScanBudget", "default_user_agent", "engine_rank", "urllib_fetch"]
