"""The trade-learning conductor.

It connects the four stages without owning any of them: detectors observe,
`TradeLearningStore` persists, the one recurrence ledger counts, `climb` proposes
and selects, and the playbook gate decides. This module only decides *when* each
runs and what the honest result is — it is not a second loop engine.
"""

from __future__ import annotations

import datetime as _dt
from typing import Any, Optional

from .climb import climb
from .detectors import review
from .model import Playbook, Trade, parse_trades
from .playbook import PlaybookRefused
from .store import TradeLearningStore

#: Above this the in-window count alone is not enough; the finding must also have
#: cost real R (when R is available) to be worth changing behaviour for.
DEFAULT_MIN_OCCURRENCES = 3
DEFAULT_WINDOW_DAYS = 90
DEFAULT_MIN_COST_R = 1.0
DEFAULT_MIN_COVERAGE = 0.8


def _since(days: int) -> str:
    moment = _dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(days=max(1, int(days)))
    return moment.isoformat()


def _priority(entry: dict[str, Any]) -> float:
    return float(entry["windowCount"]) * (entry.get("meanCostR") or 1.0)


class TradeLearningService:
    def __init__(self, store: TradeLearningStore, run_store: Any = None) -> None:
        self.store = store
        self.run_store = run_store

    # ── observe ──────────────────────────────────────────────────────────────

    def review(
        self,
        trades: Any,
        *,
        executions: Any = None,
        playbook: Any = None,
        detectors: Optional[list[str]] = None,
        config: Optional[dict[str, Any]] = None,
        now: Optional[_dt.datetime] = None,
    ) -> dict[str, Any]:
        parsed = parse_trades(trades)
        book = Playbook.from_dict(playbook) if isinstance(playbook, dict) else (
            playbook if isinstance(playbook, Playbook) else None
        )
        return review(
            parsed, executions=executions, playbook=book, detectors=detectors,
            config=config, now=now,
        )

    # ── learn ────────────────────────────────────────────────────────────────

    def learn(
        self,
        findings: list[dict[str, Any]],
        *,
        coverage: Optional[dict[str, Any]] = None,
        profile_id: str = "local",
        min_occurrences: int = DEFAULT_MIN_OCCURRENCES,
        window_days: int = DEFAULT_WINDOW_DAYS,
        min_cost_r: float = DEFAULT_MIN_COST_R,
        min_coverage: float = DEFAULT_MIN_COVERAGE,
        draft_candidates: bool = True,
    ) -> dict[str, Any]:
        recorded = self.store.record_findings(findings, profile_id=profile_id)
        ledger = self.store.record_recurrence(findings)
        since = _since(window_days)

        grouped: dict[str, dict[str, Any]] = {}
        for finding in findings:
            if not isinstance(finding, dict):
                continue
            signature = str(finding.get("signature") or "")
            if not signature:
                continue
            row = grouped.setdefault(signature, {
                "signature": signature,
                "category": str(finding.get("category") or "unknown"),
                "severity": str(finding.get("severity") or "medium"),
                "sampleFinding": finding,
            })
            # A signature is never downgraded by a later finding: if any
            # occurrence is high severity, the pattern is high severity.
            if str(finding.get("severity") or "") == "high":
                row["severity"] = "high"

        recurring: list[dict[str, Any]] = []
        created: list[dict[str, Any]] = []
        for signature, row in grouped.items():
            stats = self.store.signature_stats(
                signature, profile_id=profile_id, since=since,
            )
            category = row["category"]
            fraction = float(
                ((coverage or {}).get(category) or {}).get("fraction", 1.0)
            )
            total = int(ledger.get(signature) or self.store.ledger_count(signature))
            window_count = int(stats["occurrences"])
            cost_r = stats.get("costR")
            mean_cost = (cost_r / window_count) if (cost_r is not None and window_count) else None
            reasons: list[str] = []
            if window_count < min_occurrences:
                reasons.append("below_occurrence_threshold")
            if fraction < min_coverage:
                reasons.append("insufficient_coverage")
            if cost_r is not None and cost_r < min_cost_r:
                reasons.append("below_cost_threshold")
            eligible = not reasons
            entry = {
                "signature": signature,
                "category": category,
                "severity": row["severity"],
                "count": total,
                "windowCount": window_count,
                "costR": cost_r,
                "meanCostR": round(mean_cost, 4) if mean_cost is not None else None,
                "rAvailable": bool(stats.get("rAvailable")),
                "coverage": round(fraction, 4),
                "firstSeen": stats.get("firstSeen"),
                "lastSeenAt": stats.get("lastSeenAt"),
                "eligibility": "eligible" if eligible else "not_yet",
                "reasons": reasons,
                "sampleFinding": row["sampleFinding"],
            }
            recurring.append(entry)
            if eligible and draft_candidates:
                candidate = self._draft_candidate(entry)
                if candidate:
                    created.append(candidate)

        recurring.sort(key=_priority, reverse=True)
        return {
            "recorded": recorded,
            "recurring": recurring,
            "candidates": created,
            "windowDays": window_days,
            "thresholds": {
                "minOccurrences": min_occurrences,
                "minCostR": min_cost_r,
                "minCoverage": min_coverage,
            },
            "counts": ledger,
        }

    def _draft_candidate(self, entry: dict[str, Any]) -> Optional[dict[str, Any]]:
        """Record an INERT RSL candidate. It enables nothing."""
        try:
            from ..code.evolution_store import EvolutionStore  # noqa: PLC0415

            evolution = EvolutionStore(self.run_store or self.store._store)  # noqa: SLF001
            if evolution.get_by_signature(entry["signature"]) is not None:
                return None
            return evolution.save_candidate({
                "signature": entry["signature"],
                "sourceCategory": f"trade_{entry['category']}",
                "observedCount": int(entry["windowCount"]),
                "problemStatement": (
                    f"Trade review saw {entry['category']} {entry['windowCount']} times "
                    f"in {entry['signature'][:8]}"
                )[:1_000],
                "targetPath": None,
                "status": "inert",
            })
        except Exception:  # noqa: BLE001 - a candidate is best-effort evidence
            return None

    # ── improve ──────────────────────────────────────────────────────────────

    def improve(
        self,
        trades: Any,
        *,
        findings: Optional[list[dict[str, Any]]] = None,
        playbook: Any = None,
        bounds: Optional[dict[str, Any]] = None,
        profile_id: str = "local",
        k: int = 3,
        generations: int = 2,
        split_pct: float = 0.7,
        min_validation_trades: int = 10,
        min_lift_r: float = 0.02,
        seed: int = 7,
        equity: float = 0.0,
        apply: str = "off",
    ) -> dict[str, Any]:
        parsed = parse_trades(trades)
        active = self.store.active_playbook(profile_id)
        if isinstance(playbook, dict):
            current = Playbook.from_dict(playbook)
        elif isinstance(playbook, Playbook):
            current = playbook
        elif active is not None:
            current = active
        else:
            current = Playbook(limits={}, bounds=dict(bounds or {}))
        if not current.bounds and bounds:
            current = Playbook(limits=current.limits, bounds=dict(bounds), version=current.version)
        if not current.bounds:
            return {
                "accepted": False,
                "reason": "no_bounds",
                "candidates": [],
                "best": current.to_dict(),
                "baseline": {"fit": None, "holdout": None},
                "applied": None,
                "detail": "the operator must set a bounds envelope before the loop may change anything",
            }

        # Bounds are authority, limits are the model. Without an active version
        # the baseline is the declared/default limits; the climb tightens from
        # there inside the operator's bounds.
        current = Playbook(
            limits=dict(current.limits), bounds=current.bounds,
            version=current.version, playbook_id=current.playbook_id,
        )

        result = climb(
            parsed, current=current, findings=findings or [], k=k,
            generations=generations, split_pct=split_pct,
            min_validation_trades=min_validation_trades,
            min_lift_r=min_lift_r, seed=seed, equity=equity,
        )
        result["applied"] = None
        result["bounds"] = dict(current.bounds)

        if apply in ("apply", "confirm") and result.get("accepted"):
            best = result["best"]
            try:
                saved = self.store.save_playbook(
                    best["limits"], bounds=current.bounds, profile_id=profile_id,
                    reason=str(result.get("reason") or "holdout improvement"),
                    mode=apply,
                    evidence={
                        "signature": (findings or [{}])[0].get("signature") if findings else None,
                        "holdout": result.get("baseline", {}).get("holdout"),
                    },
                    actions=result.get("candidates"),
                    ttl_days=14,
                )
                result["applied"] = saved
            except PlaybookRefused as exc:
                result["applied"] = {"refused": exc.to_dict()}
                result["reason"] = "apply_refused"
        return result

    # ── read / rollback ──────────────────────────────────────────────────────

    def playbook(self, *, profile_id: str = "local", history: bool = False) -> dict[str, Any]:
        active = self.store.active_playbook(profile_id)
        payload: dict[str, Any] = {
            "playbook": active.to_dict() if active else None,
            "provenance": {"source": "agent-memory", "profileId": profile_id},
        }
        if history:
            payload["versions"] = self.store.playbook_history(profile_id)
        return payload

    def revert(self, *, profile_id: str = "local", reason: str = "manual") -> dict[str, Any]:
        return self.store.revert(profile_id, reason=reason) or {
            "reverted": None, "active": None, "reason": "no_active_playbook",
        }

    def expire_due(self, *, profile_id: str = "local") -> Optional[dict[str, Any]]:
        return self.store.expire_due(profile_id)


__all__ = ["DEFAULT_MIN_COVERAGE", "DEFAULT_MIN_COST_R", "DEFAULT_MIN_OCCURRENCES",
           "DEFAULT_WINDOW_DAYS", "TradeLearningService"]
