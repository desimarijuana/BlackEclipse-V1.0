"""A bounded archive of measured harness states.

The hill climb on its own is stuck: it can only ever propose from the current
champion, so a measured candidate that does not beat the champion is thrown
away. The archive keeps those measured states as `stepping_stone` rows and lets
the search sample from them later.

Boundaries that do not move:
- a stepping stone is never promotable, never activatable and never current;
- retention is not acceptance (only `utility.acceptance` decides acceptance);
- an unmeasured state is not retained (a missing number is not a foothold);
- the archive is bounded and evicts only stepping stones, least useful first.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Sequence

from . import sampler
from .cmp import CMPConfig, descendant_lift
from .state import HarnessStateStore

DEFAULT_MAX_STATES = 200


@dataclass(frozen=True)
class ArchiveConfig:
    max_states: int = DEFAULT_MAX_STATES
    sample: str = "weighted"
    temperature: float = 1.0
    novelty_min: float = 0.0
    # Metaproductivity (descendant lift) as a sampling signal. Off by default:
    # it is a ranking aid, never an acceptance rule.
    cmp: bool = False
    cmp_horizon: int = 3
    cmp_discount: float = 0.8
    cmp_min_samples: int = 2
    # Islands: a non-global scope's best measured state periodically migrates
    # into the global archive as a stepping stone. It never changes acceptance.
    islands: bool = False
    island_migration_every: int = 5

    def __post_init__(self) -> None:
        object.__setattr__(self, "max_states", max(2, min(1000, int(self.max_states))))
        mode = str(self.sample or "weighted").strip().lower()
        object.__setattr__(self, "sample", mode if mode in sampler.MODES else "weighted")
        object.__setattr__(
            self, "temperature", max(0.0, min(10.0, float(self.temperature)))
        )
        object.__setattr__(
            self, "novelty_min", max(0.0, min(1.0, float(self.novelty_min)))
        )
        object.__setattr__(self, "cmp", bool(self.cmp))
        object.__setattr__(self, "islands", bool(self.islands))
        object.__setattr__(
            self,
            "island_migration_every",
            max(0, min(100, int(self.island_migration_every))),
        )


def _measured(state: Mapping[str, Any]) -> bool:
    metrics = state.get("metrics")
    if isinstance(metrics, Mapping):
        value = metrics.get("measuredTrials", metrics.get("measured"))
        try:
            if value is not None and int(value) > 0:
                return True
        except (TypeError, ValueError):
            pass
        aggregates = metrics.get("aggregates")
        if isinstance(aggregates, Mapping) and aggregates.get("task_success") is not None:
            return True
    validation = state.get("validation")
    if isinstance(validation, Mapping):
        value = validation.get("measuredTrials", validation.get("measured"))
        try:
            if value is not None and int(value) > 0:
                return True
        except (TypeError, ValueError):
            pass
    return sampler.state_utility(state) is not None


class StateArchive:
    """Archive operations over the ONE `HarnessState` table."""

    def __init__(
        self,
        states: HarnessStateStore,
        config: Optional[ArchiveConfig] = None,
    ) -> None:
        self.states = states
        self.config = config or ArchiveConfig()
        self._cmp = CMPConfig(
            horizon=self.config.cmp_horizon,
            discount=self.config.cmp_discount,
            min_samples=self.config.cmp_min_samples,
        )
        self._island_counts: dict[str, int] = {}

    def size(self, *, scope: Optional[str] = None) -> int:
        return len(self.states.list_for_sampling(
            scope=scope, limit=self.config.max_states,
        ))

    def retain(
        self,
        state: Mapping[str, Any],
        *,
        status: str = "stepping_stone",
        island: Optional[str] = None,
    ) -> dict[str, Any]:
        """Keep one measured state as archive evidence (idempotent by digest).

        The snapshot digest IS the identity: retaining the same state twice
        returns the existing row rather than creating a duplicate.
        """
        payload = dict(state)
        digest = str(payload.get("snapshotDigest") or "").strip()
        if not digest:
            return {"retained": False, "reason": "no_snapshot_digest", "state": None}
        if not _measured(payload):
            return {"retained": False, "reason": "unmeasured", "state": None}
        scope = str(payload.get("scope") or "global").strip() or "global"
        existing = self.states.find_by_digest(digest, scope=scope)
        if existing is not None:
            self._refresh_cmp(str(existing.get("id") or ""))
            return {"retained": False, "reason": "duplicate", "state": existing}
        if status not in ("stepping_stone", "candidate"):
            status = "stepping_stone"
        metrics = payload.get("metrics") or payload.get("validation") or {}
        saved = self.states.save_state({
            "parentStateId": payload.get("parentStateId"),
            "scope": scope,
            "snapshotDigest": digest,
            "candidateId": payload.get("candidateId"),
            "acceptedRunId": payload.get("acceptedRunId"),
            "utility": payload.get("utility"),
            "metrics": metrics,
            "status": status,
            "island": island or payload.get("island") or scope,
            "novelty": payload.get("novelty"),
        })
        self._evict(scope)
        self._refresh_cmp(str(saved.get("id") or ""))
        migration = self._maybe_migrate(scope)
        return {
            "retained": True,
            "reason": "stored",
            "state": saved,
            "migration": migration,
        }

    def parent_for(
        self,
        *,
        scope: str = "global",
        rng: Optional[Any] = None,
        mode: Optional[str] = None,
        exclude_digests: Sequence[str] = (),
        island: Optional[str] = None,
    ) -> Optional[dict[str, Any]]:
        """Sample an exploration parent and count the visit.

        A missing scope falls back to `global`, mirroring how an active surface
        resolves. An empty archive returns None: the caller then proposes from
        the champion, exactly as before.
        """
        wanted = str(scope or "global")
        pool = self.states.list_for_sampling(
            scope=wanted, limit=self.config.max_states,
        )
        if not pool and wanted != "global":
            pool = self.states.list_for_sampling(
                scope="global", limit=self.config.max_states,
            )
        if island is not None:
            pool = [
                state for state in pool
                if str(state.get("island") or "") == str(island)
            ]
        if self.config.cmp:
            self._attach_cmp(pool)
        chosen = sampler.sample(
            pool,
            rng=rng,
            mode=mode or self.config.sample,
            temperature=self.config.temperature,
            exclude_digests=exclude_digests,
        )
        if chosen is None:
            return None
        state_id = str(chosen.get("id") or "")
        if state_id:
            try:
                chosen = self.states.record_visit(state_id)
            except ValueError:
                pass
        return chosen

    def children(self, state_id: str) -> list[dict[str, Any]]:
        return self.states.children(state_id)

    def _estimate(self, state: Mapping[str, Any]) -> dict[str, Any]:
        return descendant_lift(
            state, children=self.states.children, config=self._cmp,
        )

    def _attach_cmp(self, pool: list[dict[str, Any]]) -> None:
        """Attach a fresh estimate to pool rows that do not carry one.

        The write path persists `cmpScore`; this read-path fallback covers rows
        written before CMP was enabled. It is scoped to the sampled pool and
        never persists, so a read does not mutate the archive.
        """
        for item in pool:
            if item.get("cmpScore") is not None:
                continue
            estimate = self._estimate(item)
            if not estimate["coldStart"] and estimate["lift"] is not None:
                item["cmpScore"] = estimate["lift"]

    def _refresh_cmp(self, state_id: str) -> int:
        """Re-estimate the state and its ancestors after a new measured state."""
        if not self.config.cmp or not state_id:
            return 0
        updated = 0
        chain = self.states.lineage(state_id)[: self._cmp.horizon + 1]
        for row in chain:
            estimate = self._estimate(row)
            if estimate["coldStart"] or estimate["lift"] is None:
                continue
            try:
                self.states.set_scores(
                    str(row["id"]), cmp=float(estimate["lift"]),
                )
                updated += 1
            except ValueError:
                continue
        return updated

    def _maybe_migrate(self, scope: str) -> Optional[dict[str, Any]]:
        """Count non-global retains; migrate the island's best on the cadence."""
        if (
            not self.config.islands
            or self.config.island_migration_every <= 0
            or not scope
            or scope == "global"
        ):
            return None
        count = self._island_counts.get(scope, 0) + 1
        self._island_counts[scope] = count
        if count % self.config.island_migration_every != 0:
            return None
        return self.migrate_best(scope)

    def migrate_best(self, scope: str) -> dict[str, Any]:
        """Copy one island's best measured state into `global` as a stepping stone.

        The copy keeps the snapshot digest (the state's identity) but is a new
        row in the global scope, so the global sampler can find it. A digest
        already present in `global` is not copied twice, and a migrated copy is
        never migrated again.
        """
        source = str(scope or "")
        if not self.config.islands:
            return {"migrated": False, "reason": "islands_off"}
        if not source or source == "global":
            return {"migrated": False, "reason": "global_scope"}
        pool = self.states.list_for_sampling(
            scope=source, limit=self.config.max_states,
        )
        measured = [
            state for state in pool
            if sampler.state_utility(state) is not None
            and not str(state.get("island") or "").startswith("migrated:")
        ]
        if not measured:
            return {"migrated": False, "reason": "no_measured_state"}
        best = max(
            measured,
            key=lambda state: (
                float(sampler.state_utility(state) or 0.0),
                str(state.get("id") or ""),
            ),
        )
        digest = str(best.get("snapshotDigest") or "")
        if not digest:
            return {"migrated": False, "reason": "no_digest"}
        existing = self.states.find_by_digest(digest, scope="global")
        if existing is not None:
            return {"migrated": False, "reason": "already_present"}
        saved = self.states.save_state({
            "parentStateId": best.get("id"),
            "scope": "global",
            "snapshotDigest": digest,
            "candidateId": best.get("candidateId"),
            "acceptedRunId": best.get("acceptedRunId"),
            "utility": best.get("utility"),
            "metrics": best.get("metrics") or {},
            "status": "stepping_stone",
            "island": f"migrated:{source}",
        })
        return {
            "migrated": True,
            "fromScope": source,
            "stateId": saved.get("id"),
            "snapshotDigest": digest,
            "utility": saved.get("utility"),
        }

    def islands(self, *, scope: Optional[str] = None) -> dict[str, dict[str, Any]]:
        """A bounded per-island view: count and best measured utility."""
        pool = self.states.list_for_sampling(
            scope=scope, limit=self.config.max_states,
        )
        groups: dict[str, dict[str, Any]] = {}
        for state in pool:
            key = str(state.get("island") or state.get("scope") or "global")
            row = groups.setdefault(
                key, {"count": 0, "bestUtility": None, "bestStateId": None},
            )
            row["count"] += 1
            utility = sampler.state_utility(state)
            if utility is not None and (
                row["bestUtility"] is None or utility > row["bestUtility"]
            ):
                row["bestUtility"] = round(float(utility), 6)
                row["bestStateId"] = state.get("id")
        return groups

    def summary(self, *, scope: Optional[str] = None) -> dict[str, Any]:
        pool = self.states.list_for_sampling(
            scope=scope, limit=self.config.max_states,
        )
        by_status: dict[str, int] = {}
        for state in pool:
            key = str(state.get("status") or "unknown")
            by_status[key] = by_status.get(key, 0) + 1
        return {
            "enabled": True,
            "mode": self.config.sample,
            "maxStates": self.config.max_states,
            "size": len(pool),
            "byStatus": by_status,
            "cmp": {
                "enabled": self.config.cmp,
                "horizon": self._cmp.horizon,
                "discount": self._cmp.discount,
                "minSamples": self._cmp.min_samples,
            },
            "islands": {
                "enabled": self.config.islands,
                "migrationEvery": self.config.island_migration_every,
                "byIsland": self.islands(scope=scope),
            },
        }

    def _evict(self, scope: str) -> int:
        """Retire the least useful stepping stones when the cap is exceeded."""
        stones = self.states.list_states(
            scope=scope, status="stepping_stone",
            limit=self.config.max_states + 200,
        )
        excess = len(stones) - self.config.max_states
        if excess <= 0:
            return 0
        stones.sort(key=lambda row: (
            sampler.state_utility(row) is not None,
            float(sampler.state_utility(row) or 0.0),
        ))
        retired = 0
        for row in stones[:excess]:
            try:
                self.states.retire(str(row["id"]))
                retired += 1
            except ValueError:
                continue
        return retired


__all__ = [
    "ArchiveConfig",
    "DEFAULT_MAX_STATES",
    "StateArchive",
]
