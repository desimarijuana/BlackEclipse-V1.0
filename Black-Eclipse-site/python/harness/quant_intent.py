"""Deterministic quant-intent classifier + per-run quant protocol.

Mirrors `trading_intent.py`: lexical, pure, no model call. The classifier decides
whether a turn is genuinely quantitative (analysis, forecast, strategy, model,
factor, financial model, risk) and the block appended to `runtime_context` gives
the model the appropriate working protocol.

It grants nothing. The bound tool set, permissions and effects are enforced
elsewhere; a miss only means the model keeps the generic finance guidance.

Bias: a wrong `standard`/`deep` only adds guidance and a plan event. Forcing a
model on a plain lookup is still a bad answer, so quotes, news, filings and
concept explanations stay `none`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterable, Literal, Optional

QuantTier = Literal["none", "light", "standard", "deep"]
QuantKind = Literal[
    "lookup", "analysis", "forecast", "strategy", "model",
    "financial_model", "factor", "risk", "trade",
]
Confidence = Literal["certain", "likely", "unsure"]

# A directive that asks Eclipse to construct something, rather than to look it up.
_BUILD_VERBS = (
    "build", "create", "make", "design", "train", "develop", "construct",
    "implement", "write", "code", "prototype", "set up", "assemble", "engineer",
)

# A model-shaped artifact. Specific phrases first; the bare nouns are included
# because "build a model" / "build a strategy" is exactly the demand we want to
# route to the synthesis protocol.
_MODEL_OBJECTS = (
    "quant model", "trading model", "alpha model", "factor model",
    "statistical model", "risk model", "volatility model", "predictive model",
    "forecasting model", "ml model", "machine learning model",
    "trading strategy", "quant strategy", "momentum strategy",
    "mean reversion strategy", "trading algorithm", "trading bot",
    "strategy", "factor", "alpha model", "alpha factor", "signal",
    "backtest", "pipeline", "predictor", "classifier", "forecaster", "model",
)

# A code-build task must not be mistaken for quantitative research. `alpha.py`,
# `model.py` and `print(...)` are code, not an alpha/model request; the guard
# only applies when no genuine quant term is present.
_CODE_TASK_TERMS = (
    ".py", ".ts", ".tsx", ".js", ".jsx", "def ", "print(", "function ",
    "class ", "import ", "small package", "package:",
)
_CODE_TASK_QUANT_TERMS = (
    "backtest", "quant", "forecast", "portfolio", "volatility", "drawdown",
    "monte carlo", "optimi", "alpha model", "alpha factor", "trading model",
    "quant model", "factor model", "machine learning", "predict",
)

# Distinctive quantitative vocabulary. A hit plus an analysis verb/asset/horizon
# is enough for `standard`; a build verb plus a model object is `deep`.
_STRONG_TERMS = (
    "backtest", "back-test", "backtesting", "walk-forward", "walk forward",
    "walkforward", "out-of-sample", "out of sample", "oos", "monte carlo",
    "monte-carlo", "bootstrap", "sharpe", "sortino", "calmar",
    "information ratio", "alpha", "factor", "cointegration", "stationarity",
    "autocorrelation", "regression", "volatility", "drawdown", "value at risk",
    "var", "expected shortfall", "cvar", "optimize", "optimise", "optimization",
    "parameter sweep", "robustness", "sensitivity", "regime", "quantile",
    "risk parity", "mean-variance", "mean variance", "black-litterman",
    "black litterman", "information coefficient", "feature engineering",
    "cross-validation", "cross validation", "purged", "leakage", "forecast",
    "predict", "prediction", "scenario", "simulate", "simulation",
    "stress test", "stress-test", "quant", "quantitative", "statistical",
    "signal", "model", "strategy",
)

# Validation/deep-work vocabulary. Combined with a model/strategy/factor object
# it means the user wants a real research cycle, not a one-off number.
_DEEP_TERMS = (
    "walk-forward", "walk forward", "out-of-sample", "out of sample",
    "robustness", "multiple testing", "purged", "cross-validation",
    "cross validation", "overfitting", "parameter stability", "paper trade",
    "live test", "promote", "validate the strategy", "validate the model",
    "optimize", "optimise", "parameter sweep", "sensitivity",
)

_PREDICTION_PHRASES = (
    "will rise", "will fall", "will go up", "will go down", "where will",
    "how high", "how low", "price target", "predict", "prediction", "forecast",
)

# "will gold rise tomorrow" / "what will gold do next week" are predictions
# even though the exact phrase table above does not contain them.
_PREDICTION_RE = re.compile(
    r"\bwill\s+[^.?!]{0,80}?\b(?:rise|fall|go up|go down|increase|decrease|"
    r"drop|rally|crash|climb|decline)\b"
    r"|\bwhat will\b[^.?!]{0,80}?\bdo\b",
    re.IGNORECASE,
)

_METRIC_TERMS = (
    "return", "returns", "volatility", "drawdown", "sharpe", "sortino",
    "beta", "correlation", "covariance", "var", "value at risk", "cagr",
    "max drawdown", "win rate", "profit factor", "atr", "rsi",
    "moving average", "z-score", "z score",
)

_ANALYSIS_VERBS = (
    "calculate", "compute", "analyse", "analyze", "measure", "estimate",
    "derive", "evaluate", "test", "run", "plot", "chart", "visualize",
    "visualise", "simulate", "backtest", "optimize", "optimise", "compare",
)

_ASSET_TERMS = (
    "gold", "silver", "oil", "brent", "copper", "natural gas", "xauusd",
    "xau/usd", "gc=f", "s&p", "spx", "nasdaq", "ftse", "nifty", "dax",
    "eurusd", "gbpusd", "usdjpy", "btc", "bitcoin", "eth", "ethereum",
    "portfolio", "equity", "equities", "stock", "stocks", "bond", "bonds",
    "option", "options", "future", "futures", "crypto", "forex", "fx",
    "commodity", "commodities", "index", "indices", "etf",
)

_HORIZON_TERMS = (
    "tomorrow", "next day", "1-day", "one-day", "1 day", "5-day", "five-day",
    "week", "weekly", "month", "monthly", "quarter", "quarterly", "year",
    "yearly", "intraday", "hourly", "daily", "horizon", "forward",
    "next week", "next month", "next year",
)

# Plain retrieval / explanation signals. They suppress quant mode unless a
# stronger signal is also present.
_LOOKUP_TERMS = (
    "price", "quote", "trading at", "market cap", "market capitalization",
    "p/e", "pe ratio", "earnings", "dividend", "news", "headline", "filing",
    "10-k", "10-q", "annual report", "profile", "summary", "summarize",
    "list", "show me",
)
_EXPLAIN_TERMS = (
    "explain", "what is", "what's", "what does", "how does", "how do",
    "define", "meaning of", "difference between", "teach me",
    "walk me through",
)

_FOLLOW_UPS = (
    "do it", "do that", "go ahead", "proceed", "continue", "run it",
    "run that", "yes please", "sounds good", "and then", "same for",
)

# A request to use what already exists. This is a quant turn even without a
# build verb, and the protocol tells the model to check `model_catalog`.
_REUSE_TERMS = (
    "reuse", "re-use", "use the model", "use the strategy", "use the factor",
    "existing model", "existing strategy", "existing factor", "same model",
    "last model", "previous model", "catalog", "models", "strategies",
    "experiments", "factors",
)

_TRADE_PRECEDENCE = "trade"


def _norm(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def _has(text: str, term: str) -> bool:
    """Whole-word match for bare tokens; substring for phrases/punctuation."""
    term = term.lower()
    if not term:
        return False
    if re.fullmatch(r"[a-z0-9]+", term):
        return re.search(rf"\b{re.escape(term)}\b", text) is not None
    return term in text


def _first(text: str, terms: tuple[str, ...]) -> Optional[str]:
    for term in terms:
        if _has(text, term):
            return term
    return None


def _prediction_hit(text: str) -> Optional[str]:
    hit = _first(text, _PREDICTION_PHRASES)
    if hit:
        return hit
    match = _PREDICTION_RE.search(text)
    return match.group(0) if match else None


def _history_content(turn: Any) -> tuple[str, str]:
    if isinstance(turn, dict):
        return str(turn.get("role") or ""), str(turn.get("content") or "")
    return str(getattr(turn, "role", "")), str(getattr(turn, "content", ""))


def _prior_quant_intent(history: Optional[list[Any]]) -> Optional["QuantIntent"]:
    for turn in reversed(history or []):
        role, content = _history_content(turn)
        if role != "user" or not content.strip():
            continue
        prior = classify_quant_intent(content)
        if prior.tier != "none":
            return prior
        # Only the most recent user turn matters.
        break
    return None


def _kind(text: str, *, build: bool) -> QuantKind:
    if any(_has(text, k) for k in (
        "dcf", "lbo", "three-statement", "three statement", "comps",
        "valuation model", "financial model",
    )):
        return "financial_model"
    if any(_has(text, k) for k in (
        "factor", "alpha", "information coefficient", "quantile",
    )):
        return "factor"
    if any(_has(text, k) for k in (
        "strategy", "backtest", "signal", "entry", "exit", "rules",
    )):
        return "strategy"
    if build and any(_has(text, k) for k in ("model", "train", "pipeline", "predictor")):
        return "model"
    if _prediction_hit(text):
        return "forecast"
    if any(_has(text, k) for k in (
        "risk model", "value at risk", "var", "stress test", "drawdown",
        "volatility", "expected shortfall",
    )):
        return "risk"
    if any(_has(text, k) for k in (
        "model", "train", "ml", "machine learning", "classifier", "predictor",
    )):
        return "model"
    return "analysis"


def _missing(text: str, kind: QuantKind) -> tuple[str, ...]:
    missing: list[str] = []
    if kind in ("forecast", "model", "strategy", "factor", "risk") and not _first(
        text, _ASSET_TERMS
    ):
        missing.append("instrument or universe")
    if kind in ("forecast", "strategy") and not _first(text, _HORIZON_TERMS):
        missing.append("horizon")
    return tuple(missing)


@dataclass(frozen=True)
class QuantIntent:
    """One deterministic verdict about a turn's quantitative depth."""

    tier: QuantTier
    kind: QuantKind
    confidence: Confidence = "likely"
    signals: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        """JSON-safe record for the `quant.plan` run event."""
        return {
            "tier": self.tier,
            "kind": self.kind,
            "confidence": self.confidence,
            "signals": list(self.signals),
            "reasons": list(self.reasons),
            "missing": list(self.missing),
        }


def _none(reason: str, signals: tuple[str, ...] = ()) -> QuantIntent:
    return QuantIntent(
        tier="none", kind="lookup", confidence="certain",
        signals=signals, reasons=(reason,),
    )


def classify_quant_intent(
    query: str,
    history: Optional[list[Any]] = None,
    *,
    mode: Any = None,
) -> QuantIntent:
    """Classify one user turn. `mode` is an optional override ("on"/"off")."""
    text = _norm(query)
    if not text:
        return _none("empty turn")

    # Explicit user override wins over the lexical classifier.
    forced = _norm(mode)
    if forced in ("off", "false", "0", "no"):
        return _none("quant mode explicitly off")
    force_on = forced in ("on", "true", "1", "yes", "always")

    # Execution wins: a trade/close/modify turn keeps the trade surface.
    try:
        from .trading_intent import is_trade_turn  # noqa: PLC0415

        if is_trade_turn(query):
            return QuantIntent(
                tier="none", kind="trade", confidence="certain",
                signals=("trade-intent",),
                reasons=("execution turn owns the surface",),
            )
    except Exception:  # noqa: BLE001 - classification must never break a run
        pass

    build = _first(text, _BUILD_VERBS)
    model = _first(text, _MODEL_OBJECTS)
    strong = _first(text, _STRONG_TERMS)
    deep = _first(text, _DEEP_TERMS)
    metric = _first(text, _METRIC_TERMS)
    analysis = _first(text, _ANALYSIS_VERBS)
    asset = _first(text, _ASSET_TERMS)
    horizon = _first(text, _HORIZON_TERMS)
    prediction = _prediction_hit(text)
    lookup = _first(text, _LOOKUP_TERMS)
    explain = _first(text, _EXPLAIN_TERMS)
    reuse = _first(text, _REUSE_TERMS)

    # A short follow-up ("do it", "what about silver?") inherits the prior turn.
    if not (build or strong or prediction) and text.startswith(_FOLLOW_UPS):
        prior = _prior_quant_intent(history)
        if prior is not None and prior.tier in ("standard", "deep"):
            return QuantIntent(
                tier=prior.tier, kind=prior.kind, confidence="likely",
                signals=("follow-up",), reasons=("follow-up to a quantitative turn",),
                missing=prior.missing,
            )

    signals = tuple(
        name for name, value in (
            ("build", build), ("model", model), ("strong", strong), ("deep", deep),
            ("metric", metric), ("analysis", analysis), ("asset", asset),
            ("horizon", horizon), ("prediction", prediction), ("lookup", lookup),
            ("explain", explain), ("reuse", reuse),
        ) if value
    )

    # An explanation of a concept is not a research request, even when the
    # concept is quantitative ("explain the Sharpe ratio", "how does a backtest
    # work"). A real imperative ("backtest this strategy") still gets through.
    concept_request = (
        explain is not None
        and text.startswith(("explain", "what", "how", "why", "define", "teach", "walk"))
        and not (build or prediction or asset or horizon or reuse)
        and not any(_has(text, k) for k in (
            "backtest this", "backtest my", "backtest our", "run a",
            "calculate", "compute", "analyse", "analyze", "measure",
            "estimate", "simulate",
        ))
    )
    if concept_request:
        return _none("concept explanation", signals)
    # A plain lookup stays fast unless a quantitative signal is present.
    if lookup and not (build or strong or prediction or reuse):
        return _none("plain retrieval", signals)

    # A code-build task is not quantitative research. This guard is why
    # "write alpha.py that prints ALPHA_OK" cannot lose the file tools to a
    # quant surface; a real quant term still gets through.
    if any(term in text for term in _CODE_TASK_TERMS) and not any(
        _has(text, term) for term in _CODE_TASK_QUANT_TERMS
    ):
        return _none("code task", signals)

    # A reuse/catalog request is quantitative even without a build verb: the
    # model should look up what exists before doing anything new.
    if reuse and not build and (
        model or _has(text, "catalog")
        or reuse in ("models", "strategies", "experiments", "factors")
    ):
        kind = _kind(text, build=False)
        if kind == "analysis" and (
            _has(text, "catalog")
            or reuse in ("models", "strategies", "experiments", "factors")
        ):
            kind = "model"
        return QuantIntent(
            tier="deep" if _has(text, "backtest") or deep else "standard",
            kind=kind, confidence="likely", signals=signals,
            reasons=("reuse/catalog request",),
        )

    # An explicit "act as a quant" / "use quantitative methods" is a standing
    # instruction for this turn even without a named instrument.
    if strong in ("quant", "quantitative") and not (
        build or model or deep or prediction
    ):
        kind = _kind(text, build=bool(build))
        return QuantIntent(
            tier="standard", kind=kind, confidence="likely", signals=signals,
            reasons=("explicit quantitative framing",), missing=_missing(text, kind),
        )

    # The user explicitly forced quant mode on.
    if force_on:
        kind = _kind(text, build=bool(build))
        tier: QuantTier = "deep" if build or deep else "standard"
        return QuantIntent(
            tier=tier, kind=kind, confidence="certain", signals=signals,
            reasons=("quant mode explicitly on",), missing=_missing(text, kind),
        )

    # Deep: construct/validate a real model, strategy, factor or research plan.
    if build and any(_has(text, k) for k in (
        "dcf", "lbo", "three-statement", "three statement", "comps",
        "valuation model", "financial model",
    )):
        return QuantIntent(
            tier="deep", kind="financial_model", confidence="certain",
            signals=signals, reasons=(f"build verb {build!r} + financial model",),
            missing=_missing(text, "financial_model"),
        )
    if build and (model or any(_has(text, k) for k in (
        "model", "strategy", "factor", "alpha model", "alpha factor",
        "signal", "pipeline", "algorithm", "backtest",
    ))):
        kind = _kind(text, build=True)
        return QuantIntent(
            tier="deep", kind=kind, confidence="certain", signals=signals,
            reasons=(f"build verb {build!r} + model artifact",),
            missing=_missing(text, kind),
        )
    if deep and (model or any(_has(text, k) for k in ("strategy", "factor", "model"))):
        kind = _kind(text, build=bool(build))
        return QuantIntent(
            tier="deep", kind=kind, confidence="certain", signals=signals,
            reasons=(f"validation term {deep!r} + model artifact",),
            missing=_missing(text, kind),
        )
    # "Backtest my strategy" is a full research cycle, not a single number.
    if _has(text, "backtest") and any(
        _has(text, k) for k in ("strategy", "my ", "this ", "our ")
    ):
        kind = _kind(text, build=bool(build))
        return QuantIntent(
            tier="deep", kind=kind, confidence="likely", signals=signals,
            reasons=("backtest of a named strategy",),
            missing=_missing(text, kind),
        )

    # Standard: a forecast/scenario or a multi-step quantitative question.
    if prediction and (asset or horizon or strong):
        kind = _kind(text, build=bool(build))
        return QuantIntent(
            tier="standard", kind=kind, confidence="likely", signals=signals,
            reasons=(f"prediction signal {prediction!r}",),
            missing=_missing(text, kind),
        )
    # Light: one computed metric over named data. This precedes the broader
    # `strong` branch so "calculate gold's volatility" is a single computation,
    # not a full research project.
    if metric and (analysis or asset):
        kind = _kind(text, build=False)
        return QuantIntent(
            tier="light", kind=kind, confidence="likely", signals=signals,
            reasons=(f"metric {metric!r} over named data",),
            missing=_missing(text, kind),
        )
    if strong and (analysis or asset or horizon or model):
        kind = _kind(text, build=bool(build))
        return QuantIntent(
            tier="standard", kind=kind, confidence="likely", signals=signals,
            reasons=(f"quantitative signal {strong!r}",),
            missing=_missing(text, kind),
        )

    return _none("no quantitative signal", signals)


def _has_tool(available: Optional[set[str]], name: str) -> bool:
    return available is None or name in available


def quant_intent_block(
    intent: QuantIntent,
    *,
    available: Optional[set[str]] = None,
) -> str:
    """The per-turn quant protocol, or "" when the turn is not quantitative.

    `available` is the run's bound tool names. Tool-specific lines are omitted
    when the tool is not bound, so the block never advertises an unavailable
    action.
    """
    if intent.tier == "none":
        return ""

    lines: list[str] = [
        f"# Quant protocol — {intent.tier} ({intent.kind})",
        "",
        "This turn is a quantitative request. Work as a quant researcher / quant "
        "developer: frame it, get the data, compute with tools, validate, and "
        "deliver an artifact. Do not stop at commentary.",
    ]

    if intent.kind == "financial_model":
        lines.append(
            "Build the financial model with the modelling tools and audit its "
            "inputs; a valuation is an estimate, never a reported fact."
        )
    elif intent.kind == "factor":
        lines.append(
            "Use the factor lab: definition -> evaluation -> quantile portfolio -> "
            "validation. Do not present a raw correlation as an alpha."
        )
    elif intent.kind == "strategy":
        lines.append(
            "Use the strategy engine (spec -> validate -> backtest -> costs -> "
            "walk-forward -> robustness). Do not hand-roll a backtest in prose."
        )
    elif intent.kind == "model":
        lines.append(
            "Use the ML/statistical lab or a tested capability. A model must be "
            "trained on a declared dataset, validated out-of-sample, and compared "
            "against a naive baseline."
        )
    elif intent.kind == "forecast":
        lines.append(
            "A point prediction is not defensible. Start from a naive/random-walk "
            "baseline and report a distribution or scenario band with its assumptions."
        )
    elif intent.kind == "risk":
        lines.append(
            "Use the deterministic risk/statistics tools; state the confidence "
            "level, horizon and method."
        )

    if intent.tier == "light":
        lines.extend([
            "",
            "1. Read the named series with the data tools; state provider, as-of,",
            "   interval and any gap.",
            "2. Compute with the tool (never in prose); show formula, inputs, seed",
            "   and result.",
            "3. Label the result as computed by Eclipse, not as data from a source.",
        ])
    else:
        lines.extend([
            "",
            "1. Frame it: instrument(s), venue, horizon, frequency, currency,",
            "   objective. Resolve ambiguity once; state the assumption.",
            "2. Get data: state provider, as-of, interval, adjustment and gaps.",
            "   Never proceed silently on a stale or proxy series.",
            "3. Pick the simplest defensible method. Prefer an existing model; if",
            "   none fits, compose one from the primitives or construct it.",
            "4. Compute with tools, never in prose. Show formula, inputs, seed and",
            "   output. Never invent a metric.",
            "5. Validate: in-sample vs out-of-sample/walk-forward, costs, benchmark,",
            "   sample size, multiple testing. In-sample fit is not evidence of edge.",
            "6. Deliver at least one artifact: experiment id, model id, factor id,",
            "   analysis id, chart or report. Name it.",
            "7. Caveat: label estimates and what-if; state the counter-case and what",
            "   would invalidate the view. No guaranteed return, no 'tomorrow will be X'.",
            "8. End with exactly one line: `Artifacts: <comma-separated ids>` or",
            "   `Artifacts: none — <what is missing>`. Chat is the only delivery surface.",
            "9. For gold, state the basis: spot XAUUSD vs GC=F futures; never mix them.",
        ])
        if _has_tool(available, "model_catalog"):
            lines.append(
                "Before building a new model/strategy/factor, check `model_catalog` "
                "and reuse a fitting artifact instead of rebuilding a duplicate."
            )

    if intent.tier == "deep":
        lines.extend([
            "",
            "Model synthesis: the built-in models are primitives, not a closed list.",
            "Choose the cheapest safe route: reuse a registered model/strategy/factor/"
            "recipe; configure an engine; compose primitives; one-off compute in the "
            "sandbox; build a tested reusable capability; hand off new code/tools with "
            "tests; connect an external system with operator credentials. Never "
            "self-enable an external capability.",
            "Every created model states its target, inputs, method, validation design, "
            "metrics, artifacts, limitations, reproducibility and reuse surface.",
            "Assess fitness before building: enough history, leakage risk, regime "
            "stability, sample size. If the requested model is not defensible, say so "
            "and propose the better one.",
        ])
        if _has_tool(available, "create_research_plan"):
            lines.append(
                "Write the research plan first (hypothesis, universe, period, costs, "
                "benchmark, acceptance criteria, known biases), then execute it."
            )
        if _has_tool(available, "model_catalog"):
            lines.append(
                "For a build/create request, call `model_catalog` FIRST. If a fitting "
                "strategy/model/factor exists, reuse it; do not rebuild a duplicate. "
                "If none fits, build it, then confirm the new id is registered and "
                "name it in the artifact line."
            )
        lines.append(
            "If the model family is ambiguous (valuation/DCF vs ML prediction vs "
            "trading strategy vs risk model), ask ONE clarify question with those "
            "options before building."
        )

    if intent.tier in ("standard", "deep") and intent.missing:
        lines.append(
            "Missing before a defensible answer: "
            + ", ".join(intent.missing)
            + ". Ask ONE short clarify question with concrete options; do not "
            "invent them."
        )

    lines.extend([
        "",
        "Hard rules: no look-ahead, no survivorship bias, costs always, no",
        "fabricated fills or prices, and never present a computed estimate as a",
        "reported fact.",
    ])
    return "\n".join(lines)


_QUANT_SURFACE_PREFIXES = (
    "market_", "financial_", "research_", "macro_", "history_", "backfill_",
    "portfolio_", "ml_", "stats_", "factor_", "capability_", "broker_",
    "mcp__", "plug_", "plugin_",
)
_QUANT_SURFACE_EXTRA = frozenset({
    # Data and research
    "get_quote", "get_historical_prices", "get_ohlcv", "get_volume",
    "get_orderbook", "get_trades", "get_market_cap", "get_supply",
    "get_funding_rate", "get_open_interest", "get_options_chain",
    "get_fx_rate", "get_bond_data", "get_tvl", "get_onchain_metric",
    "get_liquidations", "get_long_short_ratio", "get_market_snapshot",
    "get_fundamentals", "get_news", "get_source_health", "get_coverage",
    "get_capability_matrix", "get_research_health", "history_catalog",
    "backfill_history", "stream_market_data",
    # Compute, artifacts, synthesis and response contract
    "analysis_run", "python_chart", "eclipse_report", "clarify", "memory",
    "response_block_schema", "response_style_guide", "response_validate",
    "scaffold_kit", "financial_model_build", "financial_model_audit",
    "model_catalog",
    # Stats tools that do not share a prefix
    "run_statistical_analysis", "submit_statistical_analysis",
    "stats_capabilities", "stats_analysis_status", "stats_cancel_analysis",
    "stats_list_analyses", "stats_get_analysis", "validate_formula",
    "execute_formula",
})


@lru_cache(maxsize=1)
def _quant_surface_names() -> frozenset[str]:
    """Every engine tool name, imported lazily so a missing layer cannot break
    the classifier. The surface is a KEEP list; an import failure only means
    that layer's tools are not added."""
    names: set[str] = set()
    for module, attr in (
        (".quant.tools", "QUANT_TOOLS"),
        (".stats.tools", "STATS_TOOLS"),
        (".factors.tools", "FACTOR_TOOLS"),
        (".ml.tools", "ML_TOOLS"),
        (".market.research_tools", "RESEARCH_DATA_TOOLS"),
    ):
        try:
            mod = __import__(f"{__package__}{module}", fromlist=[attr])  # noqa: PLC0415
            names.update(getattr(mod, attr) or ())
        except Exception:  # noqa: BLE001 - an absent layer simply contributes none
            continue
    return frozenset(names)


def _is_quant_surface_tool(name: str, engine_names: frozenset[str]) -> bool:
    if name in engine_names or name in _QUANT_SURFACE_EXTRA:
        return True
    return name.startswith(_QUANT_SURFACE_PREFIXES)


def apply_quant_surface(
    query: str,
    allowed: Optional[set[str]],
    resolution: Any,
    *,
    history: Optional[list[Any]] = None,
    mode: Any = None,
) -> tuple[Optional[set[str]], Any]:
    """Narrow a quantitative turn to the data/compute/artifact surface.

    It can only REMOVE tools, and only for `standard`/`deep` turns. A lookup or a
    trade turn is untouched. The keep list is the engines' own declared names
    plus the data, research, portfolio, broker-read and response tools they need.
    """
    if not allowed:
        return allowed, resolution
    intent = classify_quant_intent(query, history, mode=mode)
    if intent.tier not in ("standard", "deep"):
        return allowed, resolution
    names = _quant_surface_names()
    kept = {name for name in allowed if _is_quant_surface_tool(name, names)}
    if len(kept) < 4 or len(kept) >= len(allowed):
        return allowed, resolution
    from dataclasses import replace  # noqa: PLC0415

    return kept, replace(
        resolution, allowed=frozenset(kept), boundTools=len(kept)
    )


def apply_intent_surfaces(
    request: Any,
    allowed: Optional[set[str]],
    resolution: Any,
) -> tuple[Optional[set[str]], Any]:
    """Apply trade precedence first, then the quant surface. Never widens."""
    from .trading_intent import apply_trade_surface  # noqa: PLC0415

    query = request.input.query
    allowed, resolution = apply_trade_surface(query, allowed, resolution)
    context = getattr(request.input, "context", None)
    mode = context.get("quantMode") if isinstance(context, dict) else None
    return apply_quant_surface(
        query, allowed, resolution,
        history=getattr(request.input, "history", None), mode=mode,
    )


_ARTIFACT_RE = re.compile(
    r"\b(?:exp|experiment|strat|strategy|model|mdl|dataset|ds|factor|fac|"
    r"feature|feat|analysis|capability|cap|artifact|art)_[A-Za-z0-9-]{4,}\b"
)
_OOS_TERMS = (
    "out-of-sample", "out of sample", "walk-forward", "walk forward", "oos",
    "holdout", "hold-out",
)
_COST_TERMS = (
    "commission", "slippage", "spread", "transaction cost", "trading cost",
    "impact cost",
)
_COMPUTE_PREFIXES = (
    "analysis_run", "run_", "plot_", "calculate_", "compute_", "ml_", "stats_",
    "factor_", "python_chart", "portfolio_", "price_option", "implied_volatility",
    "build_", "create_strategy", "compile_", "generate_", "simulate_",
    "model_catalog",
)
_VALIDATION_TOOLS = frozenset({
    "run_backtest", "run_portfolio_backtest", "run_walk_forward",
    "run_robustness_analysis", "run_out_of_sample_test", "run_bootstrap_test",
    "run_multiple_testing_diagnostics", "grade_strategy_edge",
    "ml_run_experiment", "ml_compare_models", "ml_register_model",
    "run_factor_evaluation", "validate_alpha_experiment",
    "financial_model_build", "financial_model_audit", "capability_build",
    "run_python_strategy", "run_event_driven_backtest",
})


def evaluate_quant_outcome(
    plan: Optional[dict[str, Any]],
    tool_names: Iterable[str],
    output: str,
) -> Optional[dict[str, Any]]:
    """A derived, read-only completeness check for one quant run.

    It never blocks a run and never invents a fact: it only reports which
    deliverable is missing. `complete` means the protocol's minimum was observed
    in the tool calls and the final text, not that the analysis is correct.
    """
    if not plan or plan.get("tier") not in ("light", "standard", "deep"):
        return None
    tier = str(plan.get("tier"))
    kind = str(plan.get("kind") or "analysis")
    tools = {str(name) for name in tool_names if name}
    text = str(output or "")
    lowered = text.lower()
    artifacts = sorted(set(_ARTIFACT_RE.findall(text)))[:12]
    missing: list[str] = []

    used_compute = any(
        name.startswith(_COMPUTE_PREFIXES) or name in _VALIDATION_TOOLS
        for name in tools
    )
    if not used_compute:
        missing.append("a tool-backed computation")
    if not text.strip():
        missing.append("a final answer")

    if tier in ("standard", "deep"):
        if not artifacts and not any(
            term in lowered for term in ("artifact", "chart", "report", "experiment")
        ):
            missing.append("a named artifact")
        if tier == "deep":
            if not (tools & _VALIDATION_TOOLS):
                missing.append("a validation run (backtest/walk-forward/experiment)")
            if not any(term in lowered for term in _OOS_TERMS):
                missing.append("out-of-sample evidence")
            if not any(term in lowered for term in _COST_TERMS):
                missing.append("cost evidence")

    return {
        "tier": tier,
        "kind": kind,
        "complete": not missing,
        "artifacts": artifacts,
        "toolCalls": sorted(tools)[:40],
        "missing": missing,
    }


def is_deep_quant_turn(query: str, history: Optional[list[Any]] = None) -> bool:
    """Whether this turn needs the deep research budget."""
    return classify_quant_intent(query, history).tier == "deep"


def _tool_names_from_messages(messages: Iterable[Any]) -> list[str]:
    names: list[str] = []
    for message in messages or ():
        for call in getattr(message, "tool_calls", None) or ():
            name = call.get("name") if isinstance(call, dict) else getattr(call, "name", None)
            if name:
                names.append(str(name))
        name = getattr(message, "name", None)
        if name and getattr(message, "type", "") == "tool":
            names.append(str(name))
    return names


def finalize_quant_text(
    query: str,
    history: Optional[list[Any]],
    messages: Iterable[Any],
    text: str,
) -> str:
    """Append the chat contract's honest check when a quant answer omits it.

    This never rewrites the model's facts and never invents an artifact: it only
    states that no artifact id was named and, when the run's tools/text lack
    required evidence, names what is missing. A non-quant turn is unchanged.
    """
    body = str(text or "")
    intent = classify_quant_intent(query, history)
    if intent.tier not in ("standard", "deep") or not body.strip():
        return body
    outcome = evaluate_quant_outcome(
        intent.to_dict(), _tool_names_from_messages(messages), body,
    )
    additions: list[str] = []
    if "artifacts:" not in body.lower():
        artifacts = outcome["artifacts"] if outcome else []
        if artifacts:
            additions.append(
                "Artifacts: " + ", ".join(artifacts) + " (Eclipse check)."
            )
        else:
            additions.append(
                "Artifacts: none — no artifact id was named in the answer (Eclipse check)."
            )
    if outcome is not None and not outcome["complete"]:
        remaining = [item for item in outcome["missing"] if item != "a named artifact"]
        if remaining:
            additions.append("Eclipse check: still missing " + ", ".join(remaining) + ".")
    if not additions:
        return body
    return body.rstrip() + "\n\n" + "\n".join(additions)


async def apply_quant_context(
    request: Any,
    allowed: Any,
    runtime_context: str,
    emitter: Any,
) -> str:
    """Append this turn's quant protocol and emit `quant.plan`. Never raises."""
    try:
        context = getattr(request.input, "context", None)
        mode = context.get("quantMode") if isinstance(context, dict) else None
        intent = classify_quant_intent(
            request.input.query, getattr(request.input, "history", None), mode=mode,
        )
        if intent.tier == "none":
            return runtime_context
        block = quant_intent_block(
            intent, available=set(allowed) if allowed else None,
        )
        await emitter.emit("quant.plan", intent.to_dict())
        return f"{runtime_context}\n\n{block}" if block else runtime_context
    except Exception:  # noqa: BLE001 - guidance must never break the run
        return runtime_context


__all__ = [
    "QuantIntent",
    "QuantKind",
    "QuantTier",
    "apply_intent_surfaces",
    "apply_quant_context",
    "apply_quant_surface",
    "classify_quant_intent",
    "evaluate_quant_outcome",
    "finalize_quant_text",
    "is_deep_quant_turn",
    "quant_intent_block",
]
