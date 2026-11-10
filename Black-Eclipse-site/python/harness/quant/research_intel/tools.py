"""Agent-facing research and knowledge tools.

These tools orchestrate the research layer. They never compute a trading
statistic, never download a paper directly (they use the existing research
transport), and never promote a method to validated. Reading is open to the
agent; registration is a local metadata write and still requires evidence for a
validated lifecycle.
"""

from __future__ import annotations

from typing import Any

from ..errors import QuantError
from .catalog import get_catalog_method, list_catalog
from .dossier import build_dossier
from .extraction import extract_method
from .llm_extract import apply_proposal
from .implementation import run_implementation
from .repro import load_series, reproduce_method, validate_reproduction
from .schema import normalize_spec, validate_method_spec
from .scholarly import citation_graph, fetch_document, search_literature
from .store import ResearchStore
from .suitability import compare_methods
from .visuals import build_research_figures

RESEARCH_TOOLS: tuple[str, ...] = (
    "research_search_papers",
    "research_get_paper",
    "research_get_citations",
    "research_extract_method",
    "research_compare_methods",
    "research_get_evidence",
    "research_method_matrix",
    "research_visualize",
    "quant_list_methods",
    "quant_get_method",
    "quant_specify_method",
    "quant_reproduce_method",
    "quant_validate_method",
    "quant_attach_implementation",
    "quant_register_method",
    "quant_build_dossier",
    "quant_list_dossiers",
)


def _store(ctx: Any) -> ResearchStore:
    quant_store = getattr(ctx, "quant_store", None)
    if quant_store is None:
        raise QuantError("the quant store is not configured in this runtime")
    return ResearchStore(quant_store)


def _err(exc: Exception) -> tuple[str, Any]:
    if isinstance(exc, QuantError):
        return (f"ERROR — {exc.code}: {exc.message}",
                {"status": "ERROR", "error": exc.to_dict()})
    return (f"ERROR — {type(exc).__name__}: {exc}",
            {"status": "ERROR", "error": {"message": str(exc)}})


def _spec(method_id: str, store: ResearchStore) -> dict[str, Any]:
    try:
        return store.get_method_spec(method_id)["spec"]
    except QuantError:
        spec = get_catalog_method(method_id)
        if spec is None:
            raise QuantError(f"method {method_id!r} not found",
                             detail={"methodId": method_id})
        return spec


# ── external research ────────────────────────────────────────────────────────

async def research_search_papers_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        result = await search_literature(
            store,
            getattr(ctx, "data_bridge", None),
            objective=str(args.get("objective") or args.get("problem") or args.get("query") or ""),
            problem=str(args.get("problem") or ""),
            instrument=str(args.get("instrument") or ""),
            timeframe=str(args.get("timeframe") or ""),
            sources=list(args.get("sources") or []),
            limit=int(args.get("limit") or 8),
            max_queries=int(args.get("maxQueries") or 8),
            research_id=args.get("researchId"),
        )
        count = len(result["literature"])
        lines = [f"{count} literature record(s). Plan: {len(result['plan']['queries'])} queries."]
        for item in result["literature"][:12]:
            year = f" ({item['year']})" if item.get("year") else ""
            lines.append(f"- {item['id']} · {item['title']}{year}")
        if not count:
            lines.append(result["note"])
        return "\n".join(lines), result
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def research_get_paper_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        literature_id = str(args.get("literatureId") or "").strip()
        if not literature_id:
            raise QuantError("literatureId is required")
        record = store.get_literature(literature_id)
        url = str(args.get("url") or record.get("pdfUrl") or record.get("url") or "")
        text = args.get("text")
        document = None
        if text or url:
            document = await fetch_document(getattr(ctx, "data_bridge", None), url, text=text)
        text_out = f"{record['title']}"
        if record.get("year"):
            text_out += f" ({record['year']})"
        text_out += f"\nURL: {record.get('url') or 'not recorded'}"
        text_out += f"\nAccess: {record.get('accessStatus') or 'unknown'}"
        if document:
            text_out += f"\nDocument: {document.get('status')} ({len(document.get('text') or '')} chars)"
            if document.get("error"):
                text_out += f"\nDocument error: {document['error']}"
        return text_out, {"status": "OK", "literature": record, "document": document}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def research_get_citations_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        result = citation_graph(
            store, str(args["literatureId"]),
            direction=str(args.get("direction") or "both"),
            depth=int(args.get("depth") or 1),
        )
        return (f"{len(result['nodes'])} node(s), {len(result['edges'])} edge(s). "
                + result["note"]), result
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def research_extract_method_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        literature_id = str(args.get("literatureId") or "").strip()
        if not literature_id:
            raise QuantError("literatureId is required")
        literature = store.get_literature(literature_id)
        text = args.get("text")
        url = str(args.get("url") or literature.get("pdfUrl") or literature.get("url") or "")
        if not text:
            document = await fetch_document(getattr(ctx, "data_bridge", None), url)
            text = document.get("text") or ""
            if not text:
                return (
                    "Could not read the document. Provide `text` or an accessible URL. "
                    "The method was not extracted.",
                    {"status": "UNAVAILABLE", "literatureId": literature_id,
                     "error": document.get("error") or "no text",
                     "note": "An inaccessible paper is not a reason to invent its method."},
                )
        result = extract_method(
            literature_id=literature_id,
            text=str(text)[:400_000],
            title=literature.get("title") or "",
            method_hint=str(args.get("methodHint") or ""),
            structured=args.get("structured") if isinstance(args.get("structured"), dict) else None,
        )
        proposal = args.get("proposal") if isinstance(args.get("proposal"), dict) else None
        span_check = None
        if proposal:
            checked = apply_proposal(result["draft"], proposal, str(text)[:400_000])
            result["draft"] = checked["draft"]
            result["issues"] = validate_method_spec(
                checked["draft"], require_literature=True,
            )
            result["valid"] = not result["issues"]
            result["unresolved"] = checked["draft"].get("unresolved") or []
            result["confidence"] = (checked["draft"].get("provenance") or {}).get(
                "confidence", result["confidence"])
            span_check = {"verified": checked["verified"],
                          "rejected": checked["rejected"]}
            result["spanCheck"] = span_check
        draft = result["draft"]
        persisted = None
        if result["valid"] and bool(args.get("persist", True)):
            persisted = store.save_method_spec(
                {**draft, "lifecycleStatus": "specified"}, status="discovered",
            )
            store.link_paper(draft["methodId"], literature_id, role="origin")
        lines = [
            f"Extracted {result['equationCount']} equation(s) from {literature['title']}.",
            f"Method: {draft['methodId']} ({draft['family']}) · confidence {result['confidence']}",
        ]
        if result["valid"]:
            lines.append("The specification passes validation." + (
                " It is persisted." if persisted else " It was not persisted (persist=false)."
            ))
        else:
            lines.append("The specification is INCOMPLETE; it was not persisted:")
            lines.extend(f"- {issue['code']}: {issue['message']}" for issue in result["issues"][:10])
        if result["unresolved"]:
            lines.append("Unresolved: " + "; ".join(result["unresolved"][:8]))
        return "\n".join(lines), {**result, "persisted": persisted}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def research_compare_methods_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        ids = [str(x) for x in (args.get("methodIds") or []) if str(x).strip()]
        if not ids:
            query = str(args.get("objective") or args.get("query") or "")
            ids = [m["methodId"] for m in
                   (store.search_method_specs(query, limit=20) if query else store.list_method_specs(limit=20))]
            ids = ids[:10]
        specs = [_spec(i, store) for i in ids]
        constraints = dict(args.get("constraints") or {})
        for key in ("objective", "instrument", "timeframe", "availableData", "complexityMax"):
            if args.get(key) is not None and key not in constraints:
                constraints[key] = args.get(key)
        result = compare_methods(specs, constraints)
        lines = ["Method suitability (not a profit probability):"]
        for row in result:
            lines.append(f"- {row['name']}: {row['score']}/100")
            for factor in row["factors"]:
                if factor["points"]:
                    lines.append(f"    {factor['name']}: {factor['points']}/{factor['max']} — {factor['reason']}")
            for warning in row["warnings"]:
                lines.append(f"    ! {warning}")
        return "\n".join(lines), {"status": "OK", "comparison": result,
                                  "caveats": result[0]["caveats"] if result else []}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def research_get_evidence_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        method_id = str(args.get("methodId") or "").strip()
        literature_id = str(args.get("literatureId") or "").strip()
        if method_id:
            spec = _spec(method_id, store)
            papers = store.list_papers(method_id)
            literature = []
            for link in papers:
                try:
                    literature.append(store.get_literature(link["literatureId"]))
                except QuantError:
                    continue
            return (
                f"{spec.get('name')} — {len(literature)} linked paper(s), "
                f"{len(store.list_relationships(method_id))} relationship(s), "
                f"{len(store.list_reproductions(method_id))} reproduction(s).",
                {
                    "status": "OK",
                    "method": spec,
                    "papers": papers,
                    "literature": literature,
                    "relationships": store.list_relationships(method_id),
                    "reproductions": store.list_reproductions(method_id),
                    "implementations": store.list_implementations(method_id),
                },
            )
        if literature_id:
            literature = store.get_literature(literature_id)
            return (f"{literature['title']}", {"status": "OK", "literature": literature})
        raise QuantError("pass methodId or literatureId")
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def research_method_matrix_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        store.seed_catalog()
        methods = store.list_method_specs(limit=int(args.get("limit") or 500))
        family = str(args.get("family") or "").strip().lower()
        if family:
            methods = [m for m in methods
                       if str(m.get("methodFamily") or "").lower() == family]
        matrix: dict[str, list[dict[str, Any]]] = {
            h: [] for h in ("intraday", "swing", "position", "long-term")
        }
        other: list[dict[str, Any]] = []
        for record in methods:
            spec = record.get("spec") or {}
            row = {"methodId": record["id"], "name": record["name"],
                   "family": record["methodFamily"],
                   "implementation": spec.get("implementationStatus"),
                   "reproduction": spec.get("reproductionStatus")}
            horizons = [str(h).lower() for h in (spec.get("horizons") or [])]
            if not horizons:
                other.append(row)
                continue
            for horizon in horizons:
                if horizon in matrix:
                    matrix[horizon].append(row)
        total = len(methods)
        lines = [
            f"{total} method(s) across the open matrix. The 17+ seeds are a start, "
            "not a boundary: literature extraction and `quant_register_method` add methods.",
        ]
        for horizon, rows in matrix.items():
            lines.append(f"- {horizon}: {len(rows)} method(s)")
        if other:
            lines.append(f"- horizon not stated: {len(other)} method(s)")
        return "\n".join(lines), {
            "status": "OK",
            "matrix": matrix,
            "unstated": other,
            "total": total,
            "catalogOpen": True,
            "note": "A method can support more than one horizon. Empty cells are a "
                    "coverage gap, not an unavailable capability.",
        }
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def research_visualize_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        import json

        store = _store(ctx)
        store.seed_catalog()
        method_ids = [str(x) for x in (args.get("methodIds") or []) if str(x).strip()]
        methods = [_spec(mid, store) for mid in method_ids] if method_ids else []
        comparison = []
        objective = str(args.get("objective") or "").strip()
        if methods and objective:
            constraints = {
                "objective": objective,
                "instrument": args.get("instrument") or args.get("symbol"),
                "horizon": args.get("horizon"),
                "frequency": args.get("interval"),
                "availableData": args.get("availableData") or [],
            }
            comparison = compare_methods(methods, constraints)
        series = args.get("series")
        symbol = str(args.get("symbol") or "").strip()
        if series is None and symbol and bool(args.get("loadData", True)):
            series = await load_series(
                ctx, symbol=symbol, interval=str(args.get("interval") or "1d"),
                start=args.get("start"), end=args.get("end"),
            )
        reproduction = None
        reproduction_id = str(args.get("reproductionId") or "").strip()
        if reproduction_id:
            reproduction = store.get_reproduction(reproduction_id)
        result = build_research_figures(
            methods=methods or None,
            comparison=comparison or None,
            series=series,
            symbol=symbol,
            reproduction=reproduction,
        )
        if not result["blocks"]:
            reasons = "; ".join(f"{u['name']}: {u['reason']}"
                                for u in result["unavailable"])
            return (f"No research figure could be drawn. {reasons}",
                    {"status": "OK", **result})
        text = (
            f"{len(result['blocks'])} computed figure(s). Embed these `chart` blocks "
            "verbatim in the answer; do not retype the data:\n"
            + json.dumps(result["blocks"], separators=(",", ":"))
        )
        return text, {"status": "OK", **result}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── knowledge base ───────────────────────────────────────────────────────────

async def quant_list_methods_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        store.seed_catalog()
        query = str(args.get("query") or "").strip()
        if query:
            records = store.search_method_specs(query, limit=int(args.get("limit") or 50))
        else:
            records = store.list_method_specs(
                family=args.get("family"), lifecycle=args.get("lifecycle"),
                limit=int(args.get("limit") or 500),
            )
        horizon = str(args.get("horizon") or "").strip().lower()
        if horizon:
            records = [
                r for r in records
                if horizon in [str(h).lower() for h in
                               ((r.get("spec") or {}).get("horizons") or [])]
            ]
        rows = [{"methodId": r["id"], "name": r["name"],
                 "family": r["methodFamily"], "lifecycle": (r["spec"] or {}).get("lifecycleStatus"),
                 "implementation": (r["spec"] or {}).get("implementationStatus"),
                 "horizons": (r["spec"] or {}).get("horizons") or []}
                for r in records]
        lines = [f"{len(rows)} method(s). The catalog is a seed, not a limit:"]
        lines.extend(f"- {r['methodId']} · {r['name']} ({r['family']}; "
                     f"{', '.join(r['horizons']) or 'horizon not stated'})" for r in rows[:40])
        return "\n".join(lines), {"status": "OK", "methods": rows,
                                  "catalogOpen": True}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def quant_get_method_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        method_id = str(args.get("methodId") or "").strip()
        if not method_id:
            raise QuantError("methodId is required")
        record = store.get_method_spec(method_id)
        spec = record["spec"]
        return (
            f"{spec.get('name')} (`{method_id}`)\n"
            f"Family: {spec.get('family')}\n"
            f"Lifecycle: {spec.get('lifecycleStatus')}\n"
            f"Equations: {len(spec.get('equations') or [])}\n"
            f"Assumptions: {len(spec.get('assumptions') or [])}",
            {
                "status": "OK",
                "method": record,
                "relationships": store.list_relationships(method_id),
                "papers": store.list_papers(method_id),
                "reproductions": store.list_reproductions(method_id),
                "implementations": store.list_implementations(method_id),
            },
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def quant_specify_method_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        raw = args.get("spec") or args.get("draft") or {}
        if not isinstance(raw, dict):
            raise QuantError("spec must be an object")
        spec = normalize_spec(raw)
        issues = validate_method_spec(spec)
        if issues:
            return (
                "The method specification is incomplete; nothing was stored:\n"
                + "\n".join(f"- {i['code']}: {i['message']}" for i in issues[:15]),
                {"status": "INCOMPLETE", "issues": issues, "spec": spec},
            )
        if args.get("persist", True):
            spec["lifecycleStatus"] = spec.get("lifecycleStatus") or "specified"
            store.save_method_spec(spec, status="discovered")
            for lit in (spec.get("provenance") or {}).get("literatureIds") or []:
                store.link_paper(spec["methodId"], lit)
        return (f"Method {spec['methodId']} is valid.", {"status": "OK", "spec": spec})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── reproduction and validation ──────────────────────────────────────────────

async def quant_reproduce_method_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        method_id = str(args.get("methodId") or "").strip()
        if not method_id:
            raise QuantError("methodId is required")
        series = args.get("series")
        if series is None:
            symbol = str(args.get("symbol") or "").strip()
            if not symbol:
                raise QuantError("pass `series` or `symbol`")
            series = await load_series(
                ctx, symbol=symbol, interval=str(args.get("interval") or "1d"),
                start=args.get("start"), end=args.get("end"),
            )
        record = reproduce_method(
            store, method_id=method_id, series=series,
            published_benchmark=args.get("publishedBenchmark") if isinstance(args.get("publishedBenchmark"), dict) else None,
            params=args.get("params") if isinstance(args.get("params"), dict) else None,
            dataset_id=args.get("datasetId"), dataset_version=args.get("datasetVersion"),
            tolerance=float(args.get("tolerance") or 0.25),
        )
        return (
            f"{method_id}: {record['status']} (`{record['id']}`)\n"
            + (f"Observed: {record.get('observedMetrics')}" if record.get("observedMetrics") else
               "No metrics were produced."),
            {"status": "OK", "reproduction": record},
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def quant_validate_method_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        reproduction_id = str(args.get("reproductionId") or "").strip()
        if not reproduction_id:
            raise QuantError("reproductionId is required")
        result = validate_reproduction(store, reproduction_id)
        validation = result["validation"]
        return (
            f"Validation: {validation['status']}\n"
            + "\n".join(f"- {c['check']}: {c['status']} — {c['detail']}"
                        for c in validation["checks"]),
            {"status": "OK", **result},
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def quant_attach_implementation_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        method_id = str(args.get("methodId") or "").strip()
        source = str(args.get("source") or "").strip()
        if not method_id or not source:
            raise QuantError("methodId and source are required")
        spec = _spec(method_id, store)
        sample = args.get("series")
        if sample is None:
            sample = [{"ts": f"2024-01-{i + 1:02d}", "close": 100.0 + i * 0.1}
                      for i in range(30)]
        params = args.get("params") if isinstance(args.get("params"), dict) else {}
        result = run_implementation(source, sample, params)
        if result.get("status") != "OK":
            return (
                "The implementation failed its isolated test. Nothing was attached.\n"
                + str(result.get("error") or result.get("reason")),
                {"status": "FAILED", **result},
            )
        updated = dict(spec)
        updated["implementation"] = {
            "kind": "python", "source": source,
            "isolation": result.get("isolation") or "process",
            "testedWith": len(sample),
        }
        updated["implementationStatus"] = "tested"
        updated["lifecycleStatus"] = updated.get("lifecycleStatus") or "implemented"
        if updated["lifecycleStatus"] == "specified":
            updated["lifecycleStatus"] = "implemented"
        saved = store.save_method_spec(updated, status="discovered")
        implementation = store.save_implementation(
            method_id=method_id, version=updated.get("version") or "1.0.0",
            test_status="passing",
        )
        return (
            f"Implementation attached to {method_id}. Test status: passing. "
            f"Isolation: {result.get('isolation')}.",
            {"status": "OK", "method": saved, "implementation": implementation,
             "test": result},
        )
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def quant_register_method_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        raw = args.get("spec") or args.get("draft") or {}
        if not isinstance(raw, dict):
            raise QuantError("spec must be an object")
        spec = normalize_spec(raw)
        issues = validate_method_spec(spec)
        if issues:
            return (
                "The method specification is invalid; nothing was registered:\n"
                + "\n".join(f"- {i['code']}: {i['message']}" for i in issues[:15]),
                {"status": "INCOMPLETE", "issues": issues},
            )
        requested = str(args.get("lifecycleStatus") or "specified")
        if requested in ("validated", "evaluated"):
            reps = [str(x) for x in (args.get("reproductionIds") or [])]
            passing = []
            for rep_id in reps:
                try:
                    rep = store.get_reproduction(rep_id)
                except QuantError:
                    continue
                if (rep.get("validation") or {}).get("status") == "pass":
                    passing.append(rep_id)
            if not passing:
                raise QuantError(
                    "a validated lifecycle requires at least one reproduction whose "
                    "validation status is 'pass'",
                    detail={"reproductionIds": reps},
                )
            for rep_id in passing:
                store.save_validation(rep_id, store.get_reproduction(rep_id)["validation"])
        spec["lifecycleStatus"] = requested
        saved = store.save_method_spec(spec, status="discovered")
        for lit in (spec.get("provenance") or {}).get("literatureIds") or []:
            store.link_paper(spec["methodId"], lit)
        return (f"Registered {spec['methodId']} ({requested}).",
                {"status": "OK", "method": saved})
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── dossiers ─────────────────────────────────────────────────────────────────

async def quant_build_dossier_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        series = args.get("series") if isinstance(args.get("series"), list) else None
        symbol = str(args.get("symbol") or "").strip()
        if series is None and symbol:
            series = await load_series(
                ctx, symbol=symbol,
                interval=str(args.get("interval") or "1d"),
                start=args.get("start"), end=args.get("end"),
            )
        result = build_dossier(
            store,
            title=str(args.get("title") or "Quant research dossier"),
            question=str(args.get("question") or args.get("objective") or "Research question not stated"),
            artifact_service=getattr(ctx, "artifact_service", None),
            session_id=args.get("sessionId"),
            research_id=args.get("researchId"),
            method_ids=args.get("methodIds") or [],
            literature_ids=args.get("literatureIds") or [],
            reproduction_ids=args.get("reproductionIds") or [],
            constraints=args.get("constraints") if isinstance(args.get("constraints"), dict) else None,
            summary=str(args.get("summary") or ""),
            run_id=getattr(ctx, "run_id", None),
            series=series,
            symbol=symbol,
        )
        lines = [
            f"Dossier {result['dossierId']} — {result['status']}.",
            f"Artifact: {result['artifactId'] or 'not registered'}",
        ]
        if result["missing"]:
            lines.append("Missing: " + "; ".join(result["missing"]))
        blocks = (result.get("dossier") or {}).get("figures") or []
        if blocks:
            import json

            lines.append(
                f"{len(blocks)} computed figure(s). Embed these `chart` blocks "
                "verbatim; do not retype the data:\n"
                + json.dumps(blocks, separators=(",", ":"))
            )
        return "\n".join(lines), result
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


async def quant_list_dossiers_tool(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    try:
        store = _store(ctx)
        rows = store.list_dossiers(session_id=args.get("sessionId"),
                                   limit=int(args.get("limit") or 50))
        summary = [{"id": r["id"], "title": r["title"], "status": r["status"],
                    "artifactId": r["artifactId"], "createdAt": r["createdAt"]}
                   for r in rows]
        lines = [f"{len(summary)} dossier(s):"]
        lines.extend(f"- {r['id']} · {r['title']} ({r['status']})" for r in summary[:20])
        return "\n".join(lines), {"status": "OK", "dossiers": summary}
    except Exception as exc:  # noqa: BLE001
        return _err(exc)


# ── registration ─────────────────────────────────────────────────────────────

def register_research_tools(registry: Any) -> list[str]:
    from ...tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any],
             timeout: int = 30_000, long_running: bool = False) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema, handler=handler,
            permission="read", risk="low", timeout_ms=timeout,
            long_running=long_running,
        ))

    _def("research_search_papers",
         "Search academic literature through the existing scholarly connectors. "
         "Plans a topic query set, deduplicates DOI/arXiv results and stores pointers. "
         "A result is a pointer, never evidence.",
         research_search_papers_tool, {"type": "object", "properties": {
             "objective": {"type": "string"}, "problem": {"type": "string"},
             "query": {"type": "string"}, "instrument": {"type": "string"},
             "timeframe": {"type": "string"},
             "sources": {"type": "array", "items": {"type": "string"}},
             "limit": {"type": "integer"}, "maxQueries": {"type": "integer"},
             "researchId": {"type": "string"}}})
    _def("research_get_paper",
         "Read one literature record and, optionally, fetch its accessible text.",
         research_get_paper_tool, {"type": "object", "properties": {
             "literatureId": {"type": "string"}, "url": {"type": "string"},
             "text": {"type": "string"}}, "required": ["literatureId"]})
    _def("research_get_citations",
         "Return the citation neighbourhood recorded for a paper. Missing metadata "
         "is reported as absent, never invented.",
         research_get_citations_tool, {"type": "object", "properties": {
             "literatureId": {"type": "string"},
             "direction": {"type": "string", "enum": ["references", "citing", "both"]},
             "depth": {"type": "integer"}}, "required": ["literatureId"]})
    _def("research_extract_method",
         "Extract a formal method specification from a paper document, with section "
         "and page provenance for every equation. Missing fields are named, never guessed.",
         research_extract_method_tool, {"type": "object", "properties": {
             "literatureId": {"type": "string"}, "text": {"type": "string"},
             "url": {"type": "string"}, "methodHint": {"type": "string"},
             "structured": {"type": "object"}, "proposal": {"type": "object",
             "description": "Model proposal. Every field needs a verbatim quote "
                            "in `quotes`; an equation needs `source.quote`. A field "
                            "without a quote is rejected."},
             "persist": {"type": "boolean"}},
             "required": ["literatureId"]}, 120_000)
    _def("research_compare_methods",
         "Compare candidate methods against the stated objective, data, instrument "
         "and frequency. Deterministic and explained; never a profit probability.",
         research_compare_methods_tool, {"type": "object", "properties": {
             "methodIds": {"type": "array", "items": {"type": "string"}},
             "objective": {"type": "string"}, "query": {"type": "string"},
             "instrument": {"type": "string"}, "timeframe": {"type": "string"},
             "availableData": {"type": "array", "items": {"type": "string"}},
             "complexityMax": {"type": "integer"},
             "constraints": {"type": "object"}}})
    _def("research_get_evidence",
         "Return the evidence chain for a method or paper: links, relationships, "
         "reproductions and implementations.",
         research_get_evidence_tool, {"type": "object", "properties": {
             "methodId": {"type": "string"}, "literatureId": {"type": "string"}}})
    _def("research_method_matrix",
         "Show the open, horizon-wide method matrix: which methods exist for "
         "intraday, swing, position and long-term work. The seeded catalog is a "
         "start; registered and literature-derived methods extend it.",
         research_method_matrix_tool, {"type": "object", "properties": {
             "family": {"type": "string"}, "limit": {"type": "integer"}}})
    _def("research_visualize",
         "Build deterministic research figures from real inputs: method coverage, "
         "suitability, price and rolling volatility, return distribution, and "
         "reproduction fit. Returns chart blocks to embed verbatim.",
         research_visualize_tool, {"type": "object", "properties": {
             "methodIds": {"type": "array", "items": {"type": "string"}},
             "objective": {"type": "string"}, "instrument": {"type": "string"},
             "horizon": {"type": "string"}, "availableData": {"type": "array",
             "items": {"type": "string"}},
             "symbol": {"type": "string"}, "interval": {"type": "string"},
             "start": {"type": "string"}, "end": {"type": "string"},
             "series": {"type": "array", "items": {"type": "object"}},
             "reproductionId": {"type": "string"},
             "loadData": {"type": "boolean"}}}, 120_000)
    _def("quant_list_methods",
         "List the quantitative method knowledge base (seeded catalog + registered "
         "methods), filterable by family and lifecycle.",
         quant_list_methods_tool, {"type": "object", "properties": {
             "family": {"type": "string"}, "lifecycle": {"type": "string"},
             "query": {"type": "string"}, "horizon": {"type": "string"},
             "limit": {"type": "integer"}}})
    _def("quant_get_method",
         "Return one method specification with its relationships, papers, "
         "implementations and reproductions.",
         quant_get_method_tool, {"type": "object", "properties": {
             "methodId": {"type": "string"}}, "required": ["methodId"]})
    _def("quant_specify_method",
         "Validate and persist a formal method specification. An invalid "
         "specification is rejected, never stored.",
         quant_specify_method_tool, {"type": "object", "properties": {
             "spec": {"type": "object"}, "draft": {"type": "object"},
             "persist": {"type": "boolean"}}})
    _def("quant_reproduce_method",
         "Run a registered method on a dataset (or symbol) and record the observed "
         "estimates. Reproduction is separate from a trading adaptation.",
         quant_reproduce_method_tool, {"type": "object", "properties": {
             "methodId": {"type": "string"}, "series": {"type": "array",
             "items": {"type": "object"}}, "symbol": {"type": "string"},
             "interval": {"type": "string"}, "start": {"type": "string"},
             "end": {"type": "string"}, "publishedBenchmark": {"type": "object"},
             "params": {"type": "object"}, "datasetId": {"type": "string"},
             "datasetVersion": {"type": "string"}, "tolerance": {"type": "number"}},
             "required": ["methodId"]}, 120_000)
    _def("quant_validate_method",
         "Run the validation checks that are possible for a reproduction and record "
         "the result. A pass is not a profit claim.",
         quant_validate_method_tool, {"type": "object", "properties": {
             "reproductionId": {"type": "string"}}, "required": ["reproductionId"]})
    _def("quant_attach_implementation",
         "Attach a Python `run(rows, params)` implementation to a method. The code "
         "is tested in an isolated worker before it is saved. A failed test "
         "attaches nothing.",
         quant_attach_implementation_tool, {"type": "object", "properties": {
             "methodId": {"type": "string"}, "source": {"type": "string"},
             "series": {"type": "array", "items": {"type": "object"}},
             "params": {"type": "object"}}, "required": ["methodId", "source"]},
         120_000)
    _def("quant_register_method",
         "Register a validated method specification. A 'validated' lifecycle requires "
         "a reproduction whose validation passed.",
         quant_register_method_tool, {"type": "object", "properties": {
             "spec": {"type": "object"}, "draft": {"type": "object"},
             "lifecycleStatus": {"type": "string"},
             "reproductionIds": {"type": "array", "items": {"type": "string"}}}})
    _def("quant_build_dossier",
         "Build the durable Quant Research Dossier (literature, equations, "
         "comparison, reproduction, validation, limitations) and register it in the "
         "Artifact Center.",
         quant_build_dossier_tool, {"type": "object", "properties": {
             "title": {"type": "string"}, "question": {"type": "string"},
             "objective": {"type": "string"}, "sessionId": {"type": "string"},
             "researchId": {"type": "string"},
             "methodIds": {"type": "array", "items": {"type": "string"}},
             "literatureIds": {"type": "array", "items": {"type": "string"}},
             "reproductionIds": {"type": "array", "items": {"type": "string"}},
             "constraints": {"type": "object"}, "summary": {"type": "string"},
             "series": {"type": "array", "items": {"type": "object"}},
             "symbol": {"type": "string"}, "interval": {"type": "string"},
             "start": {"type": "string"}, "end": {"type": "string"}}}, 60_000)
    _def("quant_list_dossiers",
         "List saved Quant Research Dossiers.",
         quant_list_dossiers_tool, {"type": "object", "properties": {
             "sessionId": {"type": "string"}, "limit": {"type": "integer"}}})
    return list(RESEARCH_TOOLS)


__all__ = ["RESEARCH_TOOLS", "register_research_tools"]
