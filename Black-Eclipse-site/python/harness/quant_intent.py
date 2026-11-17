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
    "financial_model", "factor", "risk", "trade", "discovery",
    "literature_review", "method_comparison", "method_reproduction",
    "research_discovery", "quant_model_development", "research_extension",
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

# Discovery is the core of quant mode: the user wants METHODS, not a one-off
# number and not necessarily a fully specified strategy. These phrases route to
# the method library / structure scan / hypothesis / mining protocol.
_DISCOVERY_TERMS = (
    "what methods", "which methods", "methods can i", "methods should i",
    "find a method", "find methods", "find a strategy", "find me a strategy",
    "find strategies", "what strategy", "which strategy", "give me ideas",
    "ideas for trading", "discover", "discovery", "invent",
    "new method", "new strategy", "trading ideas", "strategy ideas",
    "what works", "what should i trade", "setups", "set up now",
    "screen for", "scan for", "scan the market", "mine", "mining",
    "research ideas", "alpha ideas", "edge ideas", "generate ideas",
    "what strategies", "which strategies", "strategy library",
)

# Research-work vocabulary. These are specific phrases: a bare "research" is
# too common ("research the company"), so it only counts with a paper/literature
# object or an explicit method/research phrase.
_RESEARCH_TERMS = (
    "research paper", "research papers", "literature review", "review the literature",
    "academic", "published research", "published paper", "paper on", "papers on",
    "find papers", "find a paper", "cite", "citations", "citation", "literature",
    "survey of", "prior research", "existing research", "research the",
)
_COMPARISON_TERMS = (
    "compare methods", "compare the methods", "compare models", "method comparison",
    "compare garch", "compare the approaches", "alternatives to", "which method",
    "which model", "which approach",
)
_REPRODUCTION_TERMS = (
    "reproduce", "replicate", "replication", "implement the paper",
    "implement the methodology", "reproduce the paper", "reproduce the method",
)
_MODEL_DEV_TERMS = (
    "research-backed", "research backed", "research-driven", "research driven",
    "develop a model from research", "build a model from research",
    "research to model", "research-to-model",
)
_INDEPENDENT_TERMS = (
    "research gap", "novel hypothesis", "independent research",
    "original hypothesis", "test the hypothesis", "new hypothesis",
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


def _research_kind(text: str) -> Optional[QuantKind]:
    """The research sub-kind, or None when the turn is not research work."""
    if any(_has(text, k) for k in _INDEPENDENT_TERMS):
        return "research_extension"
    if any(_has(text, k) for k in _MODEL_DEV_TERMS):
        return "quant_model_development"
    if any(_has(text, k) for k in _REPRODUCTION_TERMS):
        return "method_reproduction"
    if any(_has(text, k) for k in _COMPARISON_TERMS):
        return "method_comparison"
    if any(_has(text, k) for k in _RESEARCH_TERMS):
        return "literature_review"
    return None


def _kind(text: str, *, build: bool) -> QuantKind:
    research = _research_kind(text)
    if research is not None:
        return research
    if any(_has(text, k) for k in _DISCOVERY_TERMS):
        return "discovery"
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
    if kind in ("forecast", "model", "strategy", "factor", "risk", "discovery") and not _first(
        text, _ASSET_TERMS
    ):
        missing.append("instrument or asset class" if kind == "discovery"
                       else "instrument or universe")
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

    discovery_hit = any(_has(text, k) for k in _DISCOVERY_TERMS)
    signals = tuple(
        name for name, value in (
            ("build", build), ("model", model), ("strong", strong), ("deep", deep),
            ("metric", metric), ("analysis", analysis), ("asset", asset),
            ("horizon", horizon), ("prediction", prediction), ("lookup", lookup),
            ("explain", explain), ("reuse", reuse), ("discovery", discovery_hit),
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

    # Research work: reading the literature, comparing methods, reproducing a
    # method, or developing a model from research. This is deliberately before
    # discovery so "research the Kalman filter" reaches the research protocol and
    # not only the internal method library.
    research = _research_kind(text)
    if research is not None:
        research_deep = (
            build is not None or deep is not None
            or research in ("method_reproduction", "quant_model_development",
                            "research_extension")
        )
        return QuantIntent(
            tier="deep" if research_deep else "standard",
            kind=research, confidence="likely", signals=signals,
            reasons=(f"research request ({research})",),
            missing=_missing(text, "model" if research != "literature_review" else "analysis"),
        )

    # Discovery: the user wants methods, ideas or setups — the core of quant
    # mode. This is deliberately before the generic build/model branches so
    # "find me a strategy" reaches the method library rather than only the spec
    # synthesizer.
    if discovery_hit:
        deep_discovery = any(_has(text, k) for k in (
            "mine", "mining", "invent", "discover", "discovery", "new method",
            "new strategy", "combinations", "scan the market", "screen for",
        ))
        return QuantIntent(
            tier="deep" if (deep_discovery or build or deep) else "standard",
            kind="discovery", confidence="likely", signals=signals,
            reasons=("method discovery request",),
            missing=_missing(text, "discovery"),
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

    if intent.kind == "literature_review":
        lines.append(
            "This is a LITERATURE / METHOD REVIEW turn. Work in this order: "
            "(a) check what already exists (`model_catalog`, `quant_list_methods`); "
            "(b) plan search topics and search the academic connectors "
            "(`research_search_papers`) — do not search one generic phrase; "
            "(c) fetch and read the accessible document (`research_get_paper`); "
            "(d) extract the method with page-level provenance "
            "(`research_extract_method`); (e) compare it with the existing catalog "
            "(`research_compare_methods`); (f) state explicitly what is established "
            "by the literature, what Eclipse inferred, and what Eclipse did not "
            "reproduce. Do not run a full model-development cycle unless asked."
        )
    elif intent.kind == "method_comparison":
        lines.append(
            "This is a METHOD COMPARISON turn. Identify the candidate methods from "
            "the literature and the internal knowledge base, extract their actual "
            "mathematics and assumptions, then compare them with an explained "
            "suitability score (`research_compare_methods`) against the user's "
            "objective, data, instrument and frequency. Print the factors and the "
            "caveats. Do not present the top score as a profit probability."
        )
    elif intent.kind == "method_reproduction":
        lines.append(
            "This is a METHOD REPRODUCTION turn. Keep two claims separate: "
            "(1) reproduction — implement the paper's procedure and compare its "
            "estimates with the published benchmark (`quant_reproduce_method`); "
            "(2) trading adaptation — apply it to the user's market, which is a "
            "different claim. Run the reproduction first, record deviations "
            "honestly, then validate the checks that are possible "
            "(`quant_validate_method`). Never call a profitable adaptation a "
            "reproduction."
        )
    elif intent.kind == "quant_model_development":
        lines.append(
            "This is a RESEARCH-TO-MODEL turn. Sequence: literature search → read "
            "and extract → compare candidates → choose a baseline and alternatives "
            "→ reproduce the chosen method → run a bounded experiment → validate "
            "(out-of-sample, costs, multiple testing, robustness) → register the "
            "method and build a Quant Research Dossier (`quant_build_dossier`). "
            "Reuse an existing model/method before building a duplicate."
        )
    elif intent.kind == "research_extension":
        lines.append(
            "This is an INDEPENDENT RESEARCH turn. First search the existing "
            "literature; an empty search is NOT evidence that a research gap "
            "exists. State the gap only if the evidence supports it. Then write "
            "competing falsifiable hypotheses, name the established methods they "
            "combine, define the data and the experiment, and report positive, "
            "negative and inconclusive results — including failed trials."
        )
    elif intent.kind == "discovery":
        lines.append(
            "This is a METHOD DISCOVERY turn. The user wants quantitative methods "
            "they can understand and trade, and potentially new ones. Work in this "
            "order:\n"
            "   a. check the method library (`list_method_families`) and recommend "
            "by asset, horizon, risk, data and regime (`recommend_methods`);\n"
            "   b. scan the actual series (`scan_market_structure`) and explain what "
            "the data looks like before proposing anything;\n"
            "   c. turn the structure into falsifiable hypotheses "
            "(`generate_method_hypotheses`) — statement, test, acceptance rule, "
            "invalidation;\n"
            "   d. synthesize a valid spec (`synthesize_method_strategy`) or compose "
            "two methods (`combine_methods`) for something new;\n"
            "   e. run a bounded search (`mine_methods`) with a real trial count and "
            "IS/OOS evidence, then the normal validation suite;\n"
            "   f. tell the user, in plain language, HOW to trade it: entry, exit, "
            "sizing, regime, what would invalidate it, and what is still unproven.\n"
            "Never present a method card, a recommendation or a mined candidate as "
            "a validated edge. Discovery produces candidates; evidence promotes them."
        )
    elif intent.kind == "financial_model":
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

    lines.extend([
        "",
        "## Visual contract (figure-first)",
        "The reader should SEE the result before reading the numbers. When the run",
        "produces a time series or a distribution, lead with the figure that answers",
        "the question and then interpret it in prose.",
    ])
    if _has_tool(available, "render_quant_figures"):
        lines.append(
            "- Use `render_quant_figures` with the experiment id. Embed the returned "
            "`chart` blocks VERBATIM inside the one `eclipse-response` document; do "
            "not retype their data and do not describe the chart in prose only."
        )
    else:
        lines.append(
            "- Emit a `chart` block (or use `python_chart` when bound) and embed it "
            "in the answer; do not describe the chart in prose only."
        )
    lines.extend([
        "- Figure budget: light = 0-1 (a single metric is a metric tile, not a",
        "  chart); standard = 1 headline + up to 2 supporting; deep = 1 headline +",
        "  up to 5 supporting, including at least one validation figure and one risk",
        "  figure.",
        "- Which figure: performance -> equity + underwater + monthly returns;",
        "  costs -> cost waterfall; concentration -> trade distribution + trades vs",
        "  holding time; risk -> exposure + rolling risk; robustness -> Monte-Carlo,",
        "  regime attribution, parameter surface; validation -> walk-forward.",
        "- A research figure needs its own source experiment: pass",
        "  `monteCarloExperimentId` (Monte-Carlo/regime),",
        "  `optimizationExperimentId` (parameter surface), or",
        "  `walkForwardExperimentId` (walk-forward). Never point a figure at an",
        "  artifact that does not contain it.",
        "- 3D is a diagnostic, not decoration. Use the parameter surface only when",
        "  two parameters genuinely vary; never use 3D for a time series, a",
        "  composition, or a third dimension the data does not measure. When the",
        "  grid is incomplete the tool falls back to a 3D point cloud and says so.",
        "- A figure that cannot be computed is an honest `unavailable` with a reason.",
        "  Never draw a decorative chart, never invent a series, and never present a",
        "  figure as evidence: every figure is computed by Eclipse.",
    ])

    if intent.tier == "light":
        lines.extend([
            "",
            "1. Read the named series with the data tools; state provider, as-of,",
            "   interval and any gap.",
            "2. Compute with the tool (never in prose); show formula, inputs, seed",
            "   and result.",
            "3. Label the result as computed by Eclipse, not as data from a source.",
            "4. If there is a series or distribution, show the one figure that makes",
            "   it legible; a lone metric stays a number, not a chart.",
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
    context = getattr(request.input, "context", None)
    # A task-dispatched turn is never a live execution turn. Its brief also
    # quotes the previous verdict, whose words ("order", "position", "open")
    # must not re-classify the run and swap its surface for the trade tools.
    task_run = bool(context.get("taskRun")) if isinstance(context, dict) else False
    if not task_run:
        allowed, resolution = apply_trade_surface(query, allowed, resolution)
    mode = context.get("quantMode") if isinstance(context, dict) else None
    return apply_quant_surface(
        query, allowed, resolution,
        history=getattr(request.input, "history", None), mode=mode,
    )


_ARTIFACT_RE = re.compile(
    r"\b(?:exp|experiment|strat|strategy|model|mdl|dataset|ds|factor|fac|"
    r"feature|feat|analysis|capability|cap|artifact|art|"
    r"dsr|dossier|lit|rep|impl|mth|method)_[A-Za-z0-9-]{4,}\b"
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
    "analysis_run", "run_", "plot_", "render_", "calculate_", "compute_", "ml_",
    "stats_", "factor_", "python_chart", "portfolio_", "price_option",
    "implied_volatility", "build_", "create_strategy", "compile_", "generate_",
    "simulate_", "model_catalog", "research_", "quant_",
)
#: Tools that produce a series or distribution worth drawing. The figure check
#: only applies when one of these ran, so "explain the Sharpe ratio" in quant
#: mode is never forced to render a chart.
_SERIES_TOOLS = frozenset({
    "run_backtest", "run_event_driven_backtest", "run_portfolio_backtest",
    "run_python_strategy", "run_walk_forward", "run_monte_carlo",
    "run_regime_monte_carlo", "optimize_parameters", "run_sensitivity_analysis",
    "run_robustness_analysis", "plot_equity_curve", "plot_drawdown",
})

#: A rendered chart block, or a tool that explicitly draws one. Prose that
#: merely contains the word "chart" does not count.
_FIGURE_MARKER = re.compile(
    r'"(?:chartType|type)"\s*:\s*"(?:chart|auto)"|"quant"\s*:\s*\{',
    re.IGNORECASE,
)

_VALIDATION_TOOLS = frozenset({
    "run_backtest", "run_portfolio_backtest", "run_walk_forward",
    "run_robustness_analysis", "run_out_of_sample_test", "run_bootstrap_test",
    "run_multiple_testing_diagnostics", "grade_strategy_edge",
    "ml_run_experiment", "ml_compare_models", "ml_register_model",
    "run_factor_evaluation", "validate_alpha_experiment",
    "financial_model_build", "financial_model_audit", "capability_build",
    "run_python_strategy", "run_event_driven_backtest",
    # Quant Research Intelligence: extraction, reproduction, validation and the
    # durable dossier are the research-cycle evidence.
    "research_extract_method", "research_compare_methods",
    "quant_reproduce_method", "quant_validate_method",
    "quant_register_method", "quant_build_dossier",
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

    # A run that produced a series should have DRAWN one. This is deliberately
    # narrower than "every quantitative turn needs a chart": a one-number answer
    # or a concept explanation is complete without a figure.
    plotted = bool(_FIGURE_MARKER.search(text)) or bool(
        tools & {"python_chart", "render_quant_figures"}
    )
    if tier in ("standard", "deep") and (tools & _SERIES_TOOLS) and not plotted:
        missing.append("a computed figure")

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
        "figures": plotted,
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
    if intent.tier not in ("light", "standard", "deep") or not body.strip():
        return body
    outcome = evaluate_quant_outcome(
        intent.to_dict(), _tool_names_from_messages(messages), body,
    )
    artifacts = outcome["artifacts"] if outcome else []
    # A light computed metric has no required artifact, but if the answer did
    # produce one (or names one), the same chat line applies.
    if intent.tier == "light" and not artifacts and "artifact" not in body.lower():
        return body
    additions: list[str] = []
    if "artifacts:" not in body.lower():
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
