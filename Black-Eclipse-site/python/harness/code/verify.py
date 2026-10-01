"""The per-run VerificationLedger: what was asserted passed vs. what is proven.

A check is passing ONLY when this module holds a record of an actual execution
whose exit code is zero. Nothing here trusts prose, a model summary, or a tool
description. Mirrors `research/claims.py`: a deterministic check owns the decision
and anything that cannot be checked is presented as UNVERIFIED, never as fact.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from .policy import COMMAND_CLASSES

# Bounded so a pathological run cannot turn the ledger into a log.
MAX_LEDGER_RECORDS = 200
MAX_CLAIM_SENTENCES = 500
MAX_OUTPUT_DIGEST_CHARS = 64

ClaimKind = Literal["tests_pass", "typecheck_clean", "build_ok", "lint_clean"]

# The classes that may satisfy each claim kind. A claim is supported when a
# zero-exit record exists whose class is IN this set.
CLAIM_CLASSES: dict[str, tuple[str, ...]] = {
    "tests_pass": ("unit_test", "python_test"),
    "typecheck_clean": ("typecheck",),
    "build_ok": ("build",),
    "lint_clean": ("lint",),
}

# Deterministic, sentence-level patterns. Deliberately narrow: a phrase that is
# not matched is not a check claim and is left alone. A negation ("the tests did
# not run", "I could not run the build") must NOT match — that is the honest case.
CLAIM_PATTERNS: tuple[tuple[ClaimKind, "re.Pattern[str]"], ...] = (
    ("tests_pass", re.compile(
        r"\b(all\s+|the\s+)?tests?\s+(pass(ed|es)?|are\s+(passing|green)|green|succeeded)\b"
        r"|\btest\s+suite\s+(passes|passed|is\s+green)\b", re.I)),
    ("typecheck_clean", re.compile(
        r"\btype[\s-]?check(ing)?\s+(passes|passed|is\s+clean|succeeds)\b"
        r"|\bno\s+type\s+errors?\b|\btsc\b[^.\n]{0,40}\b(clean|passes)\b", re.I)),
    ("build_ok", re.compile(
        r"\bbuild\s+(succeeds|succeeded|passes|passed|is\s+green)\b"
        r"|\bbuilds?\s+cleanly\b|\bcompiles?\s+(cleanly|without\s+errors)\b", re.I)),
    ("lint_clean", re.compile(
        r"\blint(ing)?\s+(is\s+)?(clean|passes|passed)\b"
        r"|\bno\s+lint\s+(errors|warnings)\b|\beslint\b[^.\n]{0,40}\b(clean|passes)\b", re.I)),
)

# A negation earlier in the sentence means the sentence is NOT a pass-claim. This
# is the honest case ("the tests did not run") and must never be flagged.
_NEGATION_RE = re.compile(
    r"\b(not|no|never|cannot|can't|could\s?n'?t|did\s?n'?t|do\s?n'?t|does\s?n'?t|"
    r"unable|failed\s+to|failed|skipped|without)\b", re.I)

# The marker appended to a claim that could not be backed. Loud on purpose and
# never hidden in a tooltip.
UNVERIFIED_MARKER = " [UNVERIFIED — no successful {class_list} execution in this run]"


def _normalize_output(text: str) -> str:
    """CRLF→LF, trailing whitespace per line stripped, trailing newlines collapsed."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    return "\n".join(lines).rstrip("\n")


def output_digest(output: str) -> str:
    """A stable digest of an execution's FULL normalized output.

    Normalization: CRLF→LF, trailing whitespace per line stripped, trailing
    newlines collapsed. Two identical runs share a digest; a different output
    (even by one line) does not. Hashed over the FULL text, never a truncated
    view — a clipped output must never be able to validate a claim.
    """
    normalized = _normalize_output(output)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:MAX_OUTPUT_DIGEST_CHARS]


class CheckClaim(BaseModel):
    """One sentence of the FINAL answer that asserts a check passed."""

    sentence: str
    kind: ClaimKind
    matchedClasses: list[str] = Field(default_factory=list)
    supported: bool = False
    evidenceExecutionId: Optional[str] = None  # noqa: N815
    evidenceDigest: Optional[str] = None  # noqa: N815
    evidenceExitCode: Optional[int] = None  # noqa: N815
    charStart: int = 0  # noqa: N815
    charEnd: int = 0  # noqa: N815


@dataclass(frozen=True)
class VerificationRecord:
    """The proof: one command execution, as the executor recorded it."""

    command_execution_id: str      # HarnessCommandExecution.id (Phase 3)
    command_class: str             # must be in policy.COMMAND_CLASSES
    exit_code: int
    duration_ms: int
    output_digest: str
    argv: tuple[str, ...] = ()
    started_at: str = ""           # ISO-8601
    workspace_id: Optional[str] = None

    @property
    def passed(self) -> bool:
        return self.exit_code == 0

    @classmethod
    def from_entry(cls, entry: dict[str, Any]) -> "VerificationRecord":
        """Rebuild from a serialized blob entry; raises on a malformed row so the
        caller can DROP it rather than guess."""
        if not isinstance(entry, dict):
            raise ValueError("record entry must be an object")
        command_class = str(entry.get("commandClass") or "")
        if command_class not in COMMAND_CLASSES:
            raise ValueError(f"unknown command class {command_class!r}")
        exit_code = entry.get("exitCode")
        if exit_code is None or not isinstance(exit_code, int):
            raise ValueError("record entry needs an integer exitCode")
        argv = entry.get("argv") or []
        if not isinstance(argv, list):
            raise ValueError("record entry argv must be a list")
        return cls(
            command_execution_id=str(entry.get("commandExecutionId") or ""),
            command_class=command_class,
            exit_code=int(exit_code),
            duration_ms=int(entry.get("durationMs") or 0),
            output_digest=str(entry.get("outputDigest") or ""),
            argv=tuple(str(a) for a in argv),
            started_at=str(entry.get("startedAt") or ""),
            workspace_id=entry.get("workspaceId"),
        )

    def to_entry(self) -> dict[str, Any]:
        return {
            "commandExecutionId": self.command_execution_id,
            "commandClass": self.command_class,
            "exitCode": self.exit_code,
            "durationMs": self.duration_ms,
            "outputDigest": self.output_digest,
            "argv": list(self.argv),
            "startedAt": self.started_at,
            "workspaceId": self.workspace_id,
        }


class VerificationLedger:
    """Per-run ledger. Constructed by execute_run, consulted by the renderer.

    NOT a graph node and NOT a store — it is a bounded value object that a run
    fills as commands execute, then serializes to `HarnessRun.codeVerification`.
    """

    def __init__(self, run_id: str, *, max_records: int = MAX_LEDGER_RECORDS) -> None:
        self.run_id = run_id
        self._records: list[VerificationRecord] = []
        self._max_records = max(1, int(max_records))

    # ── recording ──────────────────────────────────────────────────────────
    @property
    def records(self) -> list[VerificationRecord]:
        return list(self._records)

    def record(
        self,
        *,
        command_execution_id: str,
        command_class: str,
        exit_code: int,
        duration_ms: int,
        output: str = "",
        argv: tuple[str, ...] = (),
        started_at: str = "",
        workspace_id: Optional[str] = None,
    ) -> VerificationRecord:
        """Record an execution. Refuses (raises ValueError) on an unknown class."""
        if command_class not in COMMAND_CLASSES:
            raise ValueError(f"unknown command class {command_class!r}")
        record = VerificationRecord(
            command_execution_id=command_execution_id,
            command_class=command_class,
            exit_code=int(exit_code),
            duration_ms=int(duration_ms),
            output_digest=output_digest(output),
            argv=tuple(argv),
            started_at=started_at,
            workspace_id=workspace_id,
        )
        self._records.append(record)
        # Drop the OLDEST past the bound so a runaway loop cannot grow the ledger.
        if len(self._records) > self._max_records:
            self._records = self._records[-self._max_records:]
        return record

    # ── the three questions ────────────────────────────────────────────────
    def claims(self, answer: str) -> list[CheckClaim]:
        """What the model ASSERTED passed. Deterministic; no model call."""
        claims: list[CheckClaim] = []
        for text, start, end in _sentence_spans(answer or "")[:MAX_CLAIM_SENTENCES]:
            kind = _matches_any(text)
            if kind is None:
                continue
            matched = list(CLAIM_CLASSES.get(kind, ()))
            claims.append(CheckClaim(
                sentence=text.strip(), kind=kind, matchedClasses=matched,
                charStart=start, charEnd=end,
            ))
        return claims

    def verified(self, command_class: Optional[str] = None) -> list[VerificationRecord]:
        return [r for r in self._records if r.passed and (command_class is None or r.command_class == command_class)]

    def failed(self, command_class: Optional[str] = None) -> list[VerificationRecord]:
        return [r for r in self._records if not r.passed and (command_class is None or r.command_class == command_class)]

    def unverified_claims(self, answer: str) -> list[CheckClaim]:
        """The DIFFERENCE: asserted-passed minus proven-passed.

        A claim is supported when a ZERO-EXIT record exists whose class is in
        `claim.matchedClasses`; the most recent such record becomes its evidence.
        When only FAILING records exist, the most recent failing record is named
        so the marker can say "the check ran and FAILED" rather than "no check ran".
        """
        unsupported: list[CheckClaim] = []
        for claim in self.claims(answer):
            matching = [r for r in self._records if r.command_class in claim.matchedClasses]
            passing = [r for r in matching if r.passed]
            if passing:
                claim.supported = True
                latest = passing[-1]
                claim.evidenceExecutionId = latest.command_execution_id
                claim.evidenceDigest = latest.output_digest
                claim.evidenceExitCode = latest.exit_code
                continue
            if matching:
                latest = matching[-1]
                claim.evidenceExecutionId = latest.command_execution_id
                claim.evidenceDigest = latest.output_digest
                claim.evidenceExitCode = latest.exit_code
            unsupported.append(claim)
        return unsupported

    # ── serialization (additive, bounded, old-row-safe) ────────────────────
    def to_blob(self) -> dict[str, Any]:
        """Bounded JSON for `HarnessRun.codeVerification`."""
        entries = [r.to_entry() for r in self._records]
        return {
            "recordCount": len(entries),
            "truncated": len(self._records) >= self._max_records,
            "records": entries,
        }

    @classmethod
    def from_blob(cls, run_id: str, blob: Optional[dict[str, Any]]) -> "VerificationLedger":
        """Rehydrate for a resumed run. A missing/garbled blob yields an EMPTY
        ledger — never a fabricated one, so a resumed run starts unverified."""
        ledger = cls(run_id)
        if not isinstance(blob, dict):
            return ledger
        entries = blob.get("records")
        if not isinstance(entries, list):
            return ledger
        for entry in entries:
            try:
                ledger._records.append(VerificationRecord.from_entry(entry))
            except (ValueError, TypeError):
                continue  # drop a malformed row, never guess
        if len(ledger._records) > ledger._max_records:
            ledger._records = ledger._records[-ledger._max_records:]
        return ledger


def _sentence_spans(text: str) -> list[tuple[str, int, int]]:
    """Sentence → (text, charStart, charEnd). Newlines and bullets each end a
    sentence, so a bulleted list is checked line-by-line, not as one blob."""
    spans: list[tuple[str, int, int]] = []
    for match in re.finditer(r"[^\n]+", text or ""):
        line = match.group(0)
        offset = match.start()
        # Split a line on sentence enders too (``.`` `!` `?` followed by space/EOL).
        cursor = 0
        for end in re.finditer(r"(?<=[.!?])\s+", line):
            segment = line[cursor:end.start()]
            if segment.strip():
                spans.append((segment, offset + cursor, offset + end.start()))
            cursor = end.start()
        tail = line[cursor:]
        if tail.strip():
            spans.append((tail, offset + cursor, offset + len(line)))
    return spans


def _matches_any(sentence: str) -> Optional[ClaimKind]:
    """The first CLAIM kind whose pattern matches, or None. Case-insensitive.

    A sentence containing an explicit negation before a match is NOT a claim —
    "the tests did not run" is the honest case, not an assertion of a pass.
    """
    if _NEGATION_RE.search(sentence):
        return None
    for kind, pattern in CLAIM_PATTERNS:
        if pattern.search(sentence):
            return kind
    return None


# ── Answer-path enforcement ─────────────────────────────────────────────────

EnforcementMode = Literal["mark", "strip"]


class AnswerEnforcement(BaseModel):
    answer: str
    enforced: bool = False
    marked: list[CheckClaim] = Field(default_factory=list)
    stripped: list[CheckClaim] = Field(default_factory=list)
    note: Optional[str] = None


def _class_list(claim: CheckClaim) -> str:
    return ", ".join(claim.matchedClasses)


def enforce_answer(
    answer: str,
    ledger: VerificationLedger,
    *,
    mode: EnforcementMode = "mark",
) -> AnswerEnforcement:
    """Make the answer consistent with the ledger. Deterministic, no model call.

    `mark` (default): keep the sentence and append UNVERIFIED_MARKER naming the
    command classes that could have supported it. `strip`: remove the sentence
    outright. Either way an unbacked pass-claim is never rendered as a fact.
    """
    unverified = ledger.unverified_claims(answer or "")
    if not unverified:
        return AnswerEnforcement(answer=answer, enforced=False)

    if mode == "strip":
        # Remove each unsupported sentence's span (right-to-left so offsets hold).
        spans = sorted(
            ((c.charStart, c.charEnd) for c in unverified), key=lambda s: s[0], reverse=True,
        )
        stripped_answer = answer
        for start, end in spans:
            stripped_answer = stripped_answer[:start] + stripped_answer[end:]
        # Tidy the whitespace the removal can leave behind.
        stripped_answer = re.sub(r"[ \t]{2,}", " ", stripped_answer)
        stripped_answer = re.sub(r"\n{3,}", "\n\n", stripped_answer).strip()
        return AnswerEnforcement(
            answer=stripped_answer, enforced=True, stripped=unverified,
            note="unbacked check claims were removed",
        )

    # mark: append the marker to each unsupported sentence, right-to-left.
    marked_answer = answer
    for claim in sorted(unverified, key=lambda c: c.charStart, reverse=True):
        marker = UNVERIFIED_MARKER.replace("{class_list}", _class_list(claim))
        # The marker goes INSIDE the sentence's end, before the trailing punct is
        # fine; appending at charEnd keeps the marker adjacent to the claim.
        end = claim.charEnd
        # If the span ended at a sentence terminator, insert before it.
        if end > 0 and marked_answer[end - 1 : end] in (".", "!", "?"):
            marked_answer = marked_answer[: end - 1] + marker + marked_answer[end - 1:]
        else:
            marked_answer = marked_answer[:end] + marker + marked_answer[end:]
    return AnswerEnforcement(
        answer=marked_answer, enforced=True, marked=unverified,
        note="unbacked check claims were marked UNVERIFIED",
    )


async def enforce_run_answer(
    answer: str,
    ledger: VerificationLedger,
    repair_outcome: Optional[dict[str, Any]] = None,
    *,
    emitter: Any = None,
) -> tuple[str, dict[str, Any]]:
    """Enforce the answer against the ledger and build the persisted blob.

    Returns `(final_answer, blob)`. Emits `code.verify.claims`,
    `code.verify.unverified` and the repair status event. Deterministic; no
    model call. A run that asserted nothing and ran nothing yields a blob with
    zero entries — never a fabricated proof.
    """
    enforcement = enforce_answer(answer, ledger)
    claims = ledger.claims(answer)
    unverified = enforcement.marked + enforcement.stripped

    async def _emit(event: str, data: dict[str, Any]) -> None:
        if emitter is None:
            return
        try:
            await emitter.emit(event, data)
        except Exception:  # noqa: BLE001 - an event must never break a run
            pass

    if claims:
        supported = sum(1 for c in claims if c.supported)
        await _emit("code.verify.claims", {
            "claimed": len(claims), "supported": supported,
            "unverified": len(unverified),
            "kinds": sorted({c.kind for c in claims}),
        })
    if unverified:
        await _emit("code.verify.unverified", {
            "count": len(unverified),
            "sentences": [c.sentence[:200] for c in unverified[:5]],
        })

    blob: dict[str, Any] = {
        "runId": ledger.run_id,
        "records": [r.to_entry() for r in ledger.records],
        "claims": [
            {
                "sentence": c.sentence, "kind": c.kind,
                "matchedClasses": c.matchedClasses, "supported": c.supported,
                "evidenceExecutionId": c.evidenceExecutionId,
                "evidenceDigest": c.evidenceDigest,
                "evidenceExitCode": c.evidenceExitCode,
            }
            for c in claims
        ],
        "unverifiedCount": len(unverified),
        "repair": repair_outcome,
        "truncated": len(ledger.records) >= MAX_LEDGER_RECORDS,
    }
    return enforcement.answer, blob


__all__ = [
    "AnswerEnforcement",
    "CLAIM_CLASSES",
    "CLAIM_PATTERNS",
    "CheckClaim",
    "EnforcementMode",
    "MAX_LEDGER_RECORDS",
    "UNVERIFIED_MARKER",
    "VerificationLedger",
    "VerificationRecord",
    "enforce_answer",
    "enforce_run_answer",
    "output_digest",
]
