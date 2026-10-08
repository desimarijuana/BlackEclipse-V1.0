"""The strategy contract.

A strategy is a **structured specification**, not arbitrary code: a declared
universe, timeframes, indicators, entry/exit rules, risk rules, position sizing
and execution assumptions. This is deliberately a data contract so it is
serializable, versionable, reproducible and safe to run deterministically — the
LLM authors/edits the spec, the engine executes it.

The rule DSL references *price fields* (`open/high/low/close/volume/hl2/hlc3/
ohlc4`) and *indicator outputs* (e.g. `ema_50`, `atr_14`, `macd_12_26_9_signal`).
Validation resolves every reference against the declared indicators, so a typo
is rejected before a single bar is processed.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Annotated, Any, Literal, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from . import indicators as ind
from .data import INTERVAL_SECONDS

# ── Rule DSL ─────────────────────────────────────────────────────────────────

CompareOp = Literal[">", ">=", "<", "<=", "==", "!=", "cross_above", "cross_below"]
PRICE_FIELDS = {"open", "high", "low", "close", "volume", "hl2", "hlc3", "ohlc4"}


class Operand(BaseModel):
    """A rule operand: either a reference (price field / indicator output) or a constant."""

    model_config = ConfigDict(populate_by_name=True)
    ref: Optional[str] = None
    value: Optional[float] = None

    @model_validator(mode="after")
    def _exactly_one(self) -> "Operand":
        if (self.ref is None) == (self.value is None):
            raise ValueError("operand needs exactly one of `ref` or `value`")
        return self


class Condition(BaseModel):
    type: Literal["condition"] = "condition"
    left: Operand
    op: CompareOp
    right: Operand


class Group(BaseModel):
    type: Literal["group"] = "group"
    combine: Literal["all", "any"] = "all"
    conditions: list["RuleNode"] = Field(default_factory=list)


RuleNode = Annotated[Union[Condition, Group], Field(discriminator="type")]
Group.model_rebuild()


# ── Exit / sizing / execution sub-models ─────────────────────────────────────

class StopSpec(BaseModel):
    type: Literal["atr", "percent", "fixed"] = "atr"
    value: float = 2.0
    atr_indicator: Optional[str] = None   # default: atr_14 if present


class TakeProfitSpec(BaseModel):
    type: Literal["risk_reward", "percent", "fixed"] = "risk_reward"
    value: float = 2.0


class TrailingStopSpec(BaseModel):
    type: Literal["atr", "percent", "fixed"] = "atr"
    value: float = 3.0
    atr_indicator: Optional[str] = None


class EntryRules(BaseModel):
    long: Optional[Group] = None
    short: Optional[Group] = None


class ExitRules(BaseModel):
    long: Optional[Group] = None       # signal-based exit for longs
    short: Optional[Group] = None
    stop_loss: Optional[StopSpec] = None
    take_profit: Optional[TakeProfitSpec] = None
    trailing_stop: Optional[TrailingStopSpec] = None
    time_stop_bars: Optional[int] = None


class Rules(BaseModel):
    entry: EntryRules = Field(default_factory=EntryRules)
    exit: ExitRules = Field(default_factory=ExitRules)


SizingType = Literal[
    "fixed_quantity", "fixed_dollar", "percent_equity", "percent_risk", "atr",
    "volatility", "kelly", "fractional_kelly", "risk_parity", "equal_weight",
]


class PositionSizing(BaseModel):
    type: SizingType = "percent_equity"
    value: float = 1.0                 # percent for percent_equity, etc.
    lookback: Optional[int] = None     # volatility window
    atr_indicator: Optional[str] = None
    atr_multiplier: float = 1.0
    kelly_fraction: Optional[float] = 0.5
    max_fraction: Optional[float] = 1.0
    # Exchange/venue constraints.
    min_quantity: float = 0.0
    lot_size: float = 0.0              # 0 = no lot increment
    quantity_precision: Optional[int] = None
    contract_multiplier: float = 1.0


class CommissionModel(BaseModel):
    type: Literal["none", "fixed", "percentage", "per_share", "per_contract", "tiered"] = "none"
    value: float = 0.0                 # per-trade (fixed), percent, or per-unit
    minimum: Optional[float] = None
    # Marginal tiers for `tiered`: each `{"upTo": notional, "rate": percent}`.
    tiers: Optional[list[dict[str, float]]] = None
    contract_multiplier: float = 1.0   # for futures/options (per_contract)


class SlippageModel(BaseModel):
    type: Literal["none", "fixed", "percentage", "volatility", "volume", "randomized"] = "none"
    value: float = 0.0
    # randomized
    seed: Optional[int] = None
    max_ticks: Optional[float] = None
    tick_size: Optional[float] = None


class SpreadModel(BaseModel):
    type: Literal["none", "fixed", "percentage", "bps", "historical"] = "none"
    value: float = 0.0


class MarketImpactModel(BaseModel):
    type: Literal["none", "linear"] = "none"
    coefficient: float = 0.0           # impact in bps per 1% of average volume


class ExecutionAssumptions(BaseModel):
    commission: CommissionModel = Field(default_factory=CommissionModel)
    slippage: SlippageModel = Field(default_factory=SlippageModel)
    spread: SpreadModel = Field(default_factory=SpreadModel)
    market_impact: MarketImpactModel = Field(default_factory=MarketImpactModel)
    latency_bars: int = 0
    fill_at: Literal["next_open", "close"] = "next_open"

    def is_frictionless(self) -> bool:
        return (
            self.commission.type == "none" and self.slippage.type == "none"
            and self.spread.type == "none" and self.market_impact.type == "none"
        )


class RiskRules(BaseModel):
    max_position_pct: Optional[float] = None       # per-position, % of equity
    max_gross_exposure: Optional[float] = None     # × equity (1.0 = no leverage)
    max_leverage: Optional[float] = None
    max_open_positions: Optional[int] = None
    max_daily_loss_pct: Optional[float] = None
    max_risk_per_trade_pct: Optional[float] = None
    require_stop: bool = False
    allow_long: bool = True
    allow_short: bool = True


class Universe(BaseModel):
    asset_classes: list[str] = Field(default_factory=list)
    symbols: list[str] = Field(default_factory=list)

    @field_validator("symbols")
    @classmethod
    def _clean_symbols(cls, v: list[str]) -> list[str]:
        out = [s.strip().upper() for s in v if s and str(s).strip()]
        if len(set(out)) != len(out):
            raise ValueError("duplicate symbols in universe")
        return out


class Timeframes(BaseModel):
    primary: str = "1d"
    confirmation: list[str] = Field(default_factory=list)

    @field_validator("confirmation")
    @classmethod
    def _dedupe(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for tf in v:
            if tf not in out:
                out.append(tf)
        return out


class IndicatorDecl(BaseModel):
    id: Optional[str] = None
    type: str
    params: dict[str, Any] = Field(default_factory=dict)
    source: Optional[str] = None
    timeframe: Optional[str] = None

    def to_spec(self) -> ind.IndicatorSpec:
        return ind.IndicatorSpec(type=self.type, params=dict(self.params), id=self.id,
                                 source=self.source)


class StrategySpec(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    name: str
    description: str = ""
    version: str = "1.0.0"
    asset_class: Optional[str] = None
    universe: Universe
    timeframes: Timeframes = Field(default_factory=Timeframes)
    indicators: list[IndicatorDecl] = Field(default_factory=list)
    rules: Rules = Field(default_factory=Rules)
    risk: RiskRules = Field(default_factory=RiskRules)
    position_sizing: PositionSizing = Field(default_factory=PositionSizing)
    execution: ExecutionAssumptions = Field(default_factory=ExecutionAssumptions)
    metadata: dict[str, Any] = Field(default_factory=dict)

    # ── Serialization ────────────────────────────────────────────────────────
    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, sort_keys=False)

    def to_yaml(self) -> str:
        return yaml.safe_dump(self.to_dict(), sort_keys=False)


# ── Normalization (accept the YAML shorthand) ────────────────────────────────

_DECL_KEYS = {"id", "type", "params", "source", "timeframe"}


def _split_decl(entry: dict[str, Any]) -> dict[str, Any]:
    """Split a flat indicator declaration into {id,type,params,source,timeframe}.

    Keys the schema does not own (`period`, `fast`, ...) become `params`, so
    both `{type: ema, period: 50}` and `{type: ema, params: {period: 50}}` work.
    """
    decl: dict[str, Any] = {}
    params: dict[str, Any] = dict(entry.get("params") or {})
    for key, val in entry.items():
        if key in _DECL_KEYS:
            decl[key] = val
        else:
            params[key] = val
    if params:
        decl["params"] = params
    return decl


def _normalize_indicators(raw: Any) -> list[dict[str, Any]]:
    """Accept either a list of indicator declarations, or the map shorthand:

        indicators:
          ema:
            - period: 50
            - period: 200
    """
    if raw is None:
        return []
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, str):
                out.append({"type": item})
            elif isinstance(item, dict):
                out.append(_split_decl(item))
        return out
    if isinstance(raw, dict):
        out = []
        for itype, val in raw.items():
            entries = val if isinstance(val, list) else [val]
            for entry in entries:
                if isinstance(entry, dict):
                    merged = {"type": itype, **entry}
                    out.append(_split_decl(merged))
                elif entry is None:
                    out.append({"type": itype})
                else:
                    out.append({"type": itype, "params": {"period": entry}})
        return out
    raise ValueError("indicators must be a list or a mapping")


def _normalize_rule_node(node: Any) -> Any:
    """Inject the `type` discriminator so the YAML shorthand validates.

    A bare list of conditions is an implicit `all` group; a dict with
    left/op/right is a condition; a dict with combine/conditions is a group.
    Nested nodes are normalized recursively.
    """
    if isinstance(node, list):
        return {"type": "group", "combine": "all",
                "conditions": [_normalize_rule_node(c) for c in node]}
    if not isinstance(node, dict):
        return node
    if "type" not in node:
        if "conditions" in node or "combine" in node:
            node = {"type": "group", **node}
        elif "left" in node or "op" in node or "right" in node:
            node = {"type": "condition", **node}
    if node.get("type") == "group":
        node["conditions"] = [_normalize_rule_node(c) for c in node.get("conditions", [])]
    return node


def _normalize_rules(rules: Any) -> Any:
    if not isinstance(rules, dict):
        return rules
    out = dict(rules)
    for section in ("entry", "exit"):
        sec = out.get(section)
        if isinstance(sec, dict):
            sec = dict(sec)
            for side in ("long", "short"):
                if sec.get(side) is not None:
                    sec[side] = _normalize_rule_node(sec[side])
            out[section] = sec
    return out


def parse_strategy(source: Union[str, dict[str, Any]]) -> StrategySpec:
    """Parse a strategy from YAML/JSON text or a dict, normalizing shorthands.

    Accepts the mission's document shape, where identity lives under a
    top-level `strategy:` block and the rest (universe, timeframes, indicators,
    rules, ...) is top-level; the two are merged.
    """
    if isinstance(source, str):
        text = source.strip()
        if text.startswith("{"):
            data = json.loads(text)
        else:
            data = yaml.safe_load(text)
    else:
        data = dict(source)
    if not isinstance(data, dict):
        raise ValueError("strategy must be an object")
    if isinstance(data.get("strategy"), dict):
        identity = dict(data.pop("strategy"))
        identity.update(data)
        data = identity
    if "indicators" in data:
        data["indicators"] = _normalize_indicators(data["indicators"])
    if "rules" in data:
        data["rules"] = _normalize_rules(data["rules"])
    # `risk.position_sizing` shorthand from the mission example.
    risk = data.get("risk")
    if isinstance(risk, dict) and "position_sizing" in risk and "position_sizing" not in data:
        data["position_sizing"] = risk.pop("position_sizing")
    return StrategySpec.model_validate(data)


# ── Validation ───────────────────────────────────────────────────────────────

@dataclass
class ValidationIssue:
    code: str
    message: str
    path: str = ""
    severity: Literal["error", "warning"] = "error"

    def to_dict(self) -> dict[str, Any]:
        return {"code": self.code, "message": self.message, "path": self.path,
                "severity": self.severity}


SUPPORTED_ASSET_CLASSES = {
    "equity", "etf", "fund", "crypto", "fx", "commodity", "index",
    "future", "option", "bond", "macro",
}


def _collect_operands(node: RuleNode, path: str, out: list[tuple[str, Operand]]) -> None:
    if isinstance(node, Condition):
        out.append((f"{path}.left", node.left))
        out.append((f"{path}.right", node.right))
    else:
        for i, child in enumerate(node.conditions):
            _collect_operands(child, f"{path}[{i}]", out)


def _validate_group(node: RuleNode, path: str, known_refs: set[str],
                    issues: list[ValidationIssue]) -> None:
    operands: list[tuple[str, Operand]] = []
    _collect_operands(node, path, operands)
    for opath, operand in operands:
        if operand.ref is None:
            continue
        ref = operand.ref.strip()
        if ref.lower() in PRICE_FIELDS or ref in known_refs:
            continue
        issues.append(ValidationIssue(
            "UNKNOWN_REFERENCE",
            f"unknown reference {ref!r}; known: {sorted(known_refs)} + price fields",
            opath,
        ))


def validate_strategy(spec: StrategySpec) -> list[ValidationIssue]:
    """Return every validation issue (never raises). Empty list = valid."""
    issues: list[ValidationIssue] = []

    if not spec.id or not spec.id.strip():
        issues.append(ValidationIssue("MISSING_ID", "strategy id is required", "id"))
    if not spec.name or not spec.name.strip():
        issues.append(ValidationIssue("MISSING_NAME", "strategy name is required", "name"))
    if spec.asset_class and spec.asset_class not in SUPPORTED_ASSET_CLASSES:
        issues.append(ValidationIssue(
            "UNSUPPORTED_ASSET_CLASS",
            f"asset_class {spec.asset_class!r} is not supported",
            "asset_class",
        ))
    if not spec.universe.symbols:
        issues.append(ValidationIssue("EMPTY_UNIVERSE", "at least one symbol is required",
                                      "universe.symbols"))
    if spec.timeframes.primary not in INTERVAL_SECONDS:
        issues.append(ValidationIssue(
            "BAD_PRIMARY_TIMEFRAME",
            f"primary timeframe {spec.timeframes.primary!r} is not supported",
            "timeframes.primary",
        ))
    for tf in spec.timeframes.confirmation:
        if tf not in INTERVAL_SECONDS:
            issues.append(ValidationIssue("BAD_TIMEFRAME", f"unsupported timeframe {tf!r}",
                                          "timeframes.confirmation"))
        elif (spec.timeframes.primary in INTERVAL_SECONDS
              and INTERVAL_SECONDS[tf] <= INTERVAL_SECONDS[spec.timeframes.primary]):
            issues.append(ValidationIssue(
                "CONFIRMATION_NOT_HIGHER",
                f"confirmation timeframe {tf!r} must be higher than primary "
                f"{spec.timeframes.primary!r}",
                "timeframes.confirmation",
            ))

    # Indicators + their output keys.
    known_refs: set[str] = set()
    seen_ids: set[str] = set()
    for i, decl in enumerate(spec.indicators):
        path = f"indicators[{i}]"
        try:
            ind.resolve_spec(decl.to_spec())
        except ind.IndicatorError as exc:
            issues.append(ValidationIssue("BAD_INDICATOR", str(exc), path))
            continue
        rid = decl.id or decl.to_spec().resolved_id()
        if decl.id:
            if decl.id in seen_ids:
                issues.append(ValidationIssue("DUPLICATE_INDICATOR_ID",
                                              f"duplicate indicator id {decl.id!r}", path))
            seen_ids.add(decl.id)
        for key in ind.output_keys(decl.to_spec()):
            if key in known_refs:
                issues.append(ValidationIssue("DUPLICATE_INDICATOR_OUTPUT",
                                              f"indicator output {key!r} declared twice", path))
            known_refs.add(key)
        # Require an explicit id when a custom source/params make the key opaque.
        if rid not in known_refs and not any(k.startswith(rid) for k in known_refs):
            known_refs.add(rid)

    # Rules.
    rules = spec.rules
    if rules.entry.long is None and rules.entry.short is None:
        issues.append(ValidationIssue("NO_ENTRY_RULES",
                                      "at least one of entry.long / entry.short is required",
                                      "rules.entry"))
    if rules.entry.long is not None:
        _validate_group(rules.entry.long, "rules.entry.long", known_refs, issues)
    if rules.entry.short is not None:
        _validate_group(rules.entry.short, "rules.entry.short", known_refs, issues)
    if rules.exit.long is not None:
        _validate_group(rules.exit.long, "rules.exit.long", known_refs, issues)
    if rules.exit.short is not None:
        _validate_group(rules.exit.short, "rules.exit.short", known_refs, issues)

    for name, sl in (("stop_loss", rules.exit.stop_loss),
                     ("trailing_stop", rules.exit.trailing_stop)):
        if sl is not None:
            if sl.value <= 0:
                issues.append(ValidationIssue("BAD_STOP_VALUE",
                                              f"{name}.value must be > 0", f"rules.exit.{name}"))
            if sl.type == "atr" and sl.atr_indicator and sl.atr_indicator not in known_refs:
                issues.append(ValidationIssue("UNKNOWN_ATR_INDICATOR",
                                              f"{sl.atr_indicator!r} is not a declared indicator",
                                              f"rules.exit.{name}.atr_indicator"))
    if rules.exit.take_profit is not None and rules.exit.take_profit.value <= 0:
        issues.append(ValidationIssue("BAD_TAKE_PROFIT",
                                      "take_profit.value must be > 0", "rules.exit.take_profit"))
    if rules.exit.time_stop_bars is not None and rules.exit.time_stop_bars <= 0:
        issues.append(ValidationIssue("BAD_TIME_STOP", "time_stop_bars must be > 0",
                                      "rules.exit.time_stop_bars"))

    # Sizing.
    ps = spec.position_sizing
    required_value = ps.type not in ("equal_weight", "risk_parity")
    if required_value and (ps.value is None or ps.value <= 0):
        issues.append(ValidationIssue("BAD_SIZING_VALUE",
                                      f"position_sizing.value must be > 0 for {ps.type!r}",
                                      "position_sizing.value"))
    if ps.type in ("percent_equity",) and ps.value and ps.value > 100:
        issues.append(ValidationIssue("SIZING_OVER_100",
                                      "percent_equity above 100 implies leverage; "
                                      "set risk.max_leverage explicitly", "position_sizing.value",
                                      severity="warning"))
    if ps.type == "atr" and ps.atr_indicator and ps.atr_indicator not in known_refs:
        issues.append(ValidationIssue("UNKNOWN_ATR_INDICATOR",
                                      f"{ps.atr_indicator!r} is not a declared indicator",
                                      "position_sizing.atr_indicator"))

    # Risk coherence.
    r = spec.risk
    if not r.allow_long and not r.allow_short:
        issues.append(ValidationIssue("NO_SIDE_ALLOWED",
                                      "allow_long and allow_short cannot both be false", "risk"))
    if r.max_position_pct is not None and r.max_position_pct <= 0:
        issues.append(ValidationIssue("BAD_RISK", "max_position_pct must be > 0",
                                      "risk.max_position_pct"))
    if r.max_leverage is not None and r.max_leverage <= 0:
        issues.append(ValidationIssue("BAD_RISK", "max_leverage must be > 0", "risk.max_leverage"))
    if r.max_gross_exposure is not None and r.max_leverage is not None \
            and r.max_gross_exposure > r.max_leverage:
        issues.append(ValidationIssue("RISK_INCONSISTENT",
                                      "max_gross_exposure exceeds max_leverage", "risk"))
    if r.require_stop and rules.exit.stop_loss is None and rules.exit.trailing_stop is None:
        issues.append(ValidationIssue("STOP_REQUIRED",
                                      "risk.require_stop is set but no stop is configured",
                                      "risk.require_stop"))

    # Execution.
    if spec.execution.latency_bars < 0:
        issues.append(ValidationIssue("BAD_LATENCY", "latency_bars cannot be negative",
                                      "execution.latency_bars"))
    return issues


def errors_only(issues: list[ValidationIssue]) -> list[ValidationIssue]:
    return [i for i in issues if i.severity == "error"]


# ── Version helpers ──────────────────────────────────────────────────────────

VersionPart = Literal["major", "minor", "patch"]


def parse_semver(version: str) -> tuple[int, int, int]:
    core = str(version).split("-")[0].split("+")[0]
    parts = core.split(".")
    while len(parts) < 3:
        parts.append("0")
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except ValueError as exc:
        raise ValueError(f"invalid semver {version!r}") from exc


def bump_version(version: str, part: VersionPart = "patch") -> str:
    major, minor, patch = parse_semver(version)
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


__all__ = [
    "CommissionModel",
    "Condition",
    "EntryRules",
    "ExecutionAssumptions",
    "ExitRules",
    "Group",
    "IndicatorDecl",
    "MarketImpactModel",
    "PositionSizing",
    "RiskRules",
    "RuleNode",
    "Rules",
    "SizingType",
    "SlippageModel",
    "SpreadModel",
    "StopSpec",
    "StrategySpec",
    "TakeProfitSpec",
    "Timeframes",
    "TrailingStopSpec",
    "Universe",
    "ValidationIssue",
    "bump_version",
    "errors_only",
    "parse_semver",
    "parse_strategy",
    "validate_strategy",
]
