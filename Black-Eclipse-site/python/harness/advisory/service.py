"""AdvisoryService — the ONE orchestrator for the Advisory Ledger.

It turns a Fiduciary Gate verdict into durable decisions and answers the two
questions the ledger exists for: "what did I recommend, and on what basis?" and
"was it right?". Reads are deterministic; nothing here places a trade or changes
a portfolio.
"""

from __future__ import annotations

from typing import Any, Optional

from ..persistence import now_iso
from .store import AdvisoryStore, decision_id as _decision_id

# Outcome verdicts (the closed vocabulary).
RIGHT = "right"
WRONG = "wrong"
NEUTRAL = "neutral"


def classify_outcome(realized: Optional[float], benchmark: Optional[float]) -> str:
    """right | wrong | neutral — beats the benchmark (or zero) or it doesn't."""
    if realized is None:
        return NEUTRAL
    if benchmark is None:
        return RIGHT if realized > 0 else (WRONG if realized < 0 else NEUTRAL)
    return RIGHT if realized > benchmark else (WRONG if realized < benchmark else NEUTRAL)


class AdvisoryService:
    def __init__(self, store: Any) -> None:
        self.store = AdvisoryStore(store)

    # ── Recording ────────────────────────────────────────────────────────────
    def record_verdict(
        self,
        *,
        run_id: Optional[str],
        verdict: dict[str, Any],
        portfolio_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        owner_id: Optional[str] = None,
        sources: Optional[list[str]] = None,
        entry_prices: Optional[dict[str, float]] = None,
    ) -> list[dict[str, Any]]:
        """Persist every claim in a gate verdict as a durable decision.

        Idempotent: the deterministic id means re-recording the same answer is a
        no-op, so a resumed run never double-counts. Basis rows capture WHY the
        claim was computed/sourced (or that it was unverified).
        """
        recorded: list[dict[str, Any]] = []
        source_refs = list(sources or [])[:20]
        prices = {str(k).upper(): float(v) for k, v in (entry_prices or {}).items()
                  if _is_positive(v)}
        for claim in verdict.get("claims") or []:
            action = str(claim.get("action") or "recommendation")
            symbols = tuple(claim.get("symbols") or [])
            target = claim.get("target")
            did = _decision_id(run_id, action, symbols, target)
            status = str(claim.get("status") or "unverified")
            reason = claim.get("reason")
            self.store.upsert_decision({
                "id": did, "runId": run_id, "portfolioId": portfolio_id,
                "conversationId": conversation_id, "ownerId": owner_id,
                "createdAt": now_iso(), "action": action, "symbols": list(symbols),
                "target": target, "thesis": _thesis(claim), "status": status,
                "truthReason": reason,
            })
            entries = self._basis_entries(status, reason, source_refs)
            entry = prices.get(str(symbols[0]).upper()) if symbols else None
            if entry is not None:
                entries.append({"kind": "entry_price", "ref": repr(entry),
                                "valueHash": str(symbols[0]).upper()})
            self.store.add_basis(did, entries)
            recorded.append(self.store.get_decision(did))
        return recorded

    @staticmethod
    def _basis_entries(status: str, reason: Optional[str], sources: list[str]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        if status == "computed":
            entries.append({"kind": "computation", "ref": reason})
        elif status == "sourced":
            entries.append({"kind": "source", "ref": reason})
        for url in sources:
            entries.append({"kind": "source", "ref": url})
        if not entries:
            entries.append({"kind": "none", "ref": None})
        return entries

    # ── Reads ────────────────────────────────────────────────────────────────
    def list_decisions(
        self, *, portfolio_id: Optional[str] = None, owner_id: Optional[str] = None,
        status: Optional[str] = None, limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.store.list_decisions(
            portfolio_id=portfolio_id, owner_id=owner_id, status=status, limit=limit,
        )

    def get_decision(self, decision_id: str) -> Optional[dict[str, Any]]:
        return self.store.get_decision(decision_id)

    # ── Outcomes ─────────────────────────────────────────────────────────────
    def record_outcome(
        self,
        decision_id: str,
        *,
        realized_return: float,
        benchmark_return: Optional[float] = None,
        horizon: Optional[str] = None,
        note: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Attach the realized result to a decision and label it right/wrong.

        A missing decision yields None (never a fabricated outcome). Returns and
        the benchmark are caller-supplied: a jurisdiction-neutral engine records
        what it is told rather than inventing a market result.
        """
        if self.store.get_decision(decision_id) is None:
            return None
        verdict = classify_outcome(realized_return, benchmark_return)
        return self.store.upsert_outcome(decision_id, {
            "evaluatedAt": now_iso(), "horizon": horizon,
            "realizedReturn": realized_return, "benchmarkReturn": benchmark_return,
            "verdict": verdict, "note": note,
        })

    def evaluate_outcome(
        self, decision_id: str, *, current_price: float,
        benchmark_return: Optional[float] = None,
        horizon: Optional[str] = None, note: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Evaluate a decision against a caller-supplied current price.

        The return is computed from the entry price captured when the decision was
        recorded; without one (or with a non-positive price) it is `None` — never a
        fabricated result. Deterministic.
        """
        record = self.store.get_decision(decision_id)
        if record is None:
            return None
        entry = _entry_price(record)
        price = _positive_or_none(current_price)
        if not entry or price is None:
            return None
        return self.record_outcome(
            decision_id, realized_return=(price / entry) - 1.0,
            benchmark_return=benchmark_return, horizon=horizon, note=note,
        )

    def evaluate_decisions(
        self, marks: dict[str, float], *, benchmark_return: Optional[float] = None,
        horizon: Optional[str] = None, limit: int = 5000,
    ) -> list[dict[str, Any]]:
        """Evaluate every open decision that has an entry price and a matching mark.

        The primitive a scheduled monitor or the operator uses to close the loop;
        a decision with no entry price or no mark is skipped, never invented.
        """
        normalized = {str(k).upper(): _positive_or_none(v) for k, v in (marks or {}).items()}
        results: list[dict[str, Any]] = []
        for row in self.store.list_decisions(limit=limit):
            decision = self.store.get_decision(row["id"])
            if decision is None or decision.get("outcome") or _entry_price(decision) is None:
                continue
            symbols = [str(s).upper() for s in decision.get("symbols") or []]
            price = next((normalized[s] for s in symbols if normalized.get(s) is not None), None)
            if price is None:
                continue
            outcome = self.evaluate_outcome(
                decision["id"], current_price=price,
                benchmark_return=benchmark_return, horizon=horizon,
            )
            if outcome is not None:
                results.append(outcome)
        return results

    async def auto_evaluate(
        self, gateway: Any, *, benchmark_return: Optional[float] = None,
        horizon: Optional[str] = None,
    ) -> dict[str, Any]:
        """Fetch current prices for open decisions and record their outcomes.

        The unattended closer: a monitor (or the operator) invokes it, and the
        gateway supplies the marks. A decision with no entry price or an
        unavailable quote is skipped, never fabricated. Returns what was evaluated
        and what was skipped, so a short report is honest.
        """
        if gateway is None:
            return {"evaluated": 0, "skipped": [], "reason": "no market gateway"}
        open_decisions = []
        for row in self.store.list_decisions(limit=5000):
            decision = self.store.get_decision(row["id"])
            if decision is not None and not decision.get("outcome") and _entry_price(decision):
                open_decisions.append(decision)
        skipped: list[str] = []
        symbols = {str(s).upper() for d in open_decisions for s in (d.get("symbols") or [])}
        marks: dict[str, float] = {}
        for symbol in symbols:
            try:
                quote = await gateway.get_quote(symbol)
            except Exception:  # noqa: BLE001 - an unavailable quote is a skip
                quote = None
            price = _positive_or_none(_quote_price(quote))
            if price is not None:
                marks[symbol] = price
        results = self.evaluate_decisions(marks, benchmark_return=benchmark_return, horizon=horizon)
        evaluated = {r["decisionId"] for r in results}
        for decision in open_decisions:
            if decision["id"] not in evaluated:
                skipped.append(decision["id"])
        return {"evaluated": len(results), "outcomes": results, "skipped": skipped}

    def scorecard(
        self, *, portfolio_id: Optional[str] = None, owner_id: Optional[str] = None,
    ) -> dict[str, Any]:
        """A deterministic summary of decisions and how they turned out."""
        decisions = self.store.list_decisions(
            portfolio_id=portfolio_id, owner_id=owner_id, limit=10_000,
        )
        by_status = {"computed": 0, "sourced": 0, "unverified": 0}
        for decision in decisions:
            if decision["status"] in by_status:
                by_status[decision["status"]] += 1
        outcomes = self.store.outcomes_for([d["id"] for d in decisions])
        counts = {RIGHT: 0, WRONG: 0, NEUTRAL: 0}
        realized: list[float] = []
        benchmark: list[float] = []
        for outcome in outcomes:
            counts[outcome["verdict"]] = counts.get(outcome["verdict"], 0) + 1
            if outcome["realizedReturn"] is not None:
                realized.append(outcome["realizedReturn"])
            if outcome["benchmarkReturn"] is not None:
                benchmark.append(outcome["benchmarkReturn"])
        decided = counts[RIGHT] + counts[WRONG]
        return {
            "total": len(decisions),
            "byStatus": by_status,
            "evaluated": len(outcomes),
            "outcomes": counts,
            "hitRate": (counts[RIGHT] / decided) if decided else None,
            "avgRealizedReturn": (sum(realized) / len(realized)) if realized else None,
            "avgBenchmarkReturn": (sum(benchmark) / len(benchmark)) if benchmark else None,
        }


def _quote_price(quote: Any) -> Optional[float]:
    if quote is None:
        return None
    if isinstance(quote, dict):
        return quote.get("price")
    return getattr(quote, "price", None)


def _entry_price(record: dict[str, Any]) -> Optional[float]:
    for entry in record.get("basis") or []:
        if entry.get("kind") == "entry_price":
            return _positive_or_none(entry.get("ref"))
    return None


def _positive_or_none(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _is_positive(value: Any) -> bool:
    return _positive_or_none(value) is not None


def _thesis(claim: dict[str, Any]) -> str:
    who = " ".join(claim.get("symbols") or []) or "the portfolio"
    to = f" to {claim['target']}" if claim.get("target") else ""
    return f"{claim.get('action')} {who}{to}".strip()


__all__ = ["AdvisoryService", "classify_outcome", "RIGHT", "WRONG", "NEUTRAL"]
