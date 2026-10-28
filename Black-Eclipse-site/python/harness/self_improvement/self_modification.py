"""Class-authorized self-modification (the safe Tier B).

The loop may **accept** a contract-clean, evaluated candidate and may **enable**
a read-only learned skill. It never enables an effectful skill, never widens a
tool surface, and never edits this policy.

Policy is read from the environment (operator-owned). Every action is recorded
in `SelfModificationAction` with an expiry and a revocation handle. A read-only
skill enabled here is time-boxed and auto-disabled when it expires.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Any, Mapping, Optional

from ..persistence import now_iso
from ..skills.draft import propose_draft
from ..skills.evaluation import evaluate_skill

log = logging.getLogger("harness.self_modification")

MODES = ("off", "accept", "enable")
ALLOWED_SKILL_PERMISSIONS = frozenset({"data.read", "analysis.execute", "analysis.read"})
MAX_CANDIDATES = 50
MAX_SKILLS_PER_TICK = 10


def _env_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def _env_int(value: Any, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class SelfModificationPolicy:
    mode: str = "enable"
    ttl_days: int = 7
    max_active_skills: int = 3
    max_actions_per_day: int = 10

    @classmethod
    def from_env(cls, environ: Optional[Mapping[str, str]] = None) -> "SelfModificationPolicy":
        env = os.environ if environ is None else environ
        mode = str(env.get("HARNESS_SELF_MODIFICATION", "enable")).strip().lower()
        if mode not in MODES:
            mode = "off"
        return cls(
            mode=mode,
            ttl_days=_env_int(env.get("HARNESS_SELF_MODIFICATION_TTL_DAYS"), 7, 1, 90),
            max_active_skills=_env_int(
                env.get("HARNESS_SELF_MODIFICATION_MAX_SKILLS"), 3, 0, 50,
            ),
            max_actions_per_day=_env_int(
                env.get("HARNESS_SELF_MODIFICATION_MAX_ACTIONS"), 10, 0, 100,
            ),
        )

    @property
    def enabled(self) -> bool:
        return self.mode != "off"

    @property
    def auto_accept(self) -> bool:
        return self.mode in ("accept", "enable")

    @property
    def auto_enable(self) -> bool:
        return self.mode == "enable"


class SelfModificationAudit:
    """Durable audit + expiry rows on the one agent-memory connection."""

    _SCHEMA = """
    CREATE TABLE IF NOT EXISTS SelfModificationAction (
      id        TEXT PRIMARY KEY,
      kind      TEXT NOT NULL,
      subject   TEXT NOT NULL,
      evidence  TEXT,
      status    TEXT NOT NULL,
      createdAt TEXT NOT NULL,
      expiresAt TEXT,
      revokedAt TEXT,
      detail    TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_selfmod_status ON SelfModificationAction(status, createdAt);
    """

    def __init__(self, store: Any) -> None:
        self._store = store
        self._db.executescript(self._SCHEMA)
        self._db.commit()

    @property
    def _db(self):
        return self._store._db

    def record(
        self,
        *,
        kind: str,
        subject: str,
        evidence: str = "",
        expires_at: Optional[str] = None,
        detail: Optional[dict[str, Any]] = None,
    ) -> str:
        action_id = "selfmod_" + uuid.uuid4().hex[:16]
        self._db.execute(
            "INSERT INTO SelfModificationAction "
            "(id, kind, subject, evidence, status, createdAt, expiresAt, revokedAt, detail) "
            "VALUES (?, ?, ?, ?, 'active', ?, ?, NULL, ?)",
            (
                action_id, kind, subject, evidence, now_iso(), expires_at,
                json.dumps(detail or {}),
            ),
        )
        self._db.commit()
        return action_id

    def count_today(self, kind: str) -> int:
        day = _dt.datetime.now(_dt.timezone.utc).date().isoformat()
        row = self._db.execute(
            "SELECT COUNT(*) AS c FROM SelfModificationAction "
            "WHERE kind=? AND createdAt >= ?",
            (kind, f"{day}T00:00:00"),
        ).fetchone()
        return int(row["c"]) if row else 0

    def active(self, kind: Optional[str] = None) -> list[dict[str, Any]]:
        if kind:
            rows = self._db.execute(
                "SELECT * FROM SelfModificationAction WHERE status='active' AND kind=?",
                (kind,),
            ).fetchall()
        else:
            rows = self._db.execute(
                "SELECT * FROM SelfModificationAction WHERE status='active'",
            ).fetchall()
        return [dict(row) for row in rows]

    def expire_due(self, now: str) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM SelfModificationAction "
            "WHERE status='active' AND expiresAt IS NOT NULL AND expiresAt <= ?",
            (now,),
        ).fetchall()
        due = [dict(row) for row in rows]
        for row in due:
            self._db.execute(
                "UPDATE SelfModificationAction SET status='expired', revokedAt=? WHERE id=?",
                (now, row["id"]),
            )
        self._db.commit()
        return due

    def revoke(self, action_id: str) -> Optional[dict[str, Any]]:
        row = self._db.execute(
            "SELECT * FROM SelfModificationAction WHERE id=?", (action_id,),
        ).fetchone()
        if row is None or row["status"] != "active":
            return None
        self._db.execute(
            "UPDATE SelfModificationAction SET status='revoked', revokedAt=? WHERE id=?",
            (now_iso(), action_id),
        )
        self._db.commit()
        return dict(row)

    def list(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = self._db.execute(
            "SELECT * FROM SelfModificationAction ORDER BY createdAt DESC LIMIT ?",
            (max(1, min(int(limit), 500)),),
        ).fetchall()
        return [dict(row) for row in rows]


def _expiry(days: int) -> str:
    moment = _dt.datetime.now(_dt.timezone.utc) + _dt.timedelta(days=max(1, int(days)))
    return moment.isoformat().replace("+00:00", "Z")


def _tool_names(candidate: Mapping[str, Any]) -> list[str]:
    return [
        str(ref["name"]) for ref in (candidate.get("evidenceReferences") or [])
        if isinstance(ref, dict) and ref.get("kind") == "tool" and ref.get("name")
    ]


def _skill_version(store: Any, skill_id: str) -> str:
    record = store.get_skill(skill_id) or {}
    return str(record.get("latestVersion") or "")


class SelfModificationExecutor:
    """One bounded task that executes the operator-authored class policy."""

    def __init__(
        self,
        service: Any,
        policy: Optional[SelfModificationPolicy] = None,
    ) -> None:
        self.service = service
        self.policy = policy or SelfModificationPolicy.from_env()
        self.store = service.skill_registry.store
        self.registry = service.skill_registry
        self.audit = SelfModificationAudit(service.store)
        self._task: Optional[asyncio.Task[Any]] = None
        self._paused = False
        self._last_result: dict[str, Any] = {}
        self._last_error: Optional[str] = None
        self._last_run_at: Optional[str] = None
        self._skips: list[dict[str, Any]] = []

    def _skip(self, kind: str, subject: str, reason: str) -> None:
        self._skips.append({"kind": kind, "subject": subject, "reason": reason})

    def _disable(self, skill_id: str, reason: str) -> None:
        version = _skill_version(self.store, skill_id)
        if not version:
            return
        self.store.set_version_status(skill_id, version, "disabled")
        self.store.append_event(
            "skill.auto_disabled", skill_id=skill_id, version=version,
            data={"reason": reason},
        )

    def _accept_candidate(self, candidate: dict[str, Any]) -> Optional[dict[str, Any]]:
        from .lesson_contract import candidate_problems  # noqa: PLC0415

        if candidate_problems(candidate):
            return None
        candidate_id = str(candidate.get("id") or "")
        if not candidate.get("resultingSkillId"):
            result = propose_draft(
                candidate_id, self.store,
                available_tools=_tool_names(candidate),
            )
            if not result.get("ok"):
                return None
            candidate = self.store.get_candidate(candidate_id) or candidate
        skill_id = str(candidate.get("resultingSkillId") or "")
        if not skill_id or self.registry.load_stored(skill_id) is None:
            return None
        version = str(candidate.get("resultingSkillVersion") or "") or _skill_version(
            self.store, skill_id,
        )
        evaluation = evaluate_skill(skill_id, version, self.registry)
        if evaluation.get("status") != "passed":
            return None
        self.store.update_candidate(candidate_id, status="accepted", reviewedAt=now_iso())
        self.store.append_event(
            "skill.candidate_auto_accepted", skill_id=skill_id, version=version,
            data={"candidateId": candidate_id, "evaluationId": evaluation.get("evaluationId")},
        )
        self.audit.record(
            kind="accept_candidate", subject=candidate_id,
            evidence=str(evaluation.get("evaluationId") or ""),
            detail={"skillId": skill_id, "version": version},
        )
        return {"candidateId": candidate_id, "skillId": skill_id, "version": version}

    def _enable_skill(self, skill_row: dict[str, Any]) -> Optional[dict[str, Any]]:
        skill_id = str(skill_row.get("id") or "")
        if not skill_id.startswith("learned."):
            self._skip("enable_skill", skill_id, "not_learned")
            return None
        loaded = self.registry.load_stored(skill_id)
        if loaded is None:
            self._skip("enable_skill", skill_id, "manifest_unreadable")
            return None
        manifest = loaded.manifest
        if any(p not in ALLOWED_SKILL_PERMISSIONS for p in manifest.permissions):
            self._skip("enable_skill", skill_id, "permission_not_read_only")
            return None
        tools_ok, detail = self.registry.check_tools(skill_id, manifest.version)
        if not tools_ok:
            self._skip("enable_skill", skill_id, f"tools_unavailable: {detail}")
            return None
        evaluations = self.store.list_evaluations(skill_id, limit=1)
        if not evaluations or evaluations[0].get("status") != "passed":
            self._skip("enable_skill", skill_id, "evaluation_not_passed")
            return None
        version = str(skill_row.get("latestVersion") or manifest.version)
        self.store.set_version_status(skill_id, version, "enabled", "passed")
        self.store.append_event(
            "skill.auto_enabled", skill_id=skill_id, version=version,
            data={"mode": self.policy.mode, "ttlDays": self.policy.ttl_days},
        )
        action_id = self.audit.record(
            kind="enable_skill", subject=skill_id,
            evidence=str(evaluations[0].get("id") or ""),
            expires_at=_expiry(self.policy.ttl_days),
            detail={"version": version},
        )
        return {
            "skillId": skill_id, "version": version, "actionId": action_id,
            "expiresAt": _expiry(self.policy.ttl_days),
        }

    def run_once(self) -> dict[str, Any]:
        if not self.policy.enabled or self._paused:
            return {"mode": self.policy.mode, "paused": self._paused, "accepted": [], "enabled": []}
        now = now_iso()
        self._last_run_at = now
        self._skips = []
        expired: list[dict[str, Any]] = []
        for row in self.audit.expire_due(now):
            self._disable(str(row.get("subject") or ""), "self-modification TTL expired")
            expired.append(row)
        accepted: list[dict[str, Any]] = []
        if self.policy.auto_accept and self.audit.count_today("accept_candidate") < self.policy.max_actions_per_day:
            for status in ("detected", "drafted"):
                for candidate in self.store.list_candidates(status=status, limit=MAX_CANDIDATES):
                    if self.audit.count_today("accept_candidate") >= self.policy.max_actions_per_day:
                        break
                    result = self._accept_candidate(candidate)
                    if result:
                        accepted.append(result)
        enabled: list[dict[str, Any]] = []
        if self.policy.auto_enable and self.policy.max_active_skills > 0:
            active = [
                row for row in self.store.list_skills(status="enabled")
                if str(row.get("id") or "").startswith("learned.")
            ]
            remaining = max(0, self.policy.max_active_skills - len(active))
            learned_drafts = [
                skill for skill in self.store.list_skills(status="draft")
                if str(skill.get("id") or "").startswith("learned.")
            ]
            for skill in learned_drafts[:MAX_SKILLS_PER_TICK]:
                if remaining <= 0:
                    break
                if self.audit.count_today("enable_skill") >= self.policy.max_actions_per_day:
                    break
                result = self._enable_skill(skill)
                if result:
                    enabled.append(result)
                    remaining -= 1
        self._last_result = {
            "accepted": accepted, "enabled": enabled,
            "expired": [row.get("id") for row in expired],
            "skipped": list(self._skips),
        }
        return dict(self._last_result)

    async def run_now(self) -> dict[str, Any]:
        if self._paused:
            return {"paused": True, "accepted": [], "enabled": []}
        try:
            return await asyncio.to_thread(self.run_once)
        except Exception as exc:  # noqa: BLE001 - the executor must survive
            self._last_error = f"{type(exc).__name__}: {exc}"
            return {"error": self._last_error, "accepted": [], "enabled": []}

    async def start(self) -> None:
        if not self.policy.enabled or self._task is not None:
            return
        self._task = asyncio.create_task(self._loop(), name="self-modification")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass

    async def _loop(self) -> None:
        while True:
            await self.run_now()
            await asyncio.sleep(300)

    def pause(self) -> dict[str, Any]:
        self._paused = True
        return self.status()

    def resume(self) -> dict[str, Any]:
        self._paused = False
        return self.status()

    def revoke(self, action_id: str) -> dict[str, Any]:
        row = self.audit.revoke(action_id)
        if row is None:
            return {"ok": False, "reason": "not_found_or_not_active"}
        self._disable(str(row.get("subject") or ""), "self-modification revoked")
        return {"ok": True, "action": row}

    def status(self) -> dict[str, Any]:
        return {
            "mode": self.policy.mode,
            "enabled": self.policy.enabled,
            "paused": self._paused,
            "autoAccept": self.policy.auto_accept,
            "autoEnable": self.policy.auto_enable,
            "ttlDays": self.policy.ttl_days,
            "maxActiveSkills": self.policy.max_active_skills,
            "maxActionsPerDay": self.policy.max_actions_per_day,
            "running": bool(self._task is not None and not self._task.done()),
            "lastRunAt": self._last_run_at,
            "lastResult": dict(self._last_result),
            "lastError": self._last_error,
            "activeGrants": self.audit.active(),
        }


__all__ = [
    "ALLOWED_SKILL_PERMISSIONS",
    "MODES",
    "SelfModificationAudit",
    "SelfModificationExecutor",
    "SelfModificationPolicy",
]
