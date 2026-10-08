"""Agent-facing portfolio tools.

Names use the runtime's flat `portfolio_*` convention (the ONE ToolRegistry
rejects dotted names). The mapping to the directive's conceptual names:

    portfolio.get             → portfolio_get
    portfolio.add_position    → portfolio_add_position
    portfolio.remove_position → portfolio_remove_position
    portfolio.update_position → portfolio_update_position
    portfolio.calculate_pnl   → portfolio_calculate_pnl
    portfolio.calculate_exposure → portfolio_calculate_exposure
    portfolio.calculate_allocation → portfolio_calculate_allocation
    portfolio.calculate_risk  → portfolio_calculate_risk
    portfolio.calculate_tax_lots → portfolio_calculate_tax_lots
    portfolio.rebalance       → portfolio_rebalance

Safety classification (§36):
  * read tools  — get / calculate_* / list. No effect.
  * mutating    — add/remove/update position, create portfolio, set metadata.
                  permission=write, effect=portfolio.write → requires approval.
  * consequential — rebalance. permission=write, effect=portfolio.rebalance_proposal;
                  it only PROPOSES (never executes).
"""

from __future__ import annotations

from typing import Any

from .errors import PortfolioError

READ = "read"
WRITE = "write"


def _service(ctx: Any) -> Any:
    service = getattr(ctx, "portfolio_service", None)
    if service is None:
        raise PortfolioError(
            "PORTFOLIO_UNAVAILABLE",
            "the portfolio engine is not available in this run",
        )
    return service


def _actor(ctx: Any) -> Any:
    return getattr(ctx, "user_id", None)


def _fail(error: Any) -> tuple[str, Any]:
    payload = error.to_dict() if isinstance(error, PortfolioError) else {
        "code": "PORTFOLIO_ERROR", "message": str(error), "details": {}, "retryable": False,
    }
    return f"Portfolio error ({payload['code']}): {payload['message']}", {
        "status": "FAILED", "error": payload,
    }


async def _run(fn: Any, *args: Any, **kwargs: Any) -> tuple[str, Any]:
    try:
        return await fn(*args, **kwargs)
    except PortfolioError as exc:
        return _fail(exc)


# ── Read tools ────────────────────────────────────────────────────────────────

async def portfolio_list(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    rows = service.list_portfolios(owner_id=args.get("owner_id") or getattr(ctx, "user_id", None))
    lines = [f"{len(rows)} portfolio(s):"]
    for r in rows:
        lines.append(f"  - {r['id']}  {r['name']}  ({r.get('baseCurrency')}, {r.get('costBasisMethod')})")
    return "\n".join(lines), {"portfolios": rows}


async def portfolio_create(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)

    async def _do() -> tuple[str, Any]:
        record = service.create_portfolio(
            args.get("name") or "Portfolio",
            base_currency=(args.get("base_currency") or "USD"),
            cost_basis_method=args.get("cost_basis_method") or "FIFO",
            description=args.get("description"),
            owner_id=getattr(ctx, "user_id", None),
            created_by=args.get("created_by"),
        )
        return f"Created portfolio {record['id']} ({record['name']}).", {"status": "SUCCESS", "portfolio": record}

    return await _run(_do)


async def portfolio_get(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    include = args.get("include") or ["positions", "cash", "pnl", "allocation", "exposure"]
    try:
        reading = await service.read(
            args["portfolio_id"], include=include, gateway=getattr(ctx, "market_gateway", None),
            actor_id=_actor(ctx),
        )
    except PortfolioError as exc:
        return _fail(exc)
    val = reading["valuation"]
    text = (
        f"Portfolio {reading['portfolio']['name']}: total {val['totalValue']} "
        f"{val['baseCurrency']} (cash {val['cash']}), {len(reading['positions'])} open position(s); "
        f"data quality {val['dataQuality']['status']}."
    )
    return text, reading


async def portfolio_calculate_pnl(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        reading = await service.read(args["portfolio_id"], include=["pnl"],
                                     gateway=getattr(ctx, "market_gateway", None), actor_id=_actor(ctx))
    except PortfolioError as exc:
        return _fail(exc)
    pnl = reading["pnl"]
    text = (
        f"P&L: realized {pnl['realizedPnl']}, unrealized {pnl['unrealizedPnl']}, "
        f"total {pnl['totalPnl']} {reading['portfolio']['baseCurrency']}."
    )
    return text, {"portfolio": reading["portfolio"], "pnl": pnl, "dataQuality": reading["dataQuality"]}


async def portfolio_calculate_exposure(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    dimension = args.get("dimension") or "assetClass"
    try:
        reading = await service.read(args["portfolio_id"], include=["exposure"],
                                     gateway=getattr(ctx, "market_gateway", None), actor_id=_actor(ctx))
    except PortfolioError as exc:
        return _fail(exc)
    exposure = reading["exposure"].get(dimension) or reading["exposure"]["asset"]
    text = (
        f"{dimension} exposure: gross {exposure['grossExposure']}, net {exposure['netExposure']} "
        f"{exposure['baseCurrency']}."
    )
    return text, {"portfolio": reading["portfolio"], "exposure": reading["exposure"], "dimension": dimension}


async def portfolio_calculate_allocation(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    dimension = args.get("dimension") or "asset"
    try:
        reading = await service.read(args["portfolio_id"], include=["allocation"],
                                     gateway=getattr(ctx, "market_gateway", None), actor_id=_actor(ctx))
    except PortfolioError as exc:
        return _fail(exc)
    allocation = reading["allocation"].get(dimension) or reading["allocation"]["asset"]
    text = f"{dimension} allocation across {len(allocation['breakdown'])} bucket(s); reconciles={allocation['reconciles']}."
    return text, {"portfolio": reading["portfolio"], "allocation": reading["allocation"], "dimension": dimension}


async def portfolio_calculate_risk(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        existing = service.get_portfolio_record(args["portfolio_id"], actor_id=_actor(ctx))
    except PortfolioError as exc:
        return _fail(exc)
    if existing is None:
        return _fail(PortfolioError("PORTFOLIO_NOT_FOUND", f"portfolio {args['portfolio_id']} not found"))
    try:
        reading = await service.read(
            args["portfolio_id"], include=["risk"], gateway=getattr(ctx, "market_gateway", None),
            confidence=float(args.get("confidence") or 0.95), actor_id=_actor(ctx),
        )
    except PortfolioError as exc:
        return _fail(exc)
    risk = reading["risk"]
    metrics = risk.get("metrics", {})
    text = (
        f"Risk status {risk['status']}; volatility={metrics.get('volatility')}, "
        f"sharpe={metrics.get('sharpe')}, maxDD={metrics.get('maxDrawdown')}."
    )
    return text, {"portfolio": reading["portfolio"], "risk": risk}


async def portfolio_calculate_tax_lots(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        lots = service.calculate_tax_lots(args["portfolio_id"], symbol=args.get("symbol"),
                                          actor_id=_actor(ctx))
    except PortfolioError as exc:
        return _fail(exc)
    total = sum((len(s["openLots"]) for s in lots["symbols"]), 0)
    return (
        f"Tax lots ({lots['method']}): {total} open lot(s) across {len(lots['symbols'])} symbol(s).",
        lots,
    )


# ── Mutating tools ────────────────────────────────────────────────────────────

async def portfolio_add_position(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    payload = {
        "type": args.get("type") or "BUY",
        "symbol": args["symbol"],
        "quantity": args["quantity"],
        "price": args.get("price"),
        "fees": args.get("fees"),
        "taxes": args.get("taxes"),
        "currency": args.get("currency"),
        "trade_date": args.get("trade_date"),
        "asset_type": args.get("asset_type"),
        "account_id": args.get("account_id"),
        "notes": args.get("notes"),
        "external_id": args.get("external_id"),
        "source": args.get("source") or "agent",
        "created_by": getattr(ctx, "user_id", None),
    }
    outcome = service.add_position(args["portfolio_id"], payload, actor_id=_actor(ctx))
    if outcome.get("status") == "FAILED":
        return _fail(_error_from(outcome))
    return f"Recorded {payload['type']} {args['quantity']} {args['symbol']}.", outcome


async def portfolio_remove_position(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    outcome = await service.remove_position(args["portfolio_id"], {
        "symbol": args["symbol"],
        "price": args.get("price"),
        "use_market_price": args.get("use_market_price", True),
        "reason": args.get("reason"),
        "source": args.get("source") or "agent",
        "created_by": getattr(ctx, "user_id", None),
    }, actor_id=_actor(ctx))
    if outcome.get("status") == "FAILED":
        return _fail(_error_from(outcome))
    return f"Closed position {args['symbol']}.", outcome


async def portfolio_update_position(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    outcome = service.update_position(args["portfolio_id"], {
        "symbol": args["symbol"],
        "target_quantity": args["target_quantity"],
        "price": args.get("price"),
        "reason": args.get("reason"),
        "created_by": getattr(ctx, "user_id", None),
    }, actor_id=_actor(ctx))
    if outcome.get("status") == "FAILED":
        return _fail(_error_from(outcome))
    return f"Corrected {args['symbol']} to quantity {args['target_quantity']}.", outcome


async def portfolio_set_metadata(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    outcome = service.set_position_metadata(args["portfolio_id"], args, actor_id=_actor(ctx))
    if outcome.get("status") == "FAILED":
        return _fail(_error_from(outcome))
    return f"Updated metadata for {args['symbol']}.", outcome


async def portfolio_rebalance(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    outcome = await service.rebalance(args["portfolio_id"], {
        "target": args["target"],
        "allowed_drift": args.get("allowed_drift", 0.05),
        "method": args.get("method", "threshold"),
        "fee_rate": args.get("fee_rate", 0.0),
        "tax_rules": args.get("tax_rules"),
        "no_trade": args.get("no_trade"),
        "created_by": getattr(ctx, "user_id", None),
    }, actor_id=_actor(ctx))
    if outcome.get("status") == "FAILED":
        return _fail(_error_from(outcome))
    n = len(outcome.get("recommendations", []))
    return (
        f"Rebalance proposal ({outcome['method']}) with {n} recommendation(s); "
        "no trades are executed — user approval is required.",
        outcome,
    )


async def portfolio_apply_corporate_action(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    outcome = service.apply_corporate_action(args["portfolio_id"], args, actor_id=_actor(ctx))
    if outcome.get("status") == "FAILED":
        return _fail(_error_from(outcome))
    return f"Applied corporate action {outcome.get('action')}.", outcome


async def portfolio_record_swap(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    outcome = service.apply_swap(args["portfolio_id"], args, actor_id=_actor(ctx))
    if outcome.get("status") == "FAILED":
        return _fail(_error_from(outcome))
    return f"Recorded swap {outcome.get('fromSymbol')} -> {outcome.get('toSymbol')}.", outcome


async def portfolio_record_bridge(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    outcome = service.apply_bridge(args["portfolio_id"], args, actor_id=_actor(ctx))
    if outcome.get("status") == "FAILED":
        return _fail(_error_from(outcome))
    return f"Recorded bridge {outcome.get('fromSymbol')} -> {outcome.get('toSymbol')}.", outcome


async def portfolio_record_reward(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    outcome = service.record_reward(args["portfolio_id"], args, actor_id=_actor(ctx))
    if outcome.get("status") == "FAILED":
        return _fail(_error_from(outcome))
    return f"Recorded {args.get('type', 'STAKING_REWARD')} of {args.get('quantity')} {args.get('symbol')}.", outcome


async def portfolio_apply_staking(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    outcome = service.apply_staking(args["portfolio_id"], args, actor_id=_actor(ctx))
    if outcome.get("status") == "FAILED":
        return _fail(_error_from(outcome))
    return f"Recorded {args.get('action', 'stake')} for {args.get('symbol')}.", outcome


async def portfolio_rebuild(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    outcome = service.rebuild_all(args["portfolio_id"], actor_id=_actor(ctx))
    return f"Rebuilt {outcome['symbols']} materialized position(s).", outcome


async def portfolio_apply_slashing(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    outcome = service.apply_slashing(args["portfolio_id"], args, actor_id=_actor(ctx))
    if outcome.get("status") == "FAILED":
        return _fail(_error_from(outcome))
    return f"Recorded slashing of {args.get('quantity')} {args.get('symbol')}.", outcome


async def portfolio_record_funding(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    outcome = service.record_funding(args["portfolio_id"], args, actor_id=_actor(ctx))
    if outcome.get("status") == "FAILED":
        return _fail(_error_from(outcome))
    return f"Recorded funding {args.get('amount')}.", outcome


async def portfolio_reconcile(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    outcome = service.reconcile(args["portfolio_id"], args, actor_id=_actor(ctx))
    if outcome.get("status") == "FAILED" and outcome.get("error"):
        return _fail(_error_from(outcome))
    counts = outcome.get("counts", {})
    return (f"Reconciliation: {outcome.get('status')} "
            f"(matched {counts.get('MATCHED', 0)}, mismatch {counts.get('MISMATCH', 0)}, "
            f"missing {counts.get('MISSING', 0)}).", outcome)


async def portfolio_list_reconciliations(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        rows = service.list_reconciliations(args["portfolio_id"], args.get("limit", 50), actor_id=_actor(ctx))
    except PortfolioError as exc:
        return _fail(exc)
    return f"{len(rows)} reconciliation run(s).", {"reconciliations": rows}


async def portfolio_optimize(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    outcome = service.optimize(args["portfolio_id"], args, actor_id=_actor(ctx))
    if outcome.get("available") is False or outcome.get("status") == "FAILED":
        return _fail(_error_from(outcome) if outcome.get("error") else PortfolioError("OPTIMIZE_UNAVAILABLE", outcome.get("reason", "optimization unavailable")))
    return (
        f"Optimizer ({outcome['method']}) produced weights for {len(outcome['weights'])} assets; "
        "proposal only — no trades placed.",
        outcome,
    )


async def portfolio_attribution(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        outcome = await service.attribution(args["portfolio_id"], args, actor_id=_actor(ctx))
    except PortfolioError as exc:
        return _fail(exc)
    if outcome.get("available") is False:
        return _fail(PortfolioError("ATTRIBUTION_UNAVAILABLE", outcome.get("reason", "unavailable")))
    effects = outcome.get("effects", {})
    return (f"Brinson attribution: allocation {effects.get('allocation')}, "
            f"selection {effects.get('selection')}, interaction {effects.get('interaction')}.",
            outcome)


async def portfolio_factor_exposure(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        outcome = await service.factor_exposure(args["portfolio_id"], args, actor_id=_actor(ctx))
    except PortfolioError as exc:
        return _fail(exc)
    if outcome.get("available") is False:
        return _fail(PortfolioError("FACTOR_UNAVAILABLE", outcome.get("reason", "unavailable")))
    return f"Factor exposures: {outcome['exposures']}.", outcome


async def portfolio_hedge(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    try:
        outcome = await service.hedge(args["portfolio_id"], args, actor_id=_actor(ctx))
    except PortfolioError as exc:
        return _fail(exc)
    return f"{len(outcome['proposals'])} currency hedge proposal(s); proposal only.", outcome


async def portfolio_aggregate(args: dict[str, Any], ctx: Any) -> tuple[str, Any]:
    service = _service(ctx)
    outcome = await service.aggregate({**args, "owner_id": args.get("owner_id") or _actor(ctx)},
                                      actor_id=_actor(ctx))
    return f"Aggregate: {outcome['totalValue']} {outcome['baseCurrency']} across {outcome['portfolioCount']} portfolio(s).", outcome


def _error_from(outcome: dict[str, Any]) -> PortfolioError:
    err = outcome.get("error") or {}
    return PortfolioError(err.get("code", "PORTFOLIO_ERROR"), err.get("message", "operation failed"),
                          err.get("details", {}))


# ── Registration ──────────────────────────────────────────────────────────────

def register_portfolio_tools(registry: Any) -> None:
    from ..tools import ToolDefinition

    def _def(name: str, description: str, handler: Any, schema: dict[str, Any],
             permission: str, effect: Any = None, timeout: int = 20_000) -> None:
        registry.register(ToolDefinition(
            name=name, description=description, input_schema=schema, handler=handler,
            permission=permission, risk="low" if permission == READ else "medium",
            timeout_ms=timeout, effect=effect,
        ))

    pid = {"portfolio_id": {"type": "string", "description": "Portfolio id."}}
    include = {"include": {"type": "array", "items": {"type": "string"},
                           "description": "Sections: positions, cash, pnl, allocation, exposure, risk, performance."}}

    _def("portfolio_list", "List portfolios for the current user.", portfolio_list,
         {"type": "object", "properties": {"owner_id": {"type": "string"}}}, READ)
    _def("portfolio_create",
         "Create a portfolio. `cost_basis_method` is FIFO, LIFO or AVERAGE_COST.",
         portfolio_create,
         {"type": "object", "properties": {
             "name": {"type": "string"}, "base_currency": {"type": "string"},
             "cost_basis_method": {"type": "string", "enum": ["FIFO", "LIFO", "AVERAGE_COST"]},
             "description": {"type": "string"}}, "required": ["name"]},
         WRITE, "portfolio.write")
    _def("portfolio_get",
         "Read a portfolio: positions, cash, valuation, P&L, allocation and exposure, "
         "with per-price freshness/data-quality. Prices come from the Market Data Gateway.",
         portfolio_get, {"type": "object", "properties": {**pid, **include}, "required": ["portfolio_id"]},
         READ)
    _def("portfolio_calculate_pnl",
         "Realized/unrealized/total P&L derived from the transaction ledger.",
         portfolio_calculate_pnl, {"type": "object", "properties": {**pid}, "required": ["portfolio_id"]},
         READ)
    _def("portfolio_calculate_exposure",
         "Gross/net exposure by asset, asset class, sector, currency or country.",
         portfolio_calculate_exposure,
         {"type": "object", "properties": {**pid, "dimension": {"type": "string"}}, "required": ["portfolio_id"]},
         READ)
    _def("portfolio_calculate_allocation",
         "Allocation weights by asset, asset class, sector, currency or country (weights reconcile to 100%).",
         portfolio_calculate_allocation,
         {"type": "object", "properties": {**pid, "dimension": {"type": "string"}}, "required": ["portfolio_id"]},
         READ)
    _def("portfolio_calculate_risk",
         "Deterministic risk: volatility, Sharpe, Sortino, max drawdown, VaR/CVaR (historical, "
         "parametric and seeded Monte-Carlo), beta and correlation. Needs price history; reports "
         "UNAVAILABLE rather than inventing numbers.",
         portfolio_calculate_risk,
         {"type": "object", "properties": {**pid, "confidence": {"type": "number"}}}, READ, timeout=40_000)
    _def("portfolio_calculate_tax_lots",
         "Open tax lots and realized lot matches under the portfolio's cost-basis method.",
         portfolio_calculate_tax_lots,
         {"type": "object", "properties": {**pid, "symbol": {"type": "string"}}, "required": ["portfolio_id"]},
         READ)
    _def("portfolio_add_position",
         "Add a position by recording a BUY (or TRANSFER_IN) transaction; tax lots and the derived "
         "position are updated. Never a blind quantity UPDATE.",
         portfolio_add_position,
         {"type": "object", "properties": {
             **pid, "symbol": {"type": "string"}, "quantity": {"type": "string"},
             "price": {"type": "string"}, "fees": {"type": "string"}, "taxes": {"type": "string"},
             "currency": {"type": "string"}, "trade_date": {"type": "string"},
             "type": {"type": "string", "enum": ["BUY", "TRANSFER_IN"]},
             "asset_type": {"type": "string"}, "external_id": {"type": "string"},
             "notes": {"type": "string"}}, "required": ["portfolio_id", "symbol", "quantity"]},
         WRITE, "portfolio.write")
    _def("portfolio_remove_position",
         "Close a position by recording a real SELL disposal (tax lots matched, realized P&L).",
         portfolio_remove_position,
         {"type": "object", "properties": {
             **pid, "symbol": {"type": "string"}, "price": {"type": "string"},
             "use_market_price": {"type": "boolean"}, "reason": {"type": "string"}},
          "required": ["portfolio_id", "symbol"]},
         WRITE, "portfolio.write")
    _def("portfolio_update_position",
         "Correct a position quantity by appending an auditable ADJUSTMENT (history is never "
         "rewritten; a reason is required).",
         portfolio_update_position,
         {"type": "object", "properties": {
             **pid, "symbol": {"type": "string"}, "target_quantity": {"type": "string"},
             "price": {"type": "string"}, "reason": {"type": "string"}},
          "required": ["portfolio_id", "symbol", "target_quantity", "reason"]},
         WRITE, "portfolio.write")
    _def("portfolio_set_metadata",
         "Set descriptive metadata (name, asset class, sector, country, strategy, currency) used "
         "for exposure and allocation grouping.",
         portfolio_set_metadata,
         {"type": "object", "properties": {
             **pid, "symbol": {"type": "string"}, "name": {"type": "string"},
             "asset_class": {"type": "string"}, "sector": {"type": "string"},
             "country": {"type": "string"}, "strategy": {"type": "string"},
             "currency": {"type": "string"}}, "required": ["portfolio_id", "symbol"]},
         WRITE, "portfolio.write")
    _def("portfolio_rebalance",
         "Propose a rebalance (threshold/calendar/hybrid) against target weights. Returns buy/sell "
         "recommendations, allocation before/after, estimated fees and tax impact. NEVER executes "
         "trades; execution requires user approval in the Trading layer.",
         portfolio_rebalance,
         {"type": "object", "properties": {
             **pid, "target": {"type": "object",
                               "description": "Map of symbol → target weight (fraction or percent)."},
             "allowed_drift": {"type": "number"}, "method": {"type": "string"},
             "fee_rate": {"type": "number"}, "tax_rules": {"type": "object"},
             "no_trade": {"type": "array", "items": {"type": "string"}}},
          "required": ["portfolio_id", "target"]},
         WRITE, "portfolio.rebalance_proposal")
    _def("portfolio_apply_corporate_action",
         "Apply an auditable corporate action as real ledger entries: SPLIT, REVERSE_SPLIT, "
         "SPIN_OFF (reallocates parent basis to the child), MERGER (stock ratio + optional cash "
         "consideration) or SYMBOL_CHANGE. History is never rewritten.",
         portfolio_apply_corporate_action,
         {"type": "object", "properties": {
             **pid,
             "action": {"type": "string", "enum": ["SPLIT", "REVERSE_SPLIT", "SPIN_OFF", "MERGER", "SYMBOL_CHANGE"]},
             "symbol": {"type": "string"}, "ratio": {"type": "string"},
             "parent_symbol": {"type": "string"}, "child_symbol": {"type": "string"},
             "child_quantity": {"type": "string"}, "child_shares_per_parent": {"type": "string"},
             "child_price": {"type": "string"}, "parent_price": {"type": "string"},
             "acquired_symbol": {"type": "string"}, "acquirer_symbol": {"type": "string"},
             "exchange_ratio": {"type": "string"}, "acquirer_price": {"type": "string"},
             "cash_per_share": {"type": "string"}, "old_symbol": {"type": "string"},
             "new_symbol": {"type": "string"}, "trade_date": {"type": "string"},
             "reason": {"type": "string"}}, "required": ["portfolio_id", "action"]},
         WRITE, "portfolio.write")
    _def("portfolio_record_swap",
         "Record a crypto swap: a taxable disposal of from_symbol plus an acquisition of "
         "to_symbol at fair value (basis carried = net proceeds).",
         portfolio_record_swap,
         {"type": "object", "properties": {
             **pid, "from_symbol": {"type": "string"}, "to_symbol": {"type": "string"},
             "from_quantity": {"type": "string"}, "from_price": {"type": "string"},
             "to_quantity": {"type": "string"}, "to_price": {"type": "string"},
             "fees": {"type": "string"}, "currency": {"type": "string"}},
          "required": ["portfolio_id", "from_symbol", "to_symbol", "from_quantity", "from_price"]},
         WRITE, "portfolio.write")
    _def("portfolio_record_bridge",
         "Record a cross-chain bridge: an in-kind transfer where cost basis carries and no "
         "gain/loss is realized.",
         portfolio_record_bridge,
         {"type": "object", "properties": {
             **pid, "from_symbol": {"type": "string"}, "to_symbol": {"type": "string"},
             "quantity": {"type": "string"}, "to_quantity": {"type": "string"}},
          "required": ["portfolio_id", "from_symbol", "to_symbol", "quantity"]},
         WRITE, "portfolio.write")
    _def("portfolio_record_reward",
         "Record a staking reward or airdrop as an acquisition at fair market value.",
         portfolio_record_reward,
         {"type": "object", "properties": {
             **pid, "type": {"type": "string", "enum": ["STAKING_REWARD", "AIRDROP"]},
             "symbol": {"type": "string"}, "quantity": {"type": "string"},
             "price": {"type": "string"}, "currency": {"type": "string"},
             "trade_date": {"type": "string"}, "notes": {"type": "string"}},
          "required": ["portfolio_id", "symbol", "quantity"]},
         WRITE, "portfolio.write")
    _def("portfolio_apply_staking",
         "Record a staking lock/unlock. Custody-only: the position and its basis are unchanged.",
         portfolio_apply_staking,
         {"type": "object", "properties": {
             **pid, "action": {"type": "string", "enum": ["stake", "unstake"]},
             "symbol": {"type": "string"}, "quantity": {"type": "string"}, "notes": {"type": "string"}},
          "required": ["portfolio_id", "symbol", "quantity"]},
         WRITE, "portfolio.write")
    _def("portfolio_rebuild",
         "Recompute and persist all derived lots and materialized positions for a portfolio "
         "(self-heal after an out-of-band change).",
         portfolio_rebuild,
         {"type": "object", "properties": {**pid}, "required": ["portfolio_id"]},
         WRITE, "portfolio.write")
    _def("portfolio_apply_slashing",
         "Write off slashed/written-off tokens (a disposal at zero proceeds, realizing a loss).",
         portfolio_apply_slashing,
         {"type": "object", "properties": {
             **pid, "symbol": {"type": "string"}, "quantity": {"type": "string"},
             "notes": {"type": "string"}, "trade_date": {"type": "string"}},
          "required": ["portfolio_id", "symbol", "quantity"]},
         WRITE, "portfolio.write")
    _def("portfolio_record_funding",
         "Record a perpetual-futures funding payment. Signed: positive = received, negative = paid.",
         portfolio_record_funding,
         {"type": "object", "properties": {
             **pid, "symbol": {"type": "string"}, "amount": {"type": "string"},
             "currency": {"type": "string"}, "trade_date": {"type": "string"}},
          "required": ["portfolio_id", "amount"]},
         WRITE, "portfolio.write")
    _def("portfolio_reconcile",
         "Reconcile the ledger against an external statement (broker/exchange/wallet/manual). "
         "Returns MATCHED/MISMATCH/MISSING/UNKNOWN per symbol; never mutates the ledger.",
         portfolio_reconcile,
         {"type": "object", "properties": {
             **pid, "external_positions": {"type": "array", "items": {"type": "object"}},
             "source": {"type": "string"}, "tolerance": {"type": "string"},
             "relative_tolerance": {"type": "number"}, "as_of": {"type": "string"}},
          "required": ["portfolio_id", "external_positions"]},
         READ)
    _def("portfolio_list_reconciliations",
         "List saved reconciliation runs for a portfolio.",
         portfolio_list_reconciliations,
         {"type": "object", "properties": {**pid, "limit": {"type": "integer"}}, "required": ["portfolio_id"]},
         READ)
    _def("portfolio_optimize",
         "Constrained portfolio optimizer (min_variance / mean_variance / inverse_volatility) with "
         "long-only, per-asset bounds and an optional turnover cap. Proposal only.",
         portfolio_optimize,
         {"type": "object", "properties": {
             **pid, "symbols": {"type": "array", "items": {"type": "string"}},
             "expected_returns": {"type": "array", "items": {"type": "number"}},
             "covariance": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
             "min_weights": {"type": "array", "items": {"type": "number"}},
             "max_weights": {"type": "array", "items": {"type": "number"}},
             "risk_aversion": {"type": "number"}, "turnover_cap": {"type": "number"},
             "method": {"type": "string", "enum": ["min_variance", "mean_variance", "inverse_volatility"]}},
          "required": ["portfolio_id"]},
         WRITE, "portfolio.rebalance_proposal")
    _def("portfolio_attribution",
         "Brinson single-period performance attribution (allocation/selection/interaction) by group.",
         portfolio_attribution,
         {"type": "object", "properties": {
             **pid, "dimension": {"type": "string"},
             "segments": {"type": "array", "items": {"type": "object"}},
             "benchmark_weights": {"type": "object"}, "portfolio_returns": {"type": "object"},
             "benchmark_returns": {"type": "object"},
             "method": {"type": "string", "enum": ["fachler", "bhb"]}},
          "required": ["portfolio_id"]},
         READ)
    _def("portfolio_factor_exposure",
         "Portfolio exposure to named factors given caller-supplied per-symbol factor loadings.",
         portfolio_factor_exposure,
         {"type": "object", "properties": {**pid, "loadings": {"type": "object"}},
          "required": ["portfolio_id", "loadings"]},
         READ)
    _def("portfolio_hedge",
         "Propose FX hedges to flatten non-base currency exposure. Proposal only.",
         portfolio_hedge,
         {"type": "object", "properties": {
             **pid, "target_flat": {"type": "boolean"},
             "target_currency_weights": {"type": "object"}},
          "required": ["portfolio_id"]},
         READ)
    _def("portfolio_aggregate",
         "Aggregate several portfolios (by id or owner) into one combined view.",
         portfolio_aggregate,
         {"type": "object", "properties": {
             "portfolio_ids": {"type": "array", "items": {"type": "string"}},
             "owner_id": {"type": "string"}}},
         READ)


PORTFOLIO_READ_TOOLS = [
    "portfolio_list", "portfolio_get", "portfolio_calculate_pnl", "portfolio_calculate_exposure",
    "portfolio_calculate_allocation", "portfolio_calculate_risk", "portfolio_calculate_tax_lots",
    "portfolio_reconcile", "portfolio_list_reconciliations", "portfolio_attribution",
    "portfolio_factor_exposure", "portfolio_hedge", "portfolio_aggregate",
]
PORTFOLIO_WRITE_TOOLS = [
    "portfolio_create", "portfolio_add_position", "portfolio_remove_position",
    "portfolio_update_position", "portfolio_set_metadata",
    "portfolio_apply_corporate_action", "portfolio_record_swap", "portfolio_record_bridge",
    "portfolio_record_reward", "portfolio_apply_staking", "portfolio_rebuild",
    "portfolio_apply_slashing", "portfolio_record_funding",
]
PORTFOLIO_CONSEQUENTIAL_TOOLS = ["portfolio_rebalance", "portfolio_optimize"]
PORTFOLIO_TOOLS = PORTFOLIO_READ_TOOLS + PORTFOLIO_WRITE_TOOLS + PORTFOLIO_CONSEQUENTIAL_TOOLS


__all__ = ["register_portfolio_tools", "PORTFOLIO_TOOLS", "PORTFOLIO_READ_TOOLS",
           "PORTFOLIO_WRITE_TOOLS", "PORTFOLIO_CONSEQUENTIAL_TOOLS"]
