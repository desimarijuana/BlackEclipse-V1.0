"""The Quant Method Specification — the contract between research and the engine.

A method is stored as data, never as prose. The specification carries the
mathematics (with source provenance), the required inputs, the parameters, the
assumptions, the outputs and the validation plan. The LLM may draft it; this
validator decides whether it is complete enough to persist or execute.

Every rule is deterministic and pure: no model call, no I/O.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional

METHOD_SCHEMA_VERSION = "1.0.0"

LIFECYCLE = (
    "proposed", "reviewed", "specified", "implemented",
    "reproduced", "evaluated", "validated", "failed",
)
REPRODUCTION_STATUS = ("none", "attempted", "reproduced", "partial", "failed", "inconclusive")
IMPLEMENTATION_STATUS = ("none", "specified", "implemented", "tested", "builtin")

_REQUIRED = (
    "methodId", "name", "family", "version", "objective", "inputs",
    "equations", "estimation", "outputs",
)
_SLUG = re.compile(r"[^a-z0-9_.-]+")


def slug(value: str) -> str:
    text = _SLUG.sub("_", str(value or "").strip().lower()).strip("_")
    return text or "method"


def content_hash(spec: dict[str, Any]) -> str:
    canonical = json.dumps(spec, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _issue(code: str, message: str, path: str = "") -> dict[str, str]:
    return {"code": code, "message": message, "path": path}


def validate_method_spec(
    spec: dict[str, Any], *, require_literature: bool = False,
) -> list[dict[str, str]]:
    """Return every structural/semantic issue. An empty list means valid."""
    issues: list[dict[str, str]] = []
    if not isinstance(spec, dict):
        return [_issue("BAD_SPEC", "the method specification must be an object")]

    for key in _REQUIRED:
        if spec.get(key) in (None, "", [], {}):
            issues.append(_issue("MISSING_FIELD", f"{key} is required", key))

    method_id = str(spec.get("methodId") or "")
    if method_id and not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,96}", method_id):
        issues.append(_issue(
            "BAD_METHOD_ID",
            "methodId must be lowercase letters/digits with dots, dashes or underscores",
            "methodId",
        ))

    version = str(spec.get("version") or "")
    if version and not re.fullmatch(r"\d+\.\d+\.\d+", version):
        issues.append(_issue("BAD_VERSION", "version must be semver, e.g. 1.0.0", "version"))

    for collection in ("objective", "inputs", "equations", "assumptions",
                       "outputs", "validation", "limitations"):
        value = spec.get(collection)
        if value is not None and not isinstance(value, list):
            issues.append(_issue("BAD_SHAPE", f"{collection} must be a list", collection))
            continue
        if collection == "inputs":
            for i, item in enumerate(value or []):
                if not isinstance(item, dict) or not str(item.get("name") or "").strip():
                    issues.append(_issue(
                        "BAD_INPUT", "each input needs a name", f"inputs[{i}]",
                    ))
                if isinstance(item, dict) and not str(item.get("frequency") or "").strip():
                    issues.append(_issue(
                        "MISSING_INPUT_FREQUENCY",
                        "each input declares its sampling frequency",
                        f"inputs[{i}].frequency",
                    ))

    equations = spec.get("equations") or []
    if not equations:
        issues.append(_issue("NO_EQUATION", "at least one equation is required", "equations"))
    for i, eq in enumerate(equations if isinstance(equations, list) else []):
        if not isinstance(eq, dict) or not str(eq.get("latex") or "").strip():
            issues.append(_issue("BAD_EQUATION", "each equation needs latex", f"equations[{i}]"))
            continue
        source = eq.get("source") or {}
        if not isinstance(source, dict) or not (
            source.get("citation") or source.get("literatureId")
        ):
            issues.append(_issue(
                "EQUATION_WITHOUT_PROVENANCE",
                "each equation names its source (citation or literatureId)",
                f"equations[{i}].source",
            ))
        if require_literature and not source.get("literatureId"):
            issues.append(_issue(
                "EQUATION_WITHOUT_LITERATURE_ID",
                "an extracted equation must name the literatureId it came from",
                f"equations[{i}].source.literatureId",
            ))

    estimation = spec.get("estimation")
    if estimation is not None:
        if not isinstance(estimation, dict) or not str(estimation.get("method") or "").strip():
            issues.append(_issue(
                "MISSING_ESTIMATION", "estimation.method is required", "estimation.method",
            ))

    for i, ref in enumerate(spec.get("references") or []):
        if isinstance(ref, str):
            continue
        if not isinstance(ref, dict) or not str(ref.get("citation") or "").strip():
            issues.append(_issue(
                "BAD_REFERENCE", "a reference needs a citation", f"references[{i}]",
            ))

    provenance = spec.get("provenance") or {}
    if not isinstance(provenance, dict):
        issues.append(_issue("BAD_PROVENANCE", "provenance must be an object", "provenance"))
    elif require_literature and not provenance.get("literatureIds"):
        issues.append(_issue(
            "NO_LITERATURE",
            "a research method must link at least one literature record",
            "provenance.literatureIds",
        ))

    lifecycle = spec.get("lifecycleStatus")
    if lifecycle is not None and lifecycle not in LIFECYCLE:
        issues.append(_issue(
            "BAD_LIFECYCLE", f"lifecycleStatus must be one of {LIFECYCLE}", "lifecycleStatus",
        ))
    status = spec.get("reproductionStatus")
    if status is not None and status not in REPRODUCTION_STATUS:
        issues.append(_issue(
            "BAD_REPRODUCTION_STATUS",
            f"reproductionStatus must be one of {REPRODUCTION_STATUS}",
            "reproductionStatus",
        ))
    impl = spec.get("implementationStatus")
    if impl is not None and impl not in IMPLEMENTATION_STATUS:
        issues.append(_issue(
            "BAD_IMPLEMENTATION_STATUS",
            f"implementationStatus must be one of {IMPLEMENTATION_STATUS}",
            "implementationStatus",
        ))
    return issues


def normalize_spec(spec: dict[str, Any]) -> dict[str, Any]:
    """Fill defaults without inventing substantive content."""
    out = dict(spec or {})
    out.setdefault("schemaVersion", METHOD_SCHEMA_VERSION)
    out.setdefault("methodId", slug(out.get("name") or "method"))
    out.setdefault("name", out["methodId"])
    out.setdefault("family", "unspecified")
    out.setdefault("version", "1.0.0")
    for key in ("objective", "inputs", "parameters", "equations", "assumptions",
                "outputs", "validation", "limitations", "references", "unresolved"):
        value = out.get(key)
        out[key] = list(value) if isinstance(value, (list, tuple)) else ([] if value is None else [value])
    out.setdefault("estimation", {"method": "unspecified"})
    provenance = out.get("provenance")
    out["provenance"] = dict(provenance) if isinstance(provenance, dict) else {}
    out["provenance"].setdefault("literatureIds", [])
    out["provenance"].setdefault("implementationIds", [])
    out["provenance"].setdefault("confidence", "low")
    out.setdefault("implementationStatus", "none")
    out.setdefault("reproductionStatus", "none")
    out.setdefault("lifecycleStatus", "proposed")
    out.setdefault("complexity", 3)
    out.setdefault("evidenceLevel", 2)
    return out


def merge_structured(
    draft: dict[str, Any], structured: dict[str, Any],
) -> dict[str, Any]:
    """Merge a caller-supplied structured extraction into a draft.

    A caller must not be able to silently replace provenance with a guess: only
    known fields are merged, and equations without a source are kept in the draft
    so validation can reject them.
    """
    allowed = {
        "methodId", "name", "family", "version", "objective", "instruments",
        "frequencies", "inputs", "parameters", "equations", "estimation",
        "assumptions", "outputs", "validation", "limitations", "references",
    }
    out = dict(draft)
    for key, value in (structured or {}).items():
        if key in allowed and value not in (None, "", [], {}):
            out[key] = value
    return out


__all__ = [
    "IMPLEMENTATION_STATUS",
    "LIFECYCLE",
    "METHOD_SCHEMA_VERSION",
    "REPRODUCTION_STATUS",
    "content_hash",
    "merge_structured",
    "normalize_spec",
    "slug",
    "validate_method_spec",
]
