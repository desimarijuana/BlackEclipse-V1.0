"""The versioned Strategy Node Registry.

Each node is a small, pure compilation unit: given its config and the values of
its resolved inputs, it emits a fragment of the canonical `StrategySpec` IR (an
indicator declaration, a rule, a sizing/stop/risk block, or a universe). The
registry is the extension seam — adding a node never touches the canvas or the
compiler.

A node declares:
  * a stable `type_id` and its own semver (`version`),
  * typed input/output ports (`series` / `number` / `rule` / `any`),
  * a config object (with defaults) and inline config validation,
  * a deterministic `compile(ctx, node, inputs)`.

Compilation is declarative and order-independent (the compiler topo-sorts), so
"create indicators first" is not a requirement — the graph expresses intent, the
compiler resolves it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from . import indicators as ind
from .graph_model import GraphNode
from .strategy import (
    CompareOp,
    Condition,
    Group,
    IndicatorDecl,
    Operand,
    PositionSizing,
    RiskRules,
    StopSpec,
    TakeProfitSpec,
    TrailingStopSpec,
)

# ── Port types ───────────────────────────────────────────────────────────────

T_SERIES = "series"
T_NUMBER = "number"
T_RULE = "rule"
T_ANY = "any"


# ── Carried values ───────────────────────────────────────────────────────────

@dataclass
class SeriesRef:
    """A reference to a price field or an indicator output key."""

    key: str


@dataclass
class Num:
    value: float


@dataclass
class Diagnostic:
    code: str
    message: str
    node_id: str = ""
    path: str = ""
    severity: str = "error"

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "nodeId": self.node_id,
                "path": self.path, "severity": self.severity}


@dataclass
class CompileContext:
    """Accumulates the IR fragments as nodes compile (the output being built)."""

    indicators: list[IndicatorDecl] = field(default_factory=list)
    refs: set[str] = field(default_factory=set)
    entry: dict[str, Group] = field(default_factory=dict)
    exit: dict[str, Group] = field(default_factory=dict)
    stop_loss: Optional[StopSpec] = None
    take_profit: Optional[TakeProfitSpec] = None
    trailing_stop: Optional[TrailingStopSpec] = None
    time_stop_bars: Optional[int] = None
    sizing: Optional[PositionSizing] = None
    risk: RiskRules = field(default_factory=RiskRules)
    symbols: list[str] = field(default_factory=list)
    asset_classes: list[str] = field(default_factory=list)
    primary_tf: str = "1d"
    confirmation_tfs: list[str] = field(default_factory=list)
    source_map: dict[str, str] = field(default_factory=dict)
    diagnostics: list[Diagnostic] = field(default_factory=list)

    def error(self, code: str, message: str, node_id: str, path: str = "") -> None:
        self.diagnostics.append(Diagnostic(code, message, node_id, path, "error"))

    def warn(self, code: str, message: str, node_id: str, path: str = "") -> None:
        self.diagnostics.append(Diagnostic(code, message, node_id, path, "warning"))

    def add_indicator(self, decl: IndicatorDecl, node_id: str, key: str) -> None:
        self.indicators.append(decl)
        self.refs.add(key)
        self.source_map[f"indicators[{decl.id or decl.type}]"] = node_id


# ── Node / port definitions ──────────────────────────────────────────────────

@dataclass
class Port:
    name: str
    type: str
    required: bool = True
    variadic: bool = False


@dataclass
class NodeDef:
    type_id: str
    version: str
    title: str
    category: str
    description: str
    inputs: list[Port] = field(default_factory=list)
    outputs: list[Port] = field(default_factory=list)
    config_schema: dict[str, Any] = field(default_factory=dict)
    defaults: dict[str, Any] = field(default_factory=dict)
    compile: Callable[[CompileContext, GraphNode, dict[str, list[Any]]], dict[str, Any]] = (
        lambda ctx, node, inputs: {}
    )

    def in_port(self, name: str) -> Optional[Port]:
        return next((p for p in self.inputs if p.name == name), None)

    def out_port(self, name: str) -> Optional[Port]:
        return next((p for p in self.outputs if p.name == name), None)

    def effective_defaults(self) -> dict[str, Any]:
        """Explicit defaults, plus any `default` declared in the config schema."""
        merged = dict(self.defaults)
        for key, field in self.config_schema.items():
            if isinstance(field, dict) and "default" in field:
                merged.setdefault(key, field["default"])
        return merged

    def describe(self) -> dict[str, Any]:
        return {
            "type": self.type_id, "version": self.version, "title": self.title,
            "category": self.category, "description": self.description,
            "inputs": [{"name": p.name, "type": p.type, "required": p.required,
                        "variadic": p.variadic} for p in self.inputs],
            "outputs": [{"name": p.name, "type": p.type} for p in self.outputs],
            "config": self.config_schema, "defaults": self.effective_defaults(),
        }


class NodeRegistry:
    """The ONE node registry. Keyed by `type_id`; carries the node semver."""

    def __init__(self) -> None:
        self._nodes: dict[str, NodeDef] = {}

    def register(self, definition: NodeDef) -> None:
        if definition.type_id in self._nodes:
            raise ValueError(f"duplicate node type {definition.type_id!r}")
        self._nodes[definition.type_id] = definition

    def get(self, type_id: str) -> Optional[NodeDef]:
        return self._nodes.get(type_id)

    def types(self) -> list[str]:
        return sorted(self._nodes)

    def all(self) -> list[NodeDef]:
        return [self._nodes[t] for t in sorted(self._nodes)]

    def describe_all(self) -> list[dict[str, Any]]:
        return [n.describe() for n in self.all()]

    @staticmethod
    def version_supported(requested: Optional[str], available: str) -> bool:
        """Same-major versions are compatible (additive node changes)."""
        if not requested:
            return True
        def major(v: str) -> Optional[int]:
            try:
                return int(str(v).split("-")[0].split("+")[0].split(".")[0])
            except ValueError:
                return None
        return major(requested) == major(available)


# ── Compile helpers ──────────────────────────────────────────────────────────

def _operand(value: Any) -> Optional[Operand]:
    if isinstance(value, SeriesRef):
        return Operand(ref=value.key)
    if isinstance(value, Num):
        return Operand(value=float(value.value))
    if isinstance(value, (int, float)):
        return Operand(value=float(value))
    return None


def _as_group(rule: Any) -> Group:
    if isinstance(rule, Group):
        return rule
    if isinstance(rule, Condition):
        return Group(combine="all", conditions=[rule])
    return Group(combine="all", conditions=[])


def _first(inputs: dict[str, list[Any]], port: str) -> Any:
    vals = inputs.get(port) or []
    return vals[0] if vals else None


# ── Built-in nodes ───────────────────────────────────────────────────────────

def _register_builtins(reg: NodeRegistry) -> None:  # noqa: C901 - flat registry
    def node(**kw: Any) -> None:
        reg.register(NodeDef(**kw))

    # ── Data / universe ──────────────────────────────────────────────────────
    def compile_universe(ctx: CompileContext, n: GraphNode, _i: Any) -> dict[str, Any]:
        cfg = n.config
        syms = cfg.get("symbols") or []
        if isinstance(syms, str):
            syms = [s for s in syms.replace(",", " ").split() if s]
        ctx.symbols = [str(s).strip().upper() for s in syms]
        ctx.asset_classes = [str(a) for a in (cfg.get("assetClasses") or [])]
        ctx.primary_tf = str(cfg.get("primary") or "1d")
        ctx.confirmation_tfs = [str(t) for t in (cfg.get("confirmation") or [])]
        ctx.source_map["universe"] = n.id
        if not ctx.symbols:
            ctx.error("EMPTY_UNIVERSE", "universe node needs at least one symbol", n.id)
        return {}

    node(type_id="data.universe", version="1.0.0", title="Universe & Timeframes",
         category="data", description="Declares the instrument universe and timeframes.",
         compile=compile_universe,
         config_schema={"symbols": {"type": "array"}, "assetClasses": {"type": "array"},
                        "primary": {"type": "string"}, "confirmation": {"type": "array"}},
         defaults={"symbols": [], "primary": "1d"})

    def compile_price(ctx: CompileContext, n: GraphNode, _i: Any) -> dict[str, Any]:
        field_name = str(n.config.get("field") or "close").lower()
        from .strategy import PRICE_FIELDS

        if field_name not in PRICE_FIELDS:
            ctx.error("BAD_PRICE_FIELD", f"unknown price field {field_name!r}", n.id)
            return {"out": SeriesRef("close")}
        return {"out": SeriesRef(field_name)}

    node(type_id="data.price", version="1.0.0", title="Price Field",
         category="data", description="A price/volume series (open/high/low/close/volume/hl2/hlc3/ohlc4).",
         outputs=[Port("out", T_SERIES)], compile=compile_price,
         config_schema={"field": {"type": "string"}}, defaults={"field": "close"})

    # ── Constants / logic primitives ─────────────────────────────────────────
    def compile_constant(_c: CompileContext, n: GraphNode, _i: Any) -> dict[str, Any]:
        return {"out": Num(float(n.config.get("value", 0.0)))}

    node(type_id="logic.constant", version="1.0.0", title="Constant",
         category="logic", description="A numeric constant.", outputs=[Port("out", T_NUMBER)],
         compile=compile_constant, config_schema={"value": {"type": "number"}},
         defaults={"value": 0})

    def _build_condition(ctx: CompileContext, n: GraphNode, inputs: dict[str, list[Any]],
                         op: CompareOp) -> dict[str, Any]:
        left = _operand(_first(inputs, "left"))
        right = _operand(_first(inputs, "right"))
        if left is None or right is None:
            ctx.error("MISSING_INPUT", f"compare node requires both inputs (op {op})", n.id)
            return {"out": Condition(left=Operand(value=0.0), op="==", right=Operand(value=0.0))}
        return {"out": Condition(left=left, op=op, right=right)}

    def compile_compare(ctx: CompileContext, n: GraphNode, inputs: dict[str, list[Any]]) -> dict:
        op = str(n.config.get("op") or ">")
        if op not in (">", ">=", "<", "<=", "==", "!="):
            ctx.error("BAD_OPERATOR", f"unsupported comparison {op!r}", n.id)
            op = ">"
        return _build_condition(ctx, n, inputs, op)  # type: ignore[arg-type]

    node(type_id="logic.compare", version="1.0.0", title="Compare",
         category="logic", description="Compares two values (> >= < <= == !=).",
         inputs=[Port("left", T_ANY), Port("right", T_ANY)], outputs=[Port("out", T_RULE)],
         compile=compile_compare,
         config_schema={"op": {"type": "string", "enum": [">", ">=", "<", "<=", "==", "!="]}},
         defaults={"op": ">"})

    def compile_cross(ctx: CompileContext, n: GraphNode, inputs: dict[str, list[Any]]) -> dict:
        direction = str(n.config.get("direction") or "above").lower()
        op: CompareOp = "cross_above" if direction in ("above", "up", "over") else "cross_below"
        return _build_condition(ctx, n, inputs, op)

    node(type_id="logic.cross", version="1.0.0", title="Cross Above/Below",
         category="logic", description="Fires on a crossing event (above/below).",
         inputs=[Port("left", T_ANY), Port("right", T_ANY)], outputs=[Port("out", T_RULE)],
         compile=compile_cross,
         config_schema={"direction": {"type": "string", "enum": ["above", "below"]}},
         defaults={"direction": "above"})

    def compile_group(_c: CompileContext, n: GraphNode, inputs: dict[str, list[Any]]) -> dict:
        combine = str(n.config.get("combine") or "all").lower()
        combine = "any" if combine in ("any", "or") else "all"
        conditions = [v for v in (inputs.get("in") or []) if isinstance(v, (Condition, Group))]
        return {"out": Group(combine=combine, conditions=conditions)}  # type: ignore[arg-type]

    node(type_id="logic.group", version="1.0.0", title="Group (AND/OR)",
         category="logic", description="Combines condition inputs with all (AND) or any (OR).",
         inputs=[Port("in", T_RULE, required=False, variadic=True)], outputs=[Port("out", T_RULE)],
         compile=compile_group,
         config_schema={"combine": {"type": "string", "enum": ["all", "any"]}},
         defaults={"combine": "all"})

    # ── Indicators ───────────────────────────────────────────────────────────
    _MULTI = {
        "bollinger": {"upper": "_upper", "middle": "_middle", "lower": "_lower"},
        "macd": {"line": "", "signal": "_signal", "hist": "_hist", "histogram": "_hist"},
        "stochastic": {"k": "_k", "d": "_d"},
        "adx": {"line": "", "plus_di": "_plus_di", "minus_di": "_minus_di"},
        "donchian": {"upper": "_upper", "middle": "_middle", "lower": "_lower"},
        "keltner": {"upper": "_upper", "middle": "_middle", "lower": "_lower"},
    }
    _DEFAULT_OUT = {"bollinger": "middle", "macd": "line", "stochastic": "k",
                    "adx": "line", "donchian": "middle", "keltner": "middle"}

    def _select_output(ctx: CompileContext, n: GraphNode, type_: str,
                       keys: list[str], sel: Optional[str]) -> str:
        if len(keys) == 1:
            return keys[0]
        mapping = _MULTI.get(type_, {})
        suffix = mapping.get((sel or _DEFAULT_OUT.get(type_) or "line").lower(), "")
        if suffix:
            for key in keys:
                if key.endswith(suffix):
                    return key
        else:  # base output = the key with no known suffix
            for key in keys:
                if not any(key.endswith(s) for s in mapping.values() if s):
                    return key
        ctx.warn("AMBIGUOUS_INDICATOR_OUTPUT",
                 f"output {sel!r} not found for {type_}; using {keys[0]!r}", n.id)
        return keys[0]

    def _make_indicator(type_: str, title: str, schema: dict[str, Any]) -> Any:
        def compile_ind(ctx: CompileContext, n: GraphNode, _i: Any) -> dict[str, Any]:
            cfg = dict(n.config)
            out_sel = cfg.pop("output", None)
            iid = cfg.pop("id", None)
            source = cfg.pop("source", None)
            params = cfg
            decl = IndicatorDecl(id=iid, type=type_, params=params, source=source)
            try:
                keys = ind.output_keys(decl.to_spec())
            except ind.IndicatorError as exc:
                ctx.error("BAD_INDICATOR", str(exc), n.id)
                return {"out": SeriesRef(f"{type_}_invalid")}
            key = _select_output(ctx, n, type_, keys, out_sel)
            ctx.add_indicator(decl, n.id, key)
            return {"out": SeriesRef(key)}

        return NodeDef(type_id=f"indicator.{type_}", version="1.0.0", title=title,
                       category="indicator", description=f"{type_.upper()} indicator.",
                       outputs=[Port("out", T_SERIES)], compile=compile_ind,
                       config_schema=schema, defaults={})

    _simple = [("sma", "SMA", 20), ("ema", "EMA", 20), ("wma", "WMA", 20), ("rma", "RMA", 14),
               ("rsi", "RSI", 14), ("atr", "ATR", 14), ("stddev", "StdDev", 20),
               ("roc", "ROC", 12), ("highest", "Highest", 20), ("lowest", "Lowest", 20),
               ("vwap", "VWAP", 20), ("mfi", "MFI", 14), ("williams_r", "Williams %R", 14),
               ("cci", "CCI", 20)]
    for type_, title, period in _simple:
        reg.register(_make_indicator(type_, title, {"period": {"type": "integer",
                                                               "default": period}}))
    reg.register(_make_indicator("obv", "OBV", {}))
    reg.register(_make_indicator("stochastic", "Stochastic",
                                 {"period": {"type": "integer", "default": 14},
                                  "d_period": {"type": "integer", "default": 3},
                                  "output": {"type": "string", "enum": ["k", "d"]}}))
    reg.register(_make_indicator("adx", "ADX",
                                 {"period": {"type": "integer", "default": 14},
                                  "output": {"type": "string",
                                             "enum": ["line", "plus_di", "minus_di"]}}))
    reg.register(_make_indicator("donchian", "Donchian Channel",
                                 {"period": {"type": "integer", "default": 20},
                                  "output": {"type": "string",
                                             "enum": ["upper", "middle", "lower"]}}))
    reg.register(_make_indicator("keltner", "Keltner Channel",
                                 {"period": {"type": "integer", "default": 20},
                                  "mult": {"type": "number", "default": 2},
                                  "atr_period": {"type": "integer", "default": 10},
                                  "output": {"type": "string",
                                             "enum": ["upper", "middle", "lower"]}}))
    reg.register(_make_indicator("bollinger", "Bollinger Bands",
                                 {"period": {"type": "integer", "default": 20},
                                  "num_std": {"type": "number", "default": 2},
                                  "output": {"type": "string",
                                             "enum": ["upper", "middle", "lower"]}}))
    reg.register(_make_indicator("macd", "MACD",
                                 {"fast": {"type": "integer", "default": 12},
                                  "slow": {"type": "integer", "default": 26},
                                  "signal": {"type": "integer", "default": 9},
                                  "output": {"type": "string", "enum": ["line", "signal", "hist"]}}))

    # ── Trading logic ────────────────────────────────────────────────────────
    def _compile_signal(ctx: CompileContext, n: GraphNode, inputs: dict[str, list[Any]],
                        bucket: str) -> dict[str, Any]:
        side = "short" if str(n.config.get("side") or "long").lower() == "short" else "long"
        rule = _first(inputs, "in")
        if not isinstance(rule, (Condition, Group)):
            ctx.error("MISSING_INPUT", f"{bucket} node needs a connected condition", n.id)
            return {}
        target = ctx.entry if bucket == "entry" else ctx.exit
        target[side] = _as_group(rule)
        ctx.source_map[f"rules.{bucket}.{side}"] = n.id
        return {}

    node(type_id="trade.entry", version="1.0.0", title="Entry",
         category="trading", description="Opens a long/short when the condition is true.",
         inputs=[Port("in", T_RULE)], compile=lambda c, n, i: _compile_signal(c, n, i, "entry"),
         config_schema={"side": {"type": "string", "enum": ["long", "short"]}},
         defaults={"side": "long"})

    node(type_id="trade.exit", version="1.0.0", title="Exit",
         category="trading", description="Closes a long/short when the condition is true.",
         inputs=[Port("in", T_RULE)], compile=lambda c, n, i: _compile_signal(c, n, i, "exit"),
         config_schema={"side": {"type": "string", "enum": ["long", "short"]}},
         defaults={"side": "long"})

    # ── Sizing ───────────────────────────────────────────────────────────────
    _SIZING_FIELDS = {"type", "value", "lookback", "atr_indicator", "atrIndicator",
                      "atr_multiplier", "atrMultiplier", "kelly_fraction", "kellyFraction",
                      "max_fraction", "maxFraction", "min_quantity", "minQuantity",
                      "lot_size", "lotSize", "quantity_precision", "quantityPrecision",
                      "contract_multiplier", "contractMultiplier"}

    def compile_sizing(ctx: CompileContext, n: GraphNode, _i: Any) -> dict[str, Any]:
        cfg = {k: v for k, v in n.config.items() if k in _SIZING_FIELDS}
        # camelCase → snake_case for the aliased fields.
        for camel, snake in (("atrIndicator", "atr_indicator"), ("atrMultiplier", "atr_multiplier"),
                             ("kellyFraction", "kelly_fraction"), ("maxFraction", "max_fraction"),
                             ("minQuantity", "min_quantity"), ("lotSize", "lot_size"),
                             ("quantityPrecision", "quantity_precision"),
                             ("contractMultiplier", "contract_multiplier")):
            if camel in cfg:
                cfg[snake] = cfg.pop(camel)
        try:
            ctx.sizing = PositionSizing.model_validate(cfg)
        except Exception as exc:  # noqa: BLE001
            ctx.error("BAD_CONFIG", f"invalid sizing config: {exc}", n.id, "position_sizing")
        ctx.source_map["position_sizing"] = n.id
        return {}

    node(type_id="sizing.position", version="1.0.0", title="Position Sizing",
         category="sizing", description="How much to trade per entry.", compile=compile_sizing,
         config_schema={"type": {"type": "string"}, "value": {"type": "number"}},
         defaults={"type": "percent_equity", "value": 90})

    # ── Stops & targets ──────────────────────────────────────────────────────
    def _stop_config(n: GraphNode) -> dict[str, Any]:
        cfg = dict(n.config)
        if "atrIndicator" in cfg:
            cfg["atr_indicator"] = cfg.pop("atrIndicator")
        return {k: v for k, v in cfg.items() if k in {"type", "value", "atr_indicator"}}

    def compile_stop_loss(ctx: CompileContext, n: GraphNode, _i: Any) -> dict[str, Any]:
        try:
            ctx.stop_loss = StopSpec.model_validate(_stop_config(n))
        except Exception as exc:  # noqa: BLE001
            ctx.error("BAD_CONFIG", f"invalid stop_loss: {exc}", n.id, "rules.exit.stop_loss")
        ctx.source_map["rules.exit.stop_loss"] = n.id
        return {}

    def compile_take_profit(ctx: CompileContext, n: GraphNode, _i: Any) -> dict[str, Any]:
        cfg = {k: v for k, v in n.config.items() if k in {"type", "value"}}
        try:
            ctx.take_profit = TakeProfitSpec.model_validate(cfg)
        except Exception as exc:  # noqa: BLE001
            ctx.error("BAD_CONFIG", f"invalid take_profit: {exc}", n.id, "rules.exit.take_profit")
        ctx.source_map["rules.exit.take_profit"] = n.id
        return {}

    def compile_trailing(ctx: CompileContext, n: GraphNode, _i: Any) -> dict[str, Any]:
        try:
            ctx.trailing_stop = TrailingStopSpec.model_validate(_stop_config(n))
        except Exception as exc:  # noqa: BLE001
            ctx.error("BAD_CONFIG", f"invalid trailing_stop: {exc}", n.id, "rules.exit.trailing_stop")
        ctx.source_map["rules.exit.trailing_stop"] = n.id
        return {}

    def compile_time_stop(ctx: CompileContext, n: GraphNode, _i: Any) -> dict[str, Any]:
        try:
            ctx.time_stop_bars = int(n.config.get("bars"))
        except (TypeError, ValueError):
            ctx.error("BAD_CONFIG", "time stop needs an integer `bars`", n.id)
        ctx.source_map["rules.exit.time_stop_bars"] = n.id
        return {}

    node(type_id="stop.loss", version="1.0.0", title="Stop Loss",
         category="risk", description="Protective stop (atr/percent/fixed).", compile=compile_stop_loss,
         config_schema={"type": {"type": "string"}, "value": {"type": "number"},
                        "atrIndicator": {"type": "string"}}, defaults={"type": "atr", "value": 2})
    node(type_id="stop.take_profit", version="1.0.0", title="Take Profit",
         category="risk", description="Profit target (risk_reward/percent/fixed).",
         compile=compile_take_profit,
         config_schema={"type": {"type": "string"}, "value": {"type": "number"}},
         defaults={"type": "risk_reward", "value": 2})
    node(type_id="stop.trailing", version="1.0.0", title="Trailing Stop",
         category="risk", description="Trailing stop (atr/percent/fixed).", compile=compile_trailing,
         config_schema={"type": {"type": "string"}, "value": {"type": "number"},
                        "atrIndicator": {"type": "string"}}, defaults={"type": "atr", "value": 3})
    node(type_id="stop.time", version="1.0.0", title="Time Stop",
         category="risk", description="Exit after N bars.", compile=compile_time_stop,
         config_schema={"bars": {"type": "integer"}}, defaults={"bars": 20})

    # ── Risk limits ──────────────────────────────────────────────────────────
    _RISK_KEYS = {"max_position_pct", "maxPositionPct", "max_gross_exposure",
                  "maxGrossExposure", "max_leverage", "maxLeverage", "max_open_positions",
                  "maxOpenPositions", "max_daily_loss_pct", "maxDailyLossPct",
                  "max_risk_per_trade_pct", "maxRiskPerTradePct", "require_stop",
                  "requireStop", "allow_long", "allowLong", "allow_short", "allowShort"}

    def compile_risk(ctx: CompileContext, n: GraphNode, _i: Any) -> dict[str, Any]:
        cfg: dict[str, Any] = {}
        for key in _RISK_KEYS:
            if key in n.config:
                snake = "".join("_" + c.lower() if c.isupper() else c for c in key)
                cfg[snake] = n.config[key]
        try:
            ctx.risk = RiskRules.model_validate(cfg)
        except Exception as exc:  # noqa: BLE001
            ctx.error("BAD_CONFIG", f"invalid risk config: {exc}", n.id, "risk")
        ctx.source_map["risk"] = n.id
        return {}

    node(type_id="risk.limits", version="1.0.0", title="Risk Limits",
         category="risk", description="Portfolio and per-position risk limits.", compile=compile_risk,
         config_schema={"maxPositionPct": {"type": "number"},
                        "maxLeverage": {"type": "number"},
                        "maxOpenPositions": {"type": "integer"},
                        "allowShort": {"type": "boolean"}}, defaults={})


def build_registry() -> NodeRegistry:
    """Construct the default registry with every built-in node."""
    reg = NodeRegistry()
    _register_builtins(reg)
    return reg


REGISTRY = build_registry()


__all__ = [
    "CompileContext",
    "Diagnostic",
    "NodeDef",
    "NodeRegistry",
    "Num",
    "Port",
    "REGISTRY",
    "SeriesRef",
    "T_ANY",
    "T_NUMBER",
    "T_RULE",
    "T_SERIES",
    "build_registry",
]
