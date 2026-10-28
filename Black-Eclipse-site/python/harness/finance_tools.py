"""Financial tools — Python-owned contracts, JDdS-backed data.

These are the tools the agents actually call. Their definitions (name, schema,
permission, risk, honesty contract) live here, in the agentic layer. Data comes
from JDdS through the read-only `DataBridge` — the TS side is only the accessor,
so there is still exactly one market-data layer and nothing is fabricated.

Honesty contract (enforced in the tool text, mirrored from the TS vertical
slice): if JDdS has no data, the tool returns an explicit UNAVAILABLE state.
"""

from __future__ import annotations

import time
from typing import Any, Optional

from .tools import DataBridge, ToolContext, ToolDefinition, ToolRegistry, dumps


async def _fetch(ctx: ToolContext, capability: str, params: dict[str, Any]) -> dict[str, Any]:
    if ctx.data_bridge is None:
        return {"status": "UNAVAILABLE", "error": "data bridge not configured"}
    return await ctx.data_bridge.fetch(capability, params)


def _age_label(iso: Optional[str]) -> Optional[str]:
    """A plain age sentence for an observation time, or None when undateable."""
    if not iso:
        return None
    import datetime as dt

    text = str(iso).strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    age = (dt.datetime.now(dt.timezone.utc) - parsed).total_seconds()
    if age < 0:
        return "as of just now"
    if age < 90:
        return "less than 2 minutes old"
    if age < 3600:
        return f"about {int(age // 60)} minutes old"
    if age < 86_400:
        return f"about {int(age // 3600)} hours old"
    days = int(age // 86_400)
    return f"about {days} day{'s' if days != 1 else ''} old"


def _now_iso() -> str:
    import datetime as _dt

    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def _fmt(value: Any) -> str:
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:,.4f}".rstrip("0").rstrip(".")
    if isinstance(value, int):
        return f"{value:,}"
    return str(value)


async def _verified_price_leg(
    ctx: ToolContext, symbol: str, market: Optional[str]
) -> Optional[dict[str, Any]]:
    """Run the price/market-cap leg through the arbitrated retrieval layer.

    Phase 13 follow-up: the snapshot tool previously read the stored price and,
    worse, never ran the retrieval layer at all — so a months-old market cap was
    returned as if current. This routes the SAME fact through the layer, where a
    fresh live reading can beat a saved snapshot, a stale candidate is rejected
    with its age, and a cross-source disagreement is preserved.

    Returns a dict of `{status, values, obs_time, sources, disagreement, warnings}`
    or None when the layer has nothing usable.
    """
    # Import here to keep this module import-light and cycle-free.
    from .retrieval import FinancialRetrievalRequest
    from .retrieval_tools import _layer

    request = FinancialRetrievalRequest(
        objective=f"latest verified price and market cap for {symbol}",
        dataType="current_quote",
        instrument=symbol,
        market=market,
        freshnessRequirement="realtime",
        allowWeb=False,  # a price is structured data; a web snippet is not precise
    )
    result = await _layer(ctx).retrieve(request)
    if result.status not in ("OK", "PARTIAL", "CONFLICTING"):
        return None

    values: dict[str, Any] = result.data if isinstance(result.data, dict) else {}
    sources: list[str] = [r.source for r in result.sourceReferences]
    # The observation time is a property of the OBSERVATION. Pull it from the
    # returned objects first (the live bridge carries it there), then fall back to
    # a source reference's publishedAt. Never fabricate a time.
    obs_time = None
    for item in result.evidence:
        for obj in getattr(item, "objects", []):
            stamp = getattr(obj, "observation_time", None) or getattr(obj, "dataTimestamp", None)
            if stamp:
                obs_time = str(stamp)
                break
        if obs_time:
            break
    if obs_time is None:
        for ref in result.sourceReferences:
            if ref.publishedAt:
                obs_time = ref.publishedAt
                break

    disagreement = None
    if result.conflicts:
        first = result.conflicts[0]
        cands = first.get("candidates") or []
        parts = [
            f"{c.get('source')}: {_fmt(c.get('value'))}" for c in cands
        ]
        if parts:
            disagreement = f"{first.get('metric')} — " + "; ".join(parts)

    return {
        "status": result.status,
        "values": values,
        "obs_time": obs_time,
        "sources": sources,
        "disagreement": disagreement,
        "warnings": list(result.warnings),
        "strategy": list(result.strategy),
        "degraded": result.degraded,
        "conflicts": list(result.conflicts),
        "reason": next((w for w in result.warnings if "CONFLICT" in str(w).upper()
                        or "DISAGREE" in str(w).upper()), None),
    }


async def get_market_snapshot(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    symbol = str(args.get("symbol", "")).strip().upper()
    market = str(args.get("market", "") or "").strip().upper() or None
    ctx.log("jddS snapshot lookup", {"symbol": symbol, "market": market})

    payload = await _fetch(ctx, "market_snapshot", {"symbol": symbol, "market": market})
    status = payload.get("status", "UNAVAILABLE")
    failure_class = payload.get("failureClass")

    if status != "OK":
        # Derive wording from the failure class (B2), never a single generic line.
        detail = payload.get("error", "")
        if failure_class == "ambiguous" or status == "AMBIGUOUS":
            msg = (
                f"AMBIGUOUS — {detail}\n"
                "Ask the user to specify the market/venue (and share class); do NOT guess."
            )
        elif failure_class == "not_covered":
            msg = f"NOT COVERED — {detail}"
        elif failure_class == "not_found":
            msg = f"UNAVAILABLE — {detail}"
        else:
            msg = (
                f"UNAVAILABLE — no stored snapshot for {symbol}"
                + (f" in market {market}" if market else "")
                + f".\n{detail}"
            )
        return msg, {
            "status": "UNAVAILABLE" if status != "AMBIGUOUS" else "AMBIGUOUS",
            "failureClass": failure_class,
            "symbol": symbol,
            "market": market,
            "source": "JDDS",
        }

    # ── Verify the price / market cap through the arbitrated layer ──────────
    verified = await _verified_price_leg(ctx, symbol, market)

    vault_price = payload.get("price") or {}
    vault_obs = payload.get("observationTime") or payload.get("updatedAt")
    contested = bool(verified and verified["status"] == "CONFLICTING")
    live_values = (verified or {}).get("values") or {}
    live_obs = (verified or {}).get("obs_time")
    live_sources = list(dict.fromkeys((verified or {}).get("sources") or []))

    def _resolve(name: str) -> tuple[Any, str]:
        """(value, origin) for one field. Origin is `live`, `saved` or `none`.

        Per-FIELD provenance is the point: the live provider may return a price
        but no market cap, so the cap can be a saved snapshot while the price is
        live. Labelling the whole payload "verified" would repeat the original
        defect in a new form.
        """
        if (
            verified
            and not contested
            and name in live_values
            and live_values[name] is not None
        ):
            return live_values[name], "live"
        v = vault_price.get(name)
        if v is not None:
            return v, "saved"
        return None, "none"

    price_value, price_origin = _resolve("price")
    cap_value, cap_origin = _resolve("marketCap")
    change_value, change_origin = _resolve("changePct")
    volume_value, volume_origin = _resolve("volume")
    pe_value, pe_origin = _resolve("peRatio")

    def _annotate(value: Any, origin: str, suffix: str = "") -> str:
        if value is None:
            return "N/A"
        label = _fmt(value) + suffix
        if contested:
            return label  # both candidates are listed below
        if origin == "saved":
            age = _age_label(vault_obs)
            return f"{label} — saved snapshot" + (f", {age}" if age else "")
        return label

    lines = [
        f"Snapshot for {payload.get('symbol', symbol)} — {payload.get('name', '')}",
        f"  Market: {payload.get('exchange', '')} ({payload.get('country', market)})",
        f"  Currency: {payload.get('currency', 'unknown')}",
        f"  Sector: {payload.get('sector') or 'N/A'}",
        f"  Industry: {payload.get('industry') or 'N/A'}",
        f"  Security type: {payload.get('securityType') or 'N/A'}",
    ]
    if contested:
        # The sources disagree on the price/cap beyond the tolerance. Do NOT
        # present the stored (possibly stale) value as THE answer — every
        # contested figure is shown below with both candidates.
        lines.append("  Price / Market cap: sources disagree — both values are listed below.")
    elif price_value is not None:
        lines += [
            f"  Price: {_annotate(price_value, price_origin)} {payload.get('currency', '')} (per-share)",
            f"  Change: {_annotate(change_value, change_origin, '%')}",
            f"  Market cap: {_annotate(cap_value, cap_origin)}",
            f"  Volume: {_annotate(volume_value, volume_origin)}",
            f"  P/E: {_annotate(pe_value, pe_origin)}",
        ]
    else:
        lines.append("  Price: UNAVAILABLE — no source returned a current price.")

    # ── Say WHERE each value came from and HOW CURRENT it is ────────────────
    if live_values:
        if live_sources:
            lines.append(f"Live source: {', '.join(live_sources)}")
        if live_obs:
            age = _age_label(live_obs)
            lines.append(f"Live observation: {live_obs}" + (f" — {age}" if age else ""))
    saved_fields = [
        label
        for label, origin in (
            ("price", price_origin),
            ("change", change_origin),
            ("market cap", cap_origin),
            ("volume", volume_origin),
            ("P/E", pe_origin),
        )
        if origin == "saved"
    ]
    if saved_fields:
        vault_age = _age_label(vault_obs)
        lines.append(
            "Saved snapshot (not live): "
            + ", ".join(saved_fields)
            + (f" — the stored reading is {vault_age}." if vault_age else ".")
        )
        if vault_obs:
            lines.append(f"Stored at: {vault_obs} (source: JDDS/{payload.get('priceSource', 'n/a')})")
    if not live_values and (price_origin == "saved" or cap_origin == "saved"):
        lines.append("No live reading was available; the values above are a saved snapshot.")

    if verified and verified.get("disagreement"):
        lines.append("")
        lines.append("Sources disagree on this value — both are shown, not one chosen for you:")
        lines.append(f"  {verified['disagreement']}")

    if contested:
        lines.append("")
        lines.append(
            "Because the sources disagree beyond the tolerance, no single figure is "
            "asserted as the answer. Ask the user which source to trust, or use the "
            "range above."
        )

    # The structured `verified` flag is TRUE only when the PRICE itself is live —
    # a saved-only cap must not inherit a verified label.
    price_is_live = price_origin == "live"
    out: dict[str, Any] = {
        "status": "OK",
        "symbol": payload.get("symbol", symbol),
        "market": payload.get("country", market),
        "currency": payload.get("currency"),
        "instrumentId": payload.get("instrumentId"),
        "source": "VERIFIED" if price_is_live else "JDDS",
        "verified": price_is_live,
        "priceOrigin": price_origin,
        "marketCapOrigin": cap_origin,
        "observationTime": live_obs or vault_obs,
        "sources": live_sources or ["JDDS"],
    }
    if verified and verified.get("disagreement"):
        out["disagreement"] = verified["disagreement"]

    # D12: the shared envelope. D1: a cross-source disagreement is DIVERGENT or
    # SCALE_MISMATCH - never VALID, and both candidates + timestamps ride along.
    from .market.quality_contract import (
        DataQualityEnvelope,
        EnvelopeConflict,
        scale_factor as _scale,
        relative_gap as _gap,
    )

    conflicts: list[EnvelopeConflict] = []
    verdict = "VALID" if price_is_live else "UNVERIFIED"
    reason = None
    if contested:
        verdict = "DIVERGENT"
        reason = "DATA_CONFLICT"
        for raw in (verified or {}).get("conflicts") or []:
            candidates = list(raw.get("candidates") or [])
            values = [c.get("value") for c in candidates
                      if isinstance(c.get("value"), (int, float))]
            gap = factor = None
            if len(values) >= 2:
                gap = round(max(_gap(values[0], v) for v in values[1:]), 6)
                factor = _scale(values[0], values[1])
            if factor is not None:
                verdict = "SCALE_MISMATCH"
            conflicts.append(EnvelopeConflict(
                metric=str(raw.get("metric") or "price"),
                relativeGap=gap,
                scaleFactor=factor,
                candidates=candidates,
            ))
        if not conflicts:
            conflicts.append(EnvelopeConflict(
                metric="price",
                candidates=[{"provider": s, "timestamp": live_obs}
                            for s in (live_sources or ["live"])]
                + ([{"provider": "JDDS", "timestamp": vault_obs}] if vault_obs else []),
            ))
        out["reasonCode"] = reason
    out["qualityVerdict"] = verdict
    out["conflict"] = [c.model_dump(mode="json") for c in conflicts] if conflicts else None
    out["envelope"] = DataQualityEnvelope(
        value=None if contested else price_value,
        currency=payload.get("currency"),
        provider=",".join(live_sources) if live_sources else "JDDS",
        observationTimestamp=live_obs or vault_obs,
        retrievalTimestamp=_now_iso(),
        qualityVerdict=verdict,
        conflicts=conflicts,
        routesSkipped=list((verified or {}).get("routesSkipped") or []),
        stale=False,
        reasonCode=reason,
    ).to_dict()

    # D1(d): persist the conflict to the ledger so `get_data_provenance` can
    # surface it for this symbol.
    store = getattr(ctx, "market_store", None)
    if store is not None and conflicts:
        try:
            store.record_quality(
                "quote", symbol, ",".join(live_sources) or "JDDS",
                findings=[{"kind": "conflict", "severity": "warning",
                           "detail": out.get("disagreement") or verdict}],
                conflict={"metric": "price", "verdict": verdict,
                          "candidates": conflicts[0].candidates},
            )
        except Exception:  # noqa: BLE001 - persistence is best-effort
            pass
    return "\n".join(lines), out




async def get_fundamentals(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    symbol = str(args.get("symbol", "")).strip().upper()
    params: dict[str, Any] = {"symbol": symbol}
    # `refresh: true` asks the provider chain (SEC/FMP/Yahoo) for a live profile
    # and live valuation ratios instead of the saved snapshot — the route the
    # stale-P/E complaint asked for. The response labels each ratio's provenance.
    if args.get("refresh") is True:
        params["refresh"] = True
    payload = await _fetch(ctx, "fundamentals", params)
    if payload.get("status") != "OK":
        return f"UNAVAILABLE — no fundamentals stored for {symbol} in JDdS.", {"status": "UNAVAILABLE"}
    return dumps(payload), {"status": "OK", "symbol": symbol}


async def get_news(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    query = str(args.get("query", "") or "")
    payload = await _fetch(ctx, "news", {"query": query})
    failure_class = payload.get("failureClass")
    items = payload.get("items") or []
    source_kind = payload.get("sourceKind", "vault")

    # A source failure must NEVER be phrased as absence of news (B2/C2). An
    # empty result is "no matching data", not "nothing happened".
    if failure_class == "source_failure":
        return (
            "\n".join(
                [
                    "SOURCE FAILURE — the news sources could not be reached.",
                    f"Query: {query!r}",
                    "This is an infrastructure failure, NOT evidence that no news exists. "
                    "Do not report it as 'no news'.",
                    f"Detail: {payload.get('error', '')}",
                ]
            ),
            {"status": "UNAVAILABLE", "failureClass": "source_failure", "count": 0, "source": "JDDS"},
        )
    if not items:
        return (
            f"No matching news stored for {query!r} (sources reachable, no match).",
            {"status": "OK", "failureClass": "no_data", "count": 0, "source": "JDDS"},
        )

    # D8: an undated item is legal, but it must be marked and must never enter a
    # time-sensitive ("latest news") claim. Dates supplied by the provider are
    # preserved EXACTLY, including their timezone.
    normalised: list[dict[str, Any]] = []
    for raw in items:
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        published = item.get("publishedAt") or item.get("published_at") or item.get("timestamp")
        item["publishedAt"] = str(published) if published else None
        item["undated"] = item["publishedAt"] is None
        normalised.append(item)

    time_sensitive = bool(
        args.get("latest") is True
        or any(word in query.lower() for word in ("latest", "today", "this week", "recent"))
    )
    excluded_undated = 0
    visible = normalised
    if time_sensitive:
        visible = [i for i in normalised if not i["undated"]]
        excluded_undated = len(normalised) - len(visible)

    header = (
        f"{len(visible)} news item(s) matching {query!r} (source: {source_kind}):"
    )
    if time_sensitive:
        header += (
            f" {excluded_undated} undated item(s) excluded from this time-sensitive "
            "answer."
        )
    lines = [header]
    for i in visible:
        stamp = i.get("publishedAt") or "undated"
        lines.append(
            f"[{i.get('source')}] ({stamp}) ({i.get('sentiment')}) {i.get('headline')}"
            f"\n  {i.get('url', '')}"
            + ("  [UNDATED - not usable for a time-sensitive claim]" if i["undated"] else "")
        )
    return "\n\n".join(lines), {
        "status": "OK",
        "count": len(visible),
        "items": visible,
        "excludedUndated": excluded_undated,
        "undated": sum(1 for i in normalised if i["undated"]),
        "source": source_kind,
        "sourceKind": source_kind,
    }


def _one_health_line(r: dict[str, Any]) -> str:
    rate = r.get("successRate")
    rate_txt = f"{int(rate * 100)}%" if isinstance(rate, (int, float)) else "n/a"
    last = r.get("lastAttemptAt") or r.get("updatedAt") or "never"
    last_ok = r.get("lastSuccessAt") or "never"
    last_fail = r.get("lastFailureAt") or "never"
    err = f" lastError={r.get('lastError')}" if r.get("lastError") else ""
    truth = r.get("sourceOfTruth") or "live"
    return (
        f"  {r.get('source')} · {r.get('market')} · {r.get('assetClass')} · {r.get('capability', 'quote')}: "
        f"{r.get('health', 'unknown')} — {r.get('success', 0)} ok / {r.get('fail', 0)} fail "
        f"(success {rate_txt}; last attempt {last}, last ok {last_ok}, last fail {last_fail}; via {truth}){err}"
    )


def _health_explainer() -> list[str]:
    return [
        "'unknown' means NO ATTEMPTS RECORDED yet — it is neither healthy nor "
        "failing. Only a route with recorded runs can be working or failing.",
        "Each CAPABILITY is a separate route: a healthy quote route does NOT make "
        "statements, filings, news, web search or PDF extraction healthy. "
        "`configured` (a credential exists) is not the same as `healthy` (runs "
        "succeed), and `via fixture` rows are offline tests — never live health.",
    ]


async def get_source_health(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    recorded_only = bool(args.get("recordedOnly"))
    include_declared = bool(args.get("includeDeclared"))
    payload = await _fetch(
        ctx, "source_health",
        {"recordedOnly": recorded_only, "includeDeclared": include_declared},
    )
    rows = payload.get("rows") or []
    summary = payload.get("summary") or {}
    withheld = int(payload.get("withheld") or 0)

    if not rows and not summary.get("recordedRoutes"):
        # An empty health table is NO DATA, not "everything is fine". Say so.
        return (
            "No source health recorded yet (no_data). Confidence cannot be derived "
            "from history; treat any answer as unverified.",
            {"status": "OK", "failureClass": "no_data", "count": 0},
        )

    by_health = summary.get("byHealth") or {}
    markets = summary.get("marketsWithAttempts") or []
    lines = ["Source health — RECORDED ledger (the only rows that can be working/failing):"]
    lines.append(
        f"  recorded routes: {summary.get('recordedRoutes', len(rows))} live"
        + (f", {summary.get('fixtureRoutes')} fixture" if summary.get("fixtureRoutes") else "")
        + f" — healthy {by_health.get('healthy', 0)}, degraded {by_health.get('degraded', 0)}, "
        f"failing {by_health.get('failing', 0)}, unknown {by_health.get('unknown', 0)}"
    )
    if markets:
        lines.append(f"  markets with any recorded attempt: {', '.join(markets)}")
    lines.append("")
    if rows:
        lines.append("Recorded routes:")
        for r in rows:
            lines.append(_one_health_line(r))
    else:
        lines.append("No LIVE recorded routes (only fixture rows, if any, were found).")
    lines.append("")
    from .retrieval.health import diagnose_routes  # noqa: PLC0415

    diagnosis = diagnose_routes(rows)
    if diagnosis["defects"]:
        lines.append("Diagnosis — routing defects (NOT provider outages):")
        for defect in diagnosis["defects"]:
            lines.append(
                f"  {defect['source']} × {defect['capability']}: generic route failing "
                f"while {', '.join(defect['healthyMarkets'])} succeed — "
                f"{defect['recommendedAction']}"
            )
    if diagnosis["providerFailures"]:
        lines.append("Diagnosis — provider failures (every observed market fails):")
        for provider in diagnosis["providerFailures"]:
            lines.append(
                f"  {provider['source']} × {provider['capability']}: "
                f"{provider['recommendedAction']}"
            )
    lines.extend(_health_explainer())
    if withheld:
        lines.append("")
        lines.append(
            f"{withheld} declared route(s) have ZERO recorded attempts and were "
            "withheld so this report stays readable. Each is `unknown` (neither "
            "healthy nor failing). Request them explicitly with "
            "`get_source_health({includeDeclared: true})` if you need the full list."
        )
    return "\n".join(lines), {
        "status": "OK",
        "count": len(rows),
        "rows": rows,
        "recordedRoutes": summary.get("recordedRoutes", len(rows)),
        "withheld": withheld,
        "diagnosis": diagnosis,
    }


async def get_research_health(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Health of every research retrieval route, WITHOUT running a research task."""
    payload = await _fetch(ctx, "research_health", {})
    rows = payload.get("rows") or []
    if not rows:
        return (
            "No research health could be probed (no_data).",
            {"status": "UNAVAILABLE", "failureClass": "no_data"},
        )
    lines = ["Research retrieval health (per capability):"]
    for r in rows:
        state = "ok" if r.get("ok") else "FAILED"
        detail = f" — {r.get('detail')}" if r.get("detail") else ""
        http = f", HTTP {r.get('httpStatus')}" if r.get("httpStatus") else ""
        lines.append(
            f"  {r.get('provider')} [{r.get('capability')}]: {state} "
            f"({r.get('category')}{http}, {r.get('latencyMs', 0)}ms){detail}"
        )
    lines.append("")
    lines.append(
        "This identifies WHICH capability is failing without a research run. A "
        "failed route is an infrastructure state, not evidence that data is absent."
    )
    return "\n".join(lines), {"status": "OK", "healthy": payload.get("healthy"), "count": len(rows)}


def _fmt_axis(axis: dict[str, Any]) -> str:
    level = str(axis.get("level") or "unknown").replace("_", " ")
    observed = axis.get("observed") or "unknown"
    via = f" via {axis['via']}" if axis.get("via") else ""
    tier = ""
    if axis.get("tier") == "secondary":
        tier = " [SECONDARY route — not the primary venue route]"
    inconsistency = ""
    if axis.get("inconsistent"):
        inconsistency = f" [INCONSISTENT: {axis.get('inconsistencyReason')}]"
    return f"{level}{via} (observed: {observed}){tier}{inconsistency}"


async def get_capability_matrix(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Truthful per-market capability: what is implemented, configured and observed."""
    payload = await _fetch(ctx, "capability_matrix", {})
    rows = payload.get("rows") or []
    if not rows:
        return (
            "Capability matrix unavailable (no_data).",
            {"status": "UNAVAILABLE", "failureClass": "no_data"},
        )
    lines = ["Capability by market (quote ≠ statements; a listed country is not a promise):"]
    for r in rows:
        universe = r.get("universe")
        universe_txt = "unknown" if universe is None else str(universe)
        lines.append(
            f"  {r.get('market')} ({r.get('currency')}) — instruments in universe: {universe_txt}\n"
            f"      quote: {_fmt_axis(r.get('quote') or {})}\n"
            f"      history: {_fmt_axis(r.get('history') or {})}\n"
            f"      fundamentals: {_fmt_axis(r.get('fundamentals') or {})}\n"
            f"      filings: {_fmt_axis(r.get('filings') or {})}\n"
            f"      web/documents: {_fmt_axis(r.get('web') or {})}"
            + ("  [live-checked]" if r.get("liveChecked") else "")
        )
    lines.append("")
    lines.append(
        "IMPORTANT: a market being listed means it is RECOGNISED, not that every "
        "capability works there. 'fundamentals: not implemented/unconfigured' means "
        "no statement route is available for that market — do NOT infer statements "
        "from a working quote. If a capability is unconfigured, the fix is an "
        "operator-supplied credential, not a different ticker. When a capability is "
        "missing, still try the OTHER eligible routes (web/filing research) before "
        "concluding that evidence is unavailable — unless the USER explicitly "
        "restricted which sources may be used."
    )
    return "\n".join(lines), {"status": "OK", "count": len(rows)}


async def get_coverage(args: dict[str, Any], ctx: ToolContext) -> tuple[str, Any]:
    """Declared market recognition + a compact per-market capability verdict.

    This reports what the app RECOGNISES (a market id/currency/exchange is known)
    separately from what each capability can actually DO there. It deliberately
    does NOT tell the agent to stop when a market or instrument is missing — a
    missing universe row is a reason to try the other eligible routes.
    """
    payload = await _fetch(ctx, "capability_matrix", {})
    rows = payload.get("rows") or []
    if not rows:
        return "Capability matrix is empty.", {"status": "OK", "count": 0}
    lines = ["Recognised markets (market — currency — instruments in universe — key capabilities):"]
    for r in rows:
        universe = r.get("universe")
        universe_txt = "unknown" if universe is None else str(universe)
        quote = str((r.get("quote") or {}).get("level") or "unknown").replace("_", " ")
        fund = str((r.get("fundamentals") or {}).get("level") or "unknown").replace("_", " ")
        filings = str((r.get("filings") or {}).get("level") or "unknown").replace("_", " ")
        lines.append(
            f"  {r.get('market')} — {r.get('currency')} — {universe_txt} — "
            f"quote:{quote}, fundamentals:{fund}, filings:{filings}"
        )
    lines.append("")
    lines.append(
        "A listed market is RECOGNISED; it is NOT a promise that every capability "
        "works there. When a ticker or market is missing from the stored universe, "
        "or a capability is unconfigured, that is NOT a reason to stop: try the other "
        "eligible routes (live quote/history providers, official filings, then "
        "bounded web research) and report what those routes returned before "
        "concluding that evidence is unavailable. Return UNAVAILABLE only when every "
        "eligible route has been tried and none produced the fact. For the full "
        "per-capability detail, use get_capability_matrix."
    )
    lines.append("")
    lines.append(
        "Four distinctions this summary enforces:\n"
        "  1. RECOGNISED market ≠ WORKING data route — a country can be listed while "
        "no statement/filing route exists for it.\n"
        "  2. CONFIGURED ≠ HEALTHY — a route with a credential may still be failing.\n"
        "  3. UNKNOWN / NO ATTEMPTS ≠ FAILURE — a route with zero recorded runs is "
        "neither healthy nor failing; it is simply untested.\n"
        "  4. MISSING JDdS DATA ≠ STOP — a vault miss is a reason to try the other "
        "eligible routes, not to conclude the fact does not exist."
    )
    return "\n".join(lines), {"status": "OK", "count": len(rows)}


def register_finance_tools(registry: ToolRegistry) -> None:
    registry.register(
        ToolDefinition(
            name="get_market_snapshot",
            description=(
                "Read a symbol's price, change, market cap, volume, sector and industry. "
                "The price/market-cap leg is VERIFIED across every eligible source (a live "
                "provider and the stored snapshot) and the observation's age is stated; a "
                "stale snapshot is not presented as current, and a cross-source "
                "disagreement is shown rather than one value silently chosen. Returns "
                "UNAVAILABLE when the symbol is not resolvable — it never invents data."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol, e.g. AAPL, SYS, BTC."},
                    "market": {"type": "string", "description": "Market/venue code (US, PK, PSX, IN, CRYPTO). Required when the ticker is listed on more than one market; there is no default."},
                },
                "required": ["symbol"],
            },
            handler=get_market_snapshot,
            permission="read",
            risk="low",
            timeout_ms=25_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_fundamentals",
            description=(
                "Read the profile and valuation ratios for a symbol: sector/industry, "
                "plus P/E and forward P/E with their provenance. Pass refresh=true to "
                "pull live values from the provider chain instead of the saved snapshot."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "symbol": {"type": "string", "description": "Ticker symbol."},
                    "refresh": {
                        "type": "boolean",
                        "description": "Fetch live profile + ratios from the provider chain (default false).",
                    },
                },
                "required": ["symbol"],
            },
            handler=get_fundamentals,
            permission="read",
            risk="low",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_news",
            description="Read recent stored news headlines/sentiment from JDdS, optionally filtered by keyword.",
            input_schema={
                "type": "object",
                "properties": {"query": {"type": "string", "description": "Optional keyword/ticker filter."}},
            },
            handler=get_news,
            permission="read",
            risk="low",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_source_health",
            description=(
                "Read the RECORDED reliability/health of each data route (provider × market × asset "
                "class × capability), derived from real runs. Returns a compact summary plus the "
                "recorded rows; declared-but-unrun routes are withheld by default (they are "
                "`unknown`, never healthy). Set recordedOnly=true for only recorded rows, or "
                "includeDeclared=true for the full declared enumeration."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "recordedOnly": {"type": "boolean", "description": "Return only rows with recorded attempts."},
                    "includeDeclared": {"type": "boolean", "description": "Include declared-but-unrun routes (large)."},
                    "limit": {"type": "integer", "description": "Max recorded head rows (default 25)."},
                },
            },
            handler=get_source_health,
            permission="read",
            risk="low",
        )
    )
    registry.register(
        ToolDefinition(
            name="get_research_health",
            description=(
                "Probe the health of every research retrieval route (web search, page fetch, "
                "SEC direct) and report which capability is failing, with the structured reason "
                "(timeout/block/http/parse). Use this to diagnose a missing source without "
                "running a full research task. A failed route is not evidence that data is absent."
            ),
            input_schema={"type": "object", "properties": {}},
            handler=get_research_health,
            permission="read",
            risk="low",
            timeout_ms=30_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_capability_matrix",
            description=(
                "Truthful per-market capability: for each recognised market, what is "
                "implemented, configured and observed for quote, history, fundamentals, "
                "official filings and web/document retrieval, plus the instrument-universe "
                "size. Use this to learn whether a market can actually serve a data type — a "
                "listed country is NOT a promise. 'not implemented/unconfigured' means no "
                "route exists for that market yet; try other eligible routes rather than "
                "concluding the data is absent."
            ),
            input_schema={"type": "object", "properties": {}},
            handler=get_capability_matrix,
            permission="read",
            risk="low",
            timeout_ms=30_000,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_coverage",
            description=(
                "List the markets this system RECOGNISES and a compact capability verdict "
                "(quote/fundamentals/filings) for each. Recognition is not a capability "
                "promise. A ticker or market missing from the stored universe is NOT a reason "
                "to stop: try the other eligible routes before concluding evidence is "
                "unavailable. For full per-capability detail use get_capability_matrix."
            ),
            input_schema={"type": "object", "properties": {}},
            handler=get_coverage,
            permission="read",
            risk="low",
        )
    )


__all__ = ["register_finance_tools", "DataBridge"]
