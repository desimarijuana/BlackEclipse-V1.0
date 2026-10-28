"""Agent tools for the financial modeling engine."""

from __future__ import annotations

import copy
import json
from typing import Any

from ..artifacts.model import ArtifactCategory
from ..documents.authoring import FORMAT_MIME, slug_filename
from ..tools import ToolContext, ToolDefinition, ToolRegistry
from .contracts import ModelError
from .engine import build_model, build_summary
from .report_export import build_model_report
from .xlsx_export import build_workbook_bytes

_MODEL_MIME = {
    "xlsx": FORMAT_MIME["xlsx"],
    "docx": FORMAT_MIME["docx"],
    "pptx": FORMAT_MIME["pptx"],
    "pdf": "application/pdf",
}


def _service(ctx: ToolContext) -> Any:
    service = getattr(ctx, "artifact_service", None)
    if service is None:
        from ..artifacts.bootstrap import get_artifact_service  # noqa: PLC0415

        service = get_artifact_service()
    if service is None:
        raise ModelError("ARTIFACT_UNAVAILABLE", "the artifact service is not available")
    return service


def _owner(ctx: ToolContext) -> str:
    return str(getattr(ctx, "workspace_id", None) or "local")


def _err(exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, ModelError):
        return f"{exc.code}: {exc.message}", {"error": exc.code, "message": exc.message, "detail": exc.detail}
    return f"MODEL_ERROR: {exc}", {"error": "MODEL_ERROR", "message": str(exc)}


async def _hydrate_comps(spec: Any, ctx: ToolContext) -> Any:
    """Resolve `comps.peerSymbols` through the existing read bridge.

    Auto-retrieval is a convenience over the SAME bridge every market tool uses.
    A peer whose price or share count is unavailable is skipped with a note; it is
    never filled with a guessed number.
    """
    if not isinstance(spec, dict):
        return spec
    comps = spec.get("comps")
    if not isinstance(comps, dict) or comps.get("peers"):
        return spec
    symbols = comps.get("peerSymbols") or comps.get("peer_symbols")
    if not isinstance(symbols, list) or not symbols:
        return spec
    from ..finance_tools import _fetch  # noqa: PLC0415

    hydrated = copy.deepcopy(spec)
    peers: list[dict[str, Any]] = []
    notes: list[str] = []
    for symbol_value in symbols[:100]:
        symbol = str(symbol_value or "").strip().upper()
        if not symbol:
            continue
        snapshot = await _fetch(ctx, "market_snapshot", {"symbol": symbol})
        statements = await _fetch(ctx, "financial_statements", {"symbol": symbol})
        price_block = snapshot.get("price")
        price = price_block.get("price") if isinstance(price_block, dict) else price_block
        if snapshot.get("status") != "OK" or price is None:
            notes.append(f"{symbol}: no usable price; peer excluded")
            continue
        periods = statements.get("periods") if isinstance(statements.get("periods"), list) else []
        period = periods[0] if periods and isinstance(periods[0], dict) else {}
        if not period:
            notes.append(f"{symbol}: no financial statements; peer excluded")
            continue
        market_cap = price_block.get("marketCap") if isinstance(price_block, dict) else None
        shares = period.get("sharesOutstanding")
        if shares is None and market_cap and price:
            shares = float(market_cap) / float(price)
        if shares is None:
            notes.append(f"{symbol}: no share count; peer excluded")
            continue
        peers.append({
            "name": snapshot.get("name") or symbol,
            "price": float(price),
            "shares": float(shares),
            "debt": float(period.get("totalDebt") or 0.0),
            "cash": float(period.get("cash") or 0.0),
            "minority": 0.0,
            "preferred": 0.0,
            "revenue": period.get("revenue"),
            "ebitda": period.get("ebitda"),
            "ebit": period.get("operatingIncome"),
            "net_income": period.get("netIncome"),
            "eps": period.get("eps"),
            "period": period.get("endDate") or period.get("fiscalYear") or "",
            "source": statements.get("statementSource") or statements.get("provider") or "JDdS/providers",
            "currency": statements.get("currency") or snapshot.get("currency") or "",
        })
    hydrated["comps"] = {
        **comps,
        "peers": peers,
        "autoPeerNotes": notes,
        "peerSymbols": symbols,
    }
    return hydrated


async def _build(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    spec = args.get("spec")
    try:
        spec = await _hydrate_comps(spec, ctx)
        result = build_model(spec)
        try:
            ctx.log("financial_model.build", {
                "kind": result.kind,
                "company": result.company,
                "specHash": result.meta.get("specHash"),
                "checksPass": result.checks_pass(),
            })
        except Exception:  # noqa: BLE001 - telemetry must not break the build
            pass
        auto_notes = (spec.get("comps") or {}).get("autoPeerNotes") if isinstance(spec, dict) else None
        if auto_notes:
            result.warnings.extend(str(note) for note in auto_notes)
        formats = args.get("formats") or ["xlsx"]
        if not isinstance(formats, list) or not formats:
            raise ModelError("INPUT_INVALID", "formats must be a non-empty array")
        clean_formats = []
        for fmt in formats:
            key = str(fmt).strip().casefold()
            if key not in _MODEL_MIME:
                raise ModelError("MODEL_FORMAT_UNSUPPORTED", f"unsupported model format {fmt!r}")
            if key not in clean_formats:
                clean_formats.append(key)
        service = _service(ctx)
        base = str(args.get("filename") or "").strip()
        if base:
            base = base.rsplit(".", 1)[0] if "." in base else base
        else:
            base = f"{result.company}-{result.kind}"
        artifacts = []
        summary = build_summary(result)
        payloads = [
            (fmt, build_workbook_bytes(spec, result) if fmt == "xlsx" else build_model_report(fmt, spec, result))
            for fmt in clean_formats
        ]
        for fmt, payload in payloads:
            artifact = service.register_bytes(
                payload,
                name=f"{base}.{fmt}",
                owner_id=_owner(ctx),
                description=str(args.get("description") or f"{result.kind} financial model for {result.company}"),
                category=ArtifactCategory.FINANCIAL,
                mime_type=_MODEL_MIME[fmt],
                source_tool="financial_model_build",
                agent_id=str(getattr(ctx, "agent_id", None) or "eclipse-agent"),
                conversation_id=getattr(ctx, "conversation_id", None),
                run_id=getattr(ctx, "run_id", None),
                tags=list(args.get("tags") or ["financial-model", result.kind]),
                metadata={
                    "kind": result.kind,
                    "company": result.company,
                    "currency": result.currency,
                    "units": result.units,
                    "format": fmt,
                    "checksPass": result.checks_pass(),
                    "specHash": result.meta.get("specHash"),
                },
                idempotency_key=f"model:{result.meta.get('specHash')}:{fmt}",
            )
            artifacts.append(artifact)
        spec_artifact = service.register_bytes(
            json.dumps({"spec": spec, "summary": summary}, ensure_ascii=False, indent=2, default=str).encode("utf-8"),
            name=f"{result.company}-{result.kind}-spec.json",
            owner_id=_owner(ctx),
            description="Machine-readable model spec and result summary",
            category=ArtifactCategory.DATASET,
            mime_type="application/json",
            source_tool="financial_model_build",
            agent_id=str(getattr(ctx, "agent_id", None) or "eclipse-agent"),
            conversation_id=getattr(ctx, "conversation_id", None),
            run_id=getattr(ctx, "run_id", None),
            tags=["financial-model", "spec", result.kind],
            idempotency_key=f"model:{result.meta.get('specHash')}:spec",
        )
    except ModelError as exc:
        return _err(exc)
    except Exception as exc:  # noqa: BLE001 - a bad spec must not crash the run
        return _err(exc)

    failures = summary.get("failures") or []
    verdict = "all checks pass" if result.checks_pass() else f"{len(failures)} check(s) FAIL"
    return (
        f"Built the {result.kind.replace('_', ' ')} model for {result.company} ({verdict}). "
        f"Saved {len(artifacts)} deliverable(s): "
        + ", ".join(f"{artifact.name} ({artifact.id})" for artifact in artifacts)
        + f"; spec: {spec_artifact.id}.",
        {
            "status": "OK",
            "artifacts": [artifact.model_dump(by_alias=True) for artifact in artifacts],
            "artifact": artifacts[0].model_dump(by_alias=True) if artifacts else None,
            "specArtifact": spec_artifact.model_dump(by_alias=True),
            "summary": summary,
            "warnings": result.warnings,
        },
    )


async def _audit(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    try:
        result = build_model(args.get("spec"))
    except ModelError as exc:
        return _err(exc)
    except Exception as exc:  # noqa: BLE001
        return _err(exc)
    summary = build_summary(result)
    verdict = "PASS" if result.checks_pass() else "FAIL"
    return (
        f"Model audit {verdict}: {len(result.checks)} check(s), "
        f"{len(summary.get('failures') or [])} failure(s), {len(result.warnings)} warning(s).",
        {"status": "OK", "summary": summary, "checks": [check.to_dict() for check in result.checks]},
    )


def register_modeling_tools(registry: ToolRegistry) -> list[str]:
    added: list[str] = []
    if registry.get("financial_model_build") is None:
        registry.register(ToolDefinition(
            name="financial_model_build",
            description=(
                "Build a deterministic financial model and save its deliverables to the Artifact "
                "Center: a formula-bearing Excel workbook and/or a PDF/Word memo or PowerPoint deck. "
                "Kinds: three_statement, dcf, lbo, comps, integrated. "
                "Supply `history` (years + series, or facts with period/value/source), explicit "
                "`assumptions`, and — for LBO/comps — an `lbo` or `comps` block. For comps, "
                "`comps.peers` may be supplied explicitly or `comps.peerSymbols` may name tickers "
                "to resolve through the read-only market bridge (a peer with no usable price or "
                "share count is excluded with a note). Every required input is refused by name "
                "when missing; no financial value is defaulted. The workbook carries live formulas "
                "plus a Values sheet and a Checks sheet."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "spec": {"type": "object", "description": "The validated ModelSpec."},
                    "formats": {"type": "array", "items": {"type": "string", "enum": ["xlsx", "pdf", "docx", "pptx"]}},
                    "filename": {"type": "string"},
                    "description": {"type": "string"},
                    "tags": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["spec"],
            },
            handler=_build,
            permission="read",
            risk="low",
            timeout_ms=120_000,
        ))
        added.append("financial_model_build")
    if registry.get("financial_model_audit") is None:
        registry.register(ToolDefinition(
            name="financial_model_audit",
            description=(
                "Recompute a financial model and return its checks, key metrics and warnings "
                "without writing a file. Use this before presenting model outputs."
            ),
            input_schema={
                "type": "object",
                "properties": {"spec": {"type": "object"}},
                "required": ["spec"],
            },
            handler=_audit,
            permission="read",
            risk="low",
            timeout_ms=120_000,
        ))
        added.append("financial_model_audit")
    return added


__all__ = ["register_modeling_tools"]
