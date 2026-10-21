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

ClaimKind = Literal[
    "tests_pass", "typecheck_clean", "build_ok", "lint_clean",
    "artifacts_verified", "change_reviewed",
]

# The classes that may satisfy each claim kind. A claim is supported when a
# zero-exit record exists whose class is IN this set. The two Phase-19 kinds are
# supported by ARTIFACT / REVIEW records instead (see `unverified_claims`).
CLAIM_CLASSES: dict[str, tuple[str, ...]] = {
    "tests_pass": ("unit_test", "python_test"),
    "typecheck_clean": ("typecheck",),
    "build_ok": ("build",),
    "lint_clean": ("lint",),
    "artifacts_verified": ("artifact_check",),
    "change_reviewed": ("change_review",),
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
    # Phase 19 — a claim about a PRODUCED artifact or a REVIEWED change. Narrow
    # like the four above: a sentence that is not one of these shapes is left
    # alone, and the shared negation guard keeps "I could not check…" honest.
    ("artifacts_verified", re.compile(
        r"\b(chart|figure|file|artifact)s?\s+(is|are)\s+(intact|verified)\b", re.I)),
    ("change_reviewed", re.compile(
        r"\bI\s+(reviewed|checked)\s+the\s+change\b", re.I)),
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


# ── Artifact verification (Phase 19, ADR-H191) ──────────────────────────────
#
# A produced artifact is an OBSERVATION, never a claim: the file is where the
# reference says, its digest matches, its size is sane, it opens, and (when the
# inputs were recorded) the series it carries matches them. A check that cannot
# run is a FAILED record with its reason — never an absence.

ArtifactCheck = Literal[
    "artifact_exists",       # the file is where the reference says
    "artifact_digest",       # sha256 on disk == the recorded sha256
    "artifact_size",         # above the floor, below the cap
    "artifact_readable",     # an image opens; csv/json parse
    "figure_inputs_match",   # the produced series matches the recorded inputs
]

# A byte floor/cap for a produced artifact. Zero bytes is never a real artifact.
MIN_ARTIFACT_BYTES = 1
MAX_ARTIFACT_BYTES = 64 * 1024 * 1024

_IMAGE_EXTENSIONS = ("png", "jpg", "jpeg", "gif", "webp", "svg")
_IMAGE_SIGNATURES: tuple[tuple[str, bytes], ...] = (
    ("png", b"\x89PNG\r\n\x1a\n"),
    ("jpg", b"\xff\xd8\xff"),
    ("jpeg", b"\xff\xd8\xff"),
    ("gif", b"GIF8"),
    ("webp", b"RIFF"),
)


@dataclass(frozen=True)
class ArtifactRecord:
    """One VERIFIED artifact fact. Never a claim, always an observation."""

    artifact_name: str
    kind: str
    check: str
    passed: bool
    detail: str                      # plain sentence; mechanism stays in the trace
    observed: dict[str, Any] = None  # type: ignore[assignment]

    def to_entry(self) -> dict[str, Any]:
        return {
            "artifactName": self.artifact_name,
            "kind": self.kind,
            "check": self.check,
            "passed": self.passed,
            "detail": self.detail,
            "observed": dict(self.observed or {}),
        }

    @classmethod
    def from_entry(cls, entry: dict[str, Any]) -> "ArtifactRecord":
        if not isinstance(entry, dict) or not entry.get("artifactName") or not entry.get("check"):
            raise ValueError("artifact record entry must name the artifact and the check")
        observed = entry.get("observed")
        return cls(
            artifact_name=str(entry["artifactName"]),
            kind=str(entry.get("kind") or ""),
            check=str(entry["check"]),
            passed=bool(entry.get("passed")),
            detail=str(entry.get("detail") or ""),
            observed=dict(observed) if isinstance(observed, dict) else {},
        )


def _artifact_path(reference: Any, output_dir: Any) -> Optional[Any]:
    from pathlib import Path  # noqa: PLC0415

    name = str(getattr(reference, "name", "") or "")
    if not name:
        return None
    candidate = Path(output_dir) / name if output_dir is not None else None
    if candidate is not None and candidate.exists():
        return candidate
    recorded = str(getattr(reference, "path", "") or "")
    if recorded:
        path = Path(recorded)
        if path.exists():
            return path
    return candidate


def _sha256_of(path: Any) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _readable(path: Any, media_type: str, name: str) -> tuple[bool, str, dict[str, Any]]:
    """Whether the artifact opens as what it says it is. (passed, reason, observed)."""
    import json  # noqa: PLC0415

    suffix = name.rsplit(".", 1)[-1].lower() if "." in name else ""
    with open(path, "rb") as handle:
        head = handle.read(64)
    if suffix in _IMAGE_EXTENSIONS or str(media_type).startswith("image/"):
        for ext, signature in _IMAGE_SIGNATURES:
            if head.startswith(signature):
                return True, f"opens as an image ({ext})", {"signature": ext}
        if suffix == "svg" and b"<svg" in head:
            return True, "opens as an image (svg)", {"signature": "svg"}
        return False, "it does not open as an image", {"head": head[:16].hex()}
    if suffix == "csv" or str(media_type).startswith("text/csv"):
        import csv  # noqa: PLC0415

        try:
            with open(path, encoding="utf-8", newline="") as handle:
                rows = sum(1 for _ in csv.reader(handle))
        except Exception as exc:  # noqa: BLE001 - unreadable is a failed check
            return False, f"it does not parse as a table ({type(exc).__name__})", {}
        if rows < 2:
            return False, "the table has no data rows", {"rows": rows}
        return True, f"parses as a table ({rows - 1} data rows)", {"rows": rows - 1}
    if suffix == "json" or "json" in str(media_type):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            return False, f"it does not parse as JSON ({type(exc).__name__})", {}
        return True, "parses as JSON", {}
    # Any other kind: readable means non-empty text.
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001
        return False, f"it could not be read ({type(exc).__name__})", {}
    return bool(text.strip()), ("it has readable text" if text.strip() else "it is empty"), {}


def verify_artifacts(
    references: Any,
    output_dir: Any,
    recorded_inputs: Optional[dict[str, Any]] = None,
) -> list[ArtifactRecord]:
    """Run the artifact checks against the REAL files; return one record per check.

    A check that cannot run (a missing file) is a FAILED record with its reason,
    never an omission. `recorded_inputs` maps an artifact name to what the
    producing computation used; when it names a row count, the artifact's own
    series must match it. Pass None when the producer did not record inputs —
    the figure check is then recorded as failed for image artifacts.
    """
    records: list[ArtifactRecord] = []
    for reference in references or []:
        name = str(getattr(reference, "name", "") or "")
        if not name:
            continue
        media_type = str(getattr(reference, "media_type", "application/octet-stream"))
        kind = media_type.split("/", 1)[0]
        path = _artifact_path(reference, output_dir)

        exists = path is not None and path.exists()
        records.append(ArtifactRecord(
            artifact_name=name, kind=kind, check="artifact_exists", passed=bool(exists),
            detail=("it is where it was reported" if exists else "it is not where it was reported"),
            observed={"path": str(path) if path is not None else ""},
        ))
        if not exists:
            # A missing file fails every remaining check with its reason.
            for check, detail in (
                ("artifact_digest", "the file is missing, so its digest could not be checked"),
                ("artifact_size", "the file is missing, so its size could not be checked"),
                ("artifact_readable", "the file is missing, so it could not be opened"),
            ):
                records.append(ArtifactRecord(
                    artifact_name=name, kind=kind, check=check, passed=False, detail=detail,
                    observed={},
                ))
            continue

        size = path.stat().st_size
        records.append(ArtifactRecord(
            artifact_name=name, kind=kind, check="artifact_size",
            passed=MIN_ARTIFACT_BYTES <= size <= MAX_ARTIFACT_BYTES,
            detail=(
                f"it is {size:,} bytes"
                if MIN_ARTIFACT_BYTES <= size <= MAX_ARTIFACT_BYTES
                else ("it is empty" if size == 0 else "it is larger than any sane artifact")
            ),
            observed={"bytes": size},
        ))

        recorded = str(getattr(reference, "sha256", "") or "")
        if recorded:
            actual = _sha256_of(path)
            match = actual == recorded
            records.append(ArtifactRecord(
                artifact_name=name, kind=kind, check="artifact_digest", passed=match,
                detail=("its digest matches the record" if match
                        else "its digest does not match the record"),
                observed={"sha256": actual},
            ))

        passed, why, seen = _readable(path, media_type, name)
        records.append(ArtifactRecord(
            artifact_name=name, kind=kind, check="artifact_readable", passed=passed,
            detail=why, observed=seen,
        ))

        # The figure/inputs check runs only when the producer recorded inputs.
        if recorded_inputs is not None:
            entry = recorded_inputs.get(name)
            if not isinstance(entry, dict):
                if kind == "image":
                    records.append(ArtifactRecord(
                        artifact_name=name, kind=kind, check="figure_inputs_match", passed=False,
                        detail="its inputs were not recorded, so the series could not be checked",
                        observed={},
                    ))
            else:
                expected = entry.get("rows")
                actual_rows = seen.get("rows")
                if isinstance(expected, int) and isinstance(actual_rows, int):
                    ok = expected == actual_rows
                    records.append(ArtifactRecord(
                        artifact_name=name, kind=kind, check="figure_inputs_match", passed=ok,
                        detail=(f"it carries the {expected:,} record(s) it was produced from" if ok
                                else f"it carries {actual_rows:,} record(s), not the recorded {expected:,}"),
                        observed={"expectedRows": expected, "rows": actual_rows},
                    ))
    return records


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
        self._artifacts: list[ArtifactRecord] = []
        self._reviews: list[dict[str, Any]] = []
        self._max_records = max(1, int(max_records))

    # ── recording ──────────────────────────────────────────────────────────
    @property
    def records(self) -> list[VerificationRecord]:
        return list(self._records)

    @property
    def artifacts(self) -> list[ArtifactRecord]:
        return list(self._artifacts)

    @property
    def reviews(self) -> list[dict[str, Any]]:
        return list(self._reviews)

    def record_artifact(self, record: ArtifactRecord) -> ArtifactRecord:
        """Record one artifact observation (bounded like the command records)."""
        self._artifacts.append(record)
        if len(self._artifacts) > self._max_records:
            self._artifacts = self._artifacts[-self._max_records:]
        return record

    def record_review(self, entry: dict[str, Any]) -> dict[str, Any]:
        """Record that a change review RAN (the findings ride in the entry)."""
        self._reviews.append(dict(entry))
        if len(self._reviews) > 16:
            self._reviews = self._reviews[-16:]
        return entry

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
            # Phase 19: artifact and review claims are backed by ARTIFACT and
            # REVIEW records, not by command executions.
            if claim.kind == "artifacts_verified":
                if self._artifacts and all(r.passed for r in self._artifacts):
                    claim.supported = True
                else:
                    unsupported.append(claim)
                continue
            if claim.kind == "change_reviewed":
                if self._reviews:
                    claim.supported = True
                else:
                    unsupported.append(claim)
                continue
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
            # Phase 19 (additive, old-row-safe): artifact observations and the
            # review records. Absent for pre-Phase-19 blobs.
            "artifacts": [r.to_entry() for r in self._artifacts],
            "reviews": list(self._reviews),
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
        for entry in blob.get("artifacts") or []:
            try:
                ledger._artifacts.append(ArtifactRecord.from_entry(entry))
            except (ValueError, TypeError):
                continue
        for entry in blob.get("reviews") or []:
            if isinstance(entry, dict) and entry.get("ran"):
                ledger._reviews.append(dict(entry))
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
    # Round 3 / W1 (ADR-H281): a repair that EXHAUSTED its budget is disclosed
    # in the answer, not only in the blob. The ledger already refuses to
    # support a "tests pass" claim when the only record is a failure; this
    # covers the case the ledger cannot see - the loop ran out of budget, so
    # the last state of the code is simply unknown. A result must show what it
    # hides.
    answer = enforcement.answer
    if isinstance(repair_outcome, dict) and repair_outcome.get("status") == "REPAIR_EXHAUSTED":
        failed = repair_outcome.get("failedClass") or "the pinned check"
        answer = (
            f"{answer}\n\n[Note: the {failed} check was still failing when Eclipse ran out of "
            f"repair attempts, so the result above is not verified by a passing check.]"
        ).strip()
    return answer, blob


__all__ = [
    "AnswerEnforcement",
    "ArtifactCheck",
    "ArtifactRecord",
    "CLAIM_CLASSES",
    "CLAIM_PATTERNS",
    "CheckClaim",
    "EnforcementMode",
    "MAX_ARTIFACT_BYTES",
    "MAX_LEDGER_RECORDS",
    "MIN_ARTIFACT_BYTES",
    "UNVERIFIED_MARKER",
    "VerificationLedger",
    "VerificationRecord",
    "enforce_answer",
    "enforce_run_answer",
    "output_digest",
    "verify_artifacts",
]
