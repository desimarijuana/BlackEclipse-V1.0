"""The evidence ledger: one place a claim and its handles are recorded (C4).

The handle vocabulary is already proven by delegation (`VerifiableHandle`) and
code verification (`VerificationLedger`). This module unifies their shapes:

    file         a workspace path + sha256
    run          a run id (the run's own trace is the evidence)
    tool_output  a run-scoped `ToolOutput` handle
    artifact     an Artifact Center id/path + digest
    citation     a URL or record id from research
    record       a durable row (task, ledger entry, decision, ...)
    computation  a deterministic calculation the run actually performed

A claim with at least one VALID handle is `supported`; a claim with none is
`unverified` (never silently "supported"). `unsupported` is reserved for a
verifier that actively rejects the claim.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Iterable, Optional

from .model import Claim, EvidenceHandle, Verdict
from .store import GoalStore


def digest_text(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8", errors="replace")).hexdigest()


def handle(
    kind: str, ref: str, *, source: str = "", digest: Optional[str] = None,
) -> dict[str, Any]:
    """Build one handle dict in the canonical wire shape."""
    return EvidenceHandle(kind=kind, ref=str(ref), source=source, digest=digest).to_dict()


def handles_from_tool_result(result: Any, run_id: str) -> list[dict[str, Any]]:
    """Every handle a tool result legitimately carries. Pure and bounded."""
    out: list[dict[str, Any]] = []
    if run_id:
        out.append(handle("run", run_id, source="tool_result"))
        # Every executed tool call is a durable row; that row IS the record a
        # claim can cite. It is stronger than the generic run handle.
        call_id = str(getattr(result, "tool_call_id", "") or "")
        name = str(getattr(result, "name", "") or "tool")
        out.append(handle(
            "record", f"tool:{run_id}:{call_id or name}", source=name,
            digest=digest_text(str(getattr(result, "text", "") or "")),
        ))
    output_id = getattr(result, "output_id", None)
    if output_id:
        out.append(handle("tool_output", str(output_id), source=getattr(result, "name", "")))
    data = getattr(result, "data", None)
    if isinstance(data, dict):
        path, sha = data.get("path"), data.get("sha256")
        if isinstance(path, str) and path:
            out.append(handle("file", path, source="tool_result", digest=sha if isinstance(sha, str) else None))
        artifact = data.get("artifactId") or data.get("artifact_id")
        if isinstance(artifact, str) and artifact:
            out.append(handle("artifact", artifact, source="tool_result"))
        url = data.get("url") or data.get("source_url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            out.append(handle("citation", url, source="tool_result"))
        record = data.get("recordId") or data.get("record_id")
        if isinstance(record, str) and record:
            out.append(handle("record", record, source="tool_result"))
    # Deduplicate by (kind, ref); preserve order.
    seen: set[tuple[str, str]] = set()
    unique = []
    for item in out:
        key = (item["kind"], item["ref"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_NUMBER = re.compile(r"\d")


def claim_sentences(text: str, *, limit: int = 40) -> list[str]:
    """Deterministic sentence extraction for answer enforcement.

    Every non-empty sentence is a candidate. The caller decides which classes
    must be checked; extraction never turns prose into an assertion.
    """
    out: list[str] = []
    for raw in _SENTENCE_SPLIT.split(str(text or "")):
        sentence = " ".join(raw.split()).strip()
        if len(sentence) < 12:
            continue
        out.append(sentence[:600])
        if len(out) >= limit:
            break
    return out


def has_number(sentence: str) -> bool:
    return bool(_NUMBER.search(sentence or ""))


class EvidenceLedger:
    """Record claims + handles; the store owns durability."""

    def __init__(self, store: Any) -> None:
        self._store = store if isinstance(store, GoalStore) else GoalStore(store)
        self._goal_store = self._store

    @property
    def store(self) -> GoalStore:
        return self._goal_store

    def record(
        self,
        *,
        run_id: str,
        text: str,
        handles: Optional[Iterable[dict[str, Any]]] = None,
        status: Optional[str] = None,
        verifier: str = "",
        step_id: Optional[str] = None,
    ) -> Claim:
        valid = [h for h in (handles or []) if EvidenceHandle.from_dict(h).valid]
        resolved = status or ("supported" if valid else "unverified")
        if resolved not in ("supported", "unsupported", "unverified"):
            resolved = "unverified"
        return self._goal_store.record_claim(
            run_id=run_id, text=text, handles=valid, status=resolved,
            verifier=verifier, step_id=step_id,
        )

    def record_sentences(
        self, *, run_id: str, text: str, handles: Optional[Iterable[dict[str, Any]]] = None,
        step_id: Optional[str] = None,
    ) -> list[Claim]:
        """Record each sentence as a claim carrying the same handles.

        This is the simple answer-seam policy: a sentence backed by a handle is
        supported; the rest are explicitly unverified, never silently trusted.
        """
        base = list(handles or [])
        return [
            self.record(
                run_id=run_id, text=sentence, handles=base, step_id=step_id,
            )
            for sentence in claim_sentences(text)
        ]

    def claims(self, run_id: str) -> list[Claim]:
        return self._goal_store.list_claims(run_id)

    def summary(self, run_id: str) -> dict[str, Any]:
        return self._goal_store.summary(run_id)

    def verdict(self, run_id: str, *, verifier: str = "evidence") -> Verdict:
        claims = self.claims(run_id)
        unsupported = [c for c in claims if c.status == "unsupported"]
        unverified = [c for c in claims if c.status == "unverified"]
        missing = tuple(c.text[:160] for c in (unsupported + unverified)[:8])
        if not claims:
            return Verdict(verifier=verifier, ok=False, reason="no claims recorded",
                           missing=("no evidence claims",))
        if unsupported:
            return Verdict(
                verifier=verifier, ok=False,
                reason=f"{len(unsupported)} claim(s) rejected by a verifier",
                missing=missing,
            )
        return Verdict(
            verifier=verifier, ok=not unverified,
            reason="" if not unverified else f"{len(unverified)} claim(s) unverified",
            missing=missing,
        )


def render_evidence_block(claims: list[Claim], *, limit: int = 12) -> str:
    """A bounded, inert block for the answer seam / outcome."""
    if not claims:
        return ""
    lines = ["<evidence-ledger>", "Claims recorded for this run (newest evidence first):"]
    for claim in claims[-limit:]:
        handle_text = ", ".join(f"{h.kind}:{h.ref}" for h in claim.handles[:3]) or "none"
        lines.append(f"- [{claim.status}] {claim.text[:240]} ({handle_text})")
    lines.append("</evidence-ledger>")
    return "\n".join(lines)


__all__ = [
    "EvidenceLedger",
    "claim_sentences",
    "digest_text",
    "handle",
    "handles_from_tool_result",
    "has_number",
    "render_evidence_block",
]
