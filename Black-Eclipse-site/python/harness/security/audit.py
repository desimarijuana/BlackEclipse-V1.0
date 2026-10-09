"""Security audit + observability.

Every security-sensitive operation records an audit event: authorizations
requests/decisions, approvals, capability issue/revoke, secret access, network
blocks, floor triggers, policy changes. Records are persisted append-only with a
hash chain (see `store.py`) and mirrored to the Event System (`security.*`) and
the observability metrics registry.

Secrets never enter the audit trail: every payload is passed through the secret
redactor first.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import threading
from typing import Any, Optional

from .models import Decision, RiskLevel, now_ts

log = logging.getLogger("harness.security.audit")

# The metric names exposed to the observability platform.
METRICS = {
    "permission_requests": "security_permission_requests_total",
    "permission_denials": "security_permission_denials_total",
    "approval_requests": "security_approval_requests_total",
    "approval_denials": "security_approval_denials_total",
    "hard_blocks": "security_hard_blocks_total",
    "secret_access": "security_secret_access_total",
    "secret_redactions": "security_secret_redactions_total",
    "network_denials": "security_network_denials_total",
    "sandbox_events": "security_sandbox_events_total",
    "ssrf_blocks": "security_ssrf_blocks_total",
    "policy_changes": "security_policy_changes_total",
    "security_failures": "security_failures_total",
}


class AuditSink:
    """An append-only external mirror of the audit trail with an HMAC-signed head.

    Writes one JSON line per event to `path` and maintains `<path>.head` with the
    running count, the chain hash, and an HMAC of that head under a key. This is
    the tamper-evidence anchor the in-DB hash chain cannot provide: a copy that
    lives outside the runtime's writable database.
    """

    def __init__(self, path: str, key: Optional[str] = None) -> None:
        self.path = path
        self.head_path = path + ".head"
        self._key = (key or os.environ.get("BLACK_ECLIPSE_SECURITY_AUDIT_KEY") or "eclipse-audit").encode("utf-8")
        self._lock = threading.RLock()
        self._count, self._hash = self._load_head()

    def _load_head(self) -> tuple[int, str]:
        try:
            with open(self.head_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return int(data.get("count", 0)), str(data.get("hash", ""))
        except Exception:  # noqa: BLE001 - no head yet (or unreadable) starts a fresh chain
            return 0, ""

    def _sign(self, count: int, chain_hash: str) -> str:
        return hmac.new(self._key, f"{count}:{chain_hash}".encode("utf-8"), hashlib.sha256).hexdigest()

    def append(self, record: dict[str, Any]) -> None:
        with self._lock:
            try:
                line = json.dumps({k: record.get(k) for k in (
                    "id", "timestamp", "category", "type", "actor", "userId", "agentId",
                    "sessionId", "taskId", "tool", "action", "resource", "decision",
                    "risk", "policy", "approvalId", "capabilityId", "result", "error",
                )}, sort_keys=True, separators=(",", ":"), default=str)
            except (TypeError, ValueError):
                return
            try:
                os.makedirs(os.path.dirname(os.path.abspath(self.path)), exist_ok=True)
                with open(self.path, "a", encoding="utf-8") as handle:
                    handle.write(line + "\n")
                self._hash = hashlib.sha256((self._hash + "\x00" + line).encode("utf-8")).hexdigest()
                self._count += 1
                with open(self.head_path, "w", encoding="utf-8") as handle:
                    json.dump(
                        {"count": self._count, "hash": self._hash,
                         "sig": self._sign(self._count, self._hash)},
                        handle,
                    )
            except Exception:  # noqa: BLE001 - the sink must never break a decision
                log.warning("audit sink append failed", exc_info=True)

    def verify(self) -> dict[str, Any]:
        with self._lock:
            try:
                with open(self.path, "r", encoding="utf-8") as handle:
                    lines = [ln for ln in handle.read().splitlines() if ln.strip()]
            except Exception:  # noqa: BLE001
                return {"valid": True, "checked": 0, "sink": self.path, "reason": "no sink yet"}
            chain = ""
            for line in lines:
                chain = hashlib.sha256((chain + "\x00" + line).encode("utf-8")).hexdigest()
            count, head_hash = self._load_head()
            signature = ""
            try:
                with open(self.head_path, "r", encoding="utf-8") as handle:
                    signature = str(json.load(handle).get("sig", ""))
            except Exception:  # noqa: BLE001
                signature = ""
            signature_ok = head_hash == chain and hmac.compare_digest(
                self._sign(count, head_hash), signature
            )
            return {
                "valid": len(lines) == count and signature_ok,
                "checked": len(lines), "sink": self.path,
            }


class AuditLog:
    """Record security events to the durable store + event system + metrics.

    Every method is best-effort and never raises: an audit failure must not turn a
    DENY into an ALLOW, nor crash a run. The durable append is attempted first; if
    even that fails the failure is counted.
    """

    def __init__(
        self, store: Any = None, *, secrets: Any = None, events: Any = None,
        metrics: Any = None, sink: Optional[AuditSink] = None,
    ) -> None:
        self._store = store
        self._secrets = secrets
        self._events = events
        self._metrics = metrics
        self._sink = sink
        self._counter: dict[str, int] = {}

    # ── wiring ───────────────────────────────────────────────────────────────
    def attach_events(self, events: Any) -> None:
        self._events = events

    def attach_metrics(self, metrics: Any) -> None:
        self._metrics = metrics

    # ── record ───────────────────────────────────────────────────────────────
    def record(
        self,
        *,
        type: str,
        category: str = "authorization",
        actor: Optional[str] = None,
        user_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        session_id: Optional[str] = None,
        task_id: Optional[str] = None,
        tool: Optional[str] = None,
        action: Optional[str] = None,
        resource: Optional[str] = None,
        decision: Optional[str] = None,
        risk: Optional[str] = None,
        policy: Optional[str] = None,
        approval_id: Optional[str] = None,
        capability_id: Optional[str] = None,
        result: Optional[str] = None,
        error: Optional[str] = None,
        payload: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        safe_payload = self._redact(payload)
        event = {
            "id": f"secaudit_{int(now_ts()*1000)}_{abs(hash((type, action, resource, session_id))) % 10**8}",
            "timestamp": now_ts(),
            "category": category,
            "type": type,
            "actor": actor,
            "userId": user_id,
            "tenantId": tenant_id,
            "agentId": agent_id,
            "sessionId": session_id,
            "taskId": task_id,
            "tool": tool,
            "action": action,
            "resource": resource,
            "decision": decision,
            "risk": risk,
            "policy": policy,
            "approvalId": approval_id,
            "capabilityId": capability_id,
            "result": result,
            "error": self._redact_text(error) if error else None,
            "payload": safe_payload,
        }
        record: Optional[dict[str, Any]] = None
        try:
            if self._store is not None:
                record = self._store.append_audit(event)
        except Exception as exc:  # noqa: BLE001 - audit persistence must never raise
            log.warning("audit persist failed: %s", exc)
            self._bump(METRICS["security_failures"])
        if self._sink is not None:
            try:
                self._sink.append(record or event)
            except Exception:  # noqa: BLE001 - the sink must never break a decision
                self._bump(METRICS["security_failures"])
        self._publish(event)
        self._bump_for(event)
        return record

    def _publish(self, event: dict[str, Any]) -> None:
        if self._events is None:
            return
        try:
            payload = {
                "category": event.get("category"),
                "actor": event.get("actor"),
                "action": event.get("action"),
                "resource": event.get("resource"),
                "decision": event.get("decision"),
                "risk": event.get("risk"),
                "policy": event.get("policy"),
            }
            emit = getattr(self._events, "emit_nowait", None)
            if callable(emit):
                emit(event["type"], payload, source="security")
        except Exception:  # noqa: BLE001
            pass

    def _bump_for(self, event: dict[str, Any]) -> None:
        decision = event.get("decision")
        category = event.get("category")
        if decision == Decision.DENY.value:
            self._bump(METRICS["permission_denials"])
        if decision == Decision.APPROVAL_REQUIRED.value:
            self._bump(METRICS["approval_requests"])
        if category == "floor" and decision == Decision.DENY.value:
            self._bump(METRICS["hard_blocks"])
        if category == "network" and decision == Decision.DENY.value:
            self._bump(METRICS["network_denials"])
        if category == "secret":
            self._bump(METRICS["secret_access"])
            if event.get("result") == "denied":
                self._bump(METRICS["secret_redactions"])

    def _bump(self, metric: str) -> None:
        self._counter[metric] = self._counter.get(metric, 0) + 1
        if self._metrics is not None:
            try:
                self._metrics.inc_counter(metric, 1.0)
            except Exception:  # noqa: BLE001
                pass

    # ── redaction ────────────────────────────────────────────────────────────
    def _redact(self, value: Any) -> Any:
        if value is None or self._secrets is None:
            return value
        try:
            return self._secrets.redact(value)
        except Exception:  # noqa: BLE001 - redaction failure drops the payload
            return "[REDACTION_FAILED]"

    def _redact_text(self, text: str) -> str:
        if self._secrets is None:
            return text
        try:
            return self._secrets.registry.redact_text(text)
        except Exception:  # noqa: BLE001
            return "[REDACTED]"

    # ── query ────────────────────────────────────────────────────────────────
    def list(self, **kwargs: Any) -> list[dict[str, Any]]:
        if self._store is None:
            return []
        return self._store.list_audit(**kwargs)

    def summary(self) -> dict[str, Any]:
        counts = self._store.audit_counts() if self._store is not None else {"total": 0, "byDecision": {}, "byCategory": {}}
        chain = self._store.verify_chain() if self._store is not None else {"valid": True, "checked": 0}
        if self._sink is not None:
            chain = {**chain, "sink": self._sink.verify()}
        return {
            "counters": dict(self._counter),
            "audit": counts,
            "chain": chain,
        }

    def verify(self) -> dict[str, Any]:
        if self._store is None:
            return {"valid": True, "checked": 0}
        result = self._store.verify_chain()
        if self._sink is not None:
            sink = self._sink.verify()
            result = {**result, "sink": sink, "valid": result.get("valid", True) and sink.get("valid", True)}
        return result


__all__ = ["AuditLog", "METRICS"]
