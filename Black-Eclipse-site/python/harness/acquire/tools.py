"""The `acquire` tool — bounded bulk collection through the read-only bridge.

`acquire` turns a request for VOLUME into ONE declared pull: a registry source, a
closed parameter set, a Python-enforced budget, a CSV file under the run's
artifact directory, and a manifest that states rows, completeness, licence and
attribution. It REFUSES when the operator's switch (`acquisition_enabled`,
default OFF) is off, when the source is unknown, when a parameter is outside the
source's closed set, or when no bridge is reachable — always with a stable code
and one plain sentence. It never opens its own transport and never writes a
partial file without saying so.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from ..jobs.delivery import artifact_dir_for
from ..persistence import now_iso
from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .adapters import collect
from .budget import AcquisitionBudget
from .registry import CLOSED_VALUE_SETS, MAX_SYMBOLS_PER_CALL, get_source, list_sources
from .writer import write_csv

TOOL_NAMES = ("acquire",)

_PURPOSE_MAX = 300

_SWITCH_OFF_TEXT = (
    "Eclipse isn't set up to collect datasets on its own right now. You can turn "
    "that on in Eclipse Memory → Policies."
)


def new_budget() -> AcquisitionBudget:
    """TEST SEAM: the per-call budget. Never model-controlled."""
    return AcquisitionBudget()


def _acquisition_enabled(ctx: ToolContext) -> bool:
    """The operator's master switch, read fail-closed (mirrors W2)."""
    memory = getattr(ctx, "memory_service", None)
    policy = getattr(memory, "policy", None) if memory is not None else None
    if policy is None:
        return False
    try:
        return bool(policy.get_all().get("acquisition_enabled", False))
    except Exception:  # noqa: BLE001 - a policy read failure is a refusal
        return False


def _obj(properties: dict[str, Any], required: Optional[list[str]] = None) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _refusal(code: str, text: str, **data: Any) -> tuple[str, dict[str, Any]]:
    return text, {"status": "refused", "code": code, **data}


def _validate(source: Any, symbols: list[str], params: dict[str, Any]) -> Optional[tuple[str, str]]:
    """A (code, plain sentence) refusal, or None when the request is in bounds."""
    unknown = sorted(key for key in params if key not in source.query_params)
    if unknown:
        return (
            "UNKNOWN_PARAM",
            f"I don't know what to do with {', '.join(unknown)} for {source.label}. "
            f"It accepts: {', '.join(source.query_params)}.",
        )
    for key, allowed in CLOSED_VALUE_SETS.items():
        if key in params and str(params[key]).lower() not in allowed:
            return (
                "INVALID_PARAM_VALUE",
                f"{params[key]!r} isn't a value I can collect {key} at. "
                f"Allowed: {', '.join(allowed)}.",
            )
    if source.accepts_symbols:
        if not symbols:
            return ("MISSING_SYMBOLS", f"{source.label} needs the instruments to collect (symbols).")
        if len(symbols) > MAX_SYMBOLS_PER_CALL:
            return (
                "TOO_MANY_SYMBOLS",
                f"I can collect at most {MAX_SYMBOLS_PER_CALL} instruments per pull; "
                f"this asked for {len(symbols)}.",
            )
    elif symbols:
        return ("UNEXPECTED_SYMBOLS", f"{source.label} doesn't take a list of instruments.")
    return None


async def _acquire(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    from ..code.policy import acquisition_grants  # noqa: PLC0415

    enabled = _acquisition_enabled(ctx)
    profile = "declared_sources" if enabled else "none"
    if "data.collect" not in acquisition_grants(profile):
        return _refusal("ACQUISITION_OFF", _SWITCH_OFF_TEXT)

    source_id = str(args.get("source") or "").strip()
    source = get_source(source_id)
    if source is None:
        names = ", ".join(s["id"] for s in list_sources())
        return _refusal(
            "UNKNOWN_SOURCE",
            f"There's no ready-made collection called {source_id!r}. The ones I have: {names}.",
            available=[s["id"] for s in list_sources()],
        )

    purpose = str(args.get("purpose") or "").strip()
    if not purpose:
        return _refusal("MISSING_PURPOSE", "Tell me what this collection is for — it goes in the record.")
    purpose = purpose[:_PURPOSE_MAX]

    params_raw = args.get("params") or {}
    if not isinstance(params_raw, dict):
        return _refusal("INVALID_PARAMS", "The collection options must be a set of named values.")
    params = {str(k): v for k, v in params_raw.items()}

    symbols_raw = args.get("symbols") or []
    symbols = [str(s).strip() for s in symbols_raw if str(s).strip()] if isinstance(symbols_raw, list) else []
    refusal = _validate(source, symbols, params)
    if refusal is not None:
        return _refusal(refusal[0], refusal[1])

    bridge = getattr(ctx, "data_bridge", None)
    if bridge is None:
        return _refusal(
            "BRIDGE_UNAVAILABLE",
            "The data connection isn't reachable from here, so I didn't collect anything.",
        )

    try:
        directory = artifact_dir_for(str(getattr(ctx, "run_id", "") or "run"))
    except Exception:  # noqa: BLE001 - no artifact destination is a refusal
        return _refusal("ARTIFACT_UNAVAILABLE", "There's nowhere to save the collection, so I didn't start one.")

    budget = new_budget()
    rows, problems = await collect(source, symbols=symbols, params=params, bridge=bridge, budget=budget)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    filename = f"{source.id}_{stamp}.csv"
    path = directory / filename
    written, complete, stopped = write_csv(path, source.columns, rows, budget)
    if not written and not stopped:
        stopped = problems[0] if problems else "no rows were returned"
    if problems:
        complete = False
        stopped = stopped or problems[0]

    window: dict[str, Any] = {}
    dates = sorted(str(r.get("date") or r.get("period") or "") for r in rows)
    dates = [d for d in dates if d]
    if dates:
        window = {"from": dates[0], "to": dates[-1]}

    manifest: dict[str, Any] = {
        "purpose": purpose,
        "collectedAt": now_iso(),
        "sources": [{
            "id": source.id,
            "label": source.label,
            "window": window,
            "rows": written,
            "file": filename if written else None,
            "complete": bool(complete and written > 0),
            "stoppedReason": stopped or None,
            "licence": source.licence,
            "attribution": source.attribution,
        }],
        "limits": budget.snapshot(),
    }
    (directory / f"{source.id}_{stamp}.manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8",
    )

    if manifest["sources"][0]["complete"]:
        text = f"Collected {written:,} row(s) of {source.label} into {filename}."
    elif written:
        text = (
            f"Collected {written:,} row(s) of {source.label} — a partial pull: "
            f"{stopped or 'some of it could not be collected'}."
        )
    else:
        text = f"I couldn't collect {source.label}: {stopped or 'no data was returned'}."
    status = "ok" if manifest["sources"][0]["complete"] else "partial"
    return text, {"status": status, "manifest": manifest, "file": filename if written else None, "problems": problems}


def register_acquire_tools(registry: ToolRegistry) -> list[str]:
    """Register the acquisition tool. Idempotent per name."""
    if registry.get("acquire") is not None:
        return []
    registry.register(ToolDefinition(
        name="acquire",
        description=(
            "Collect a DATASET (many rows) from one declared source: daily price "
            "history, an economic series, or company statements. Provide the source "
            "id, the purpose (for the record), the instrument symbols when the source "
            "takes them, and the source's own options. Writes a CSV plus a manifest; "
            "a pull stopped at a limit is marked partial. For ONE fact, use the "
            "retrieval tools instead — this is for volume."
        ),
        input_schema=_obj({
            "source": {"type": "string", "enum": [s["id"] for s in list_sources()]},
            "purpose": {"type": "string"},
            "symbols": {"type": "array", "items": {"type": "string"}},
            "params": {"type": "object"},
        }, ["source", "purpose", "params"]),
        handler=_acquire, permission="write", risk="low", timeout_ms=300_000,
        effect="write", long_running=True,
    ))
    return ["acquire"]


__all__ = ["TOOL_NAMES", "new_budget", "register_acquire_tools"]
