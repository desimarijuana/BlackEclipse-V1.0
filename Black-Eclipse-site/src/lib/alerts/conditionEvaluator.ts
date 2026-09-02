// Price & condition alert — condition evaluator (pure TS, unit-testable).
//
// A watch's `conditions` is a JSON tree identical in shape to the Fincept
// Terminal alert engine, so it stays future-portable:
//
//   leaf:  { indicator, params?, field?, offset?, operator, compareMode:
//            'value'|'indicator', value?, value2?, compareIndicator?,
//            compareParams? }
//   group: { children: [...], logic: 'AND'|'OR', negate?: bool }
//
// Every operand is read at `offset` bars-ago (0 = current sample). Crossing /
// rising / falling / == need one extra bar of history. Non-finite operands
// (NaN or ±Infinity) are treated as FAILED conditions, never silent fires.

export type AlertOperator =
  | ">"
  | "<"
  | ">="
  | "<="
  | "=="
  | "crosses_above"
  | "crosses_below"
  | "rising"
  | "falling"
  | "between";

export interface ConditionLeaf {
  indicator: string;
  params?: Record<string, number>;
  field?: string;
  offset?: number;
  operator: AlertOperator;
  compareMode: "value" | "indicator";
  value?: number;
  value2?: number;
  compareIndicator?: string;
  compareParams?: Record<string, number>;
  compareField?: string;
  compareOffset?: number;
}

export interface ConditionGroup {
  children: Array<ConditionNode>;
  logic: "AND" | "OR";
  negate?: boolean;
}

export type ConditionNode = ConditionLeaf | ConditionGroup;

/** A numeric series keyed by operand key (see operandKey below). */
export type SeriesMap = Map<string, number[]>;

export interface ConditionDetail {
  indicator: string;
  op: string;
  targetValue?: number;
  ok: boolean;
  error?: string;
}

export interface EvaluationResult {
  triggered: boolean;
  details: ConditionDetail[];
  hasError: boolean;
}

const LEVEL_TOUCH_TOLERANCE = 1e-9;
const RELATIVE_TOUCH_FRACTION = 1e-6;

export function isConditionGroup(node: ConditionNode): node is ConditionGroup {
  return Array.isArray((node as ConditionGroup).children);
}

/** Canonical series key for an operand (indicator + params + field). */
export function operandKey(
  indicator: string,
  params?: Record<string, number>,
  field?: string
): string {
  const p = params ? JSON.stringify(params, Object.keys(params).sort()) : "";
  return field ? `${indicator}(${p}).${field}` : `${indicator}(${p})`;
}

/** Reject NaN AND ±Infinity — Number.isNaN alone is NOT enough. */
function finite(v: unknown): v is number {
  return typeof v === "number" && Number.isFinite(v);
}

/**
 * Read a sample N bars back from the series. Returns NaN when there is not
 * enough history (the caller treats this as a failed / warming condition).
 */
function sample(series: number[] | undefined, offset: number): number {
  if (!series || series.length === 0) return NaN;
  const idx = series.length - 1 - offset;
  if (idx < 0) return NaN;
  return series[idx];
}

/**
 * Compare the two sides of a leaf at their offsets, returning
 * { lhs, rhs, prevLhs, prevRhs } with NaN meaning "missing history".
 */
function operands(
  leaf: ConditionLeaf,
  window: SeriesMap
): { lhs: number; rhs: number; prevLhs: number; prevRhs: number } {
  const lhsSeries = window.get(operandKey(leaf.indicator, leaf.params, leaf.field));
  const lhsOffset = leaf.offset ?? 0;
  const lhs = sample(lhsSeries, lhsOffset);
  const prevLhs = sample(lhsSeries, lhsOffset + 1);

  let rhs: number;
  let prevRhs: number;
  if (leaf.compareMode === "indicator" && leaf.compareIndicator) {
    const rhsSeries = window.get(
      operandKey(leaf.compareIndicator, leaf.compareParams, leaf.compareField)
    );
    const rhsOffset = leaf.compareOffset ?? 0;
    rhs = sample(rhsSeries, rhsOffset);
    prevRhs = sample(rhsSeries, rhsOffset + 1);
  } else {
    rhs = leaf.value ?? NaN;
    prevRhs = rhs;
  }
  return { lhs, rhs, prevLhs, prevRhs };
}

/**
 * `==` is a LEVEL-TOUCH, not float equality: a periodically-sampled price
 * almost never lands exactly on the target (280.35 → 280.45 skips 280.40).
 * Fire when |lhs-rhs| is within a small tolerance, OR the diff changed sign
 * between the previous and current sample (it passed through the level).
 */
export function levelTouch(
  lhs: number,
  rhs: number,
  prevLhs: number,
  prevRhs: number
): boolean {
  if (!finite(lhs) || !finite(rhs)) return false;
  const tol = Math.max(
    LEVEL_TOUCH_TOLERANCE,
    Math.abs(rhs) * RELATIVE_TOUCH_FRACTION
  );
  if (Math.abs(lhs - rhs) <= tol) return true;
  if (finite(prevLhs) && finite(prevRhs)) {
    const dPrev = prevLhs - prevRhs;
    const dCurr = lhs - rhs;
    return dPrev < 0 !== dCurr < 0;
  }
  return false;
}

function compareOp(
  op: AlertOperator,
  lhs: number,
  rhs: number
): boolean | null {
  switch (op) {
    case ">":
      return lhs > rhs;
    case "<":
      return lhs < rhs;
    case ">=":
      return lhs >= rhs;
    case "<=":
      return lhs <= rhs;
    default:
      return null;
  }
}

/**
 * Evaluate a single leaf against the data window. Always returns a detail;
 * non-finite operands fail the condition AND raise an error.
 */
function evaluateLeaf(leaf: ConditionLeaf, window: SeriesMap): ConditionDetail {
  const base: ConditionDetail = {
    indicator: leaf.indicator,
    op: leaf.operator,
    targetValue:
      leaf.compareMode === "indicator" ? undefined : leaf.value ?? leaf.value2,
    ok: false,
  };

  const { lhs, rhs, prevLhs, prevRhs } = operands(leaf, window);

  // NON-FINITE GUARD: !Number.isFinite rejects NaN *and* ±Infinity.
  // `Infinity > threshold` must never silently fire. Unary operators
  // (rising/falling) only consume the left-hand series, so no rhs guard.
  const unary = leaf.operator === "rising" || leaf.operator === "falling";
  if (!finite(lhs) || (!unary && !finite(rhs))) {
    return {
      ...base,
      error: "non-finite or missing operand (insufficient history?)",
    };
  }

  switch (leaf.operator) {
    case "rising": {
      base.ok = finite(prevLhs) && lhs > prevLhs;
      if (!finite(prevLhs)) {
        return { ...base, ok: false, error: "insufficient history for rising" };
      }
      return base;
    }
    case "falling": {
      base.ok = finite(prevLhs) && lhs < prevLhs;
      if (!finite(prevLhs)) {
        return { ...base, ok: false, error: "insufficient history for falling" };
      }
      return base;
    }
    case ">":
    case "<":
    case ">=":
    case "<=": {
      const r = compareOp(leaf.operator, lhs, rhs);
      return { ...base, ok: r === true };
    }
    case "==":
      return { ...base, ok: levelTouch(lhs, rhs, prevLhs, prevRhs) };
    case "crosses_above": {
      if (!finite(prevLhs) || !finite(prevRhs)) {
        return { ...base, ok: false, error: "insufficient history for cross" };
      }
      return { ...base, ok: prevLhs <= prevRhs && lhs > rhs };
    }
    case "crosses_below": {
      if (!finite(prevLhs) || !finite(prevRhs)) {
        return { ...base, ok: false, error: "insufficient history for cross" };
      }
      return { ...base, ok: prevLhs >= prevRhs && lhs < rhs };
    }
    case "rising": {
      base.ok = finite(prevLhs) && lhs > prevLhs;
      if (!finite(prevLhs)) {
        return { ...base, ok: false, error: "insufficient history for rising" };
      }
      return base;
    }
    case "falling": {
      base.ok = finite(prevLhs) && lhs < prevLhs;
      if (!finite(prevLhs)) {
        return { ...base, ok: false, error: "insufficient history for falling" };
      }
      return base;
    }
    case "between": {
      const lo = Math.min(leaf.value ?? NaN, leaf.value2 ?? NaN);
      const hi = Math.max(leaf.value ?? NaN, leaf.value2 ?? NaN);
      if (!finite(lo) || !finite(hi)) {
        return { ...base, ok: false, error: "between requires value + value2" };
      }
      return { ...base, ok: lhs >= lo && lhs <= hi, targetValue: lo };
    }
    default:
      return { ...base, error: `unknown operator: ${String(leaf.operator)}` };
  }
}

/**
 * Evaluate a condition tree. AND/OR short-circuit; nested groups recurse;
 * negate flips the group's result. `details` only contains the evaluated
 * nodes (short-circuited siblings are not evaluated).
 */
export function evaluateGroup(
  nodes: ConditionNode[],
  logic: "AND" | "OR",
  window: SeriesMap
): EvaluationResult {
  const details: ConditionDetail[] = [];
  let hasError = false;

  const evalNode = (node: ConditionNode): boolean => {
    if (isConditionGroup(node)) {
      const inner = evaluateGroup(node.children, node.logic, window);
      details.push(...inner.details);
      if (inner.hasError) hasError = true;
      return node.negate ? !inner.triggered : inner.triggered;
    }
    const d = evaluateLeaf(node, window);
    details.push(d);
    if (d.error) hasError = true;
    return d.ok;
  };

  let triggered = logic === "AND";
  for (const node of nodes) {
    const r = evalNode(node);
    if (logic === "AND") {
      if (!r) {
        triggered = false;
        break;
      }
    } else {
      if (r) {
        triggered = true;
        break;
      }
    }
  }

  return { triggered, details, hasError };
}

/** Convenience: evaluate a whole watch's tree (top-level logic wrapper). */
export function evaluateConditions(
  conditions: unknown,
  topLogic: "AND" | "OR",
  window: SeriesMap
): EvaluationResult {
  if (Array.isArray(conditions)) {
    return evaluateGroup(conditions, topLogic, window);
  }
  const node = conditions as ConditionNode;
  if (node && isConditionGroup(node)) {
    const r = evaluateGroup(node.children, node.logic, window);
    return node.negate ? { ...r, triggered: !r.triggered } : r;
  }
  return evaluateGroup([node], topLogic, window);
}

/**
 * Does this watch need candle history (SMA/EMA/RSI) rather than just the
 * snapshot quote? Snapshot-only watches skip the candle cache entirely.
 */
const SNAPSHOT_INDICATORS = new Set([
  "CLOSE",
  "OPEN",
  "HIGH",
  "LOW",
  "VOLUME",
  "CHANGE_PCT",
  "MARKET_CAP",
  "PE",
  "EPS",
  "SECTOR",
]);

export function needsCandles(conditions: unknown): boolean {
  const walk = (node: unknown): boolean => {
    if (Array.isArray(node)) return node.some(walk);
    if (!node || typeof node !== "object") return false;
    const n = node as ConditionNode;
    if (isConditionGroup(n)) return n.children.some(walk);
    return !SNAPSHOT_INDICATORS.has(String((n as ConditionLeaf).indicator));
  };
  return walk(conditions);
}

/** Human-readable "<SYMBOL> — <indicator> <op> <target>" message builder. */
export function describeFire(symbol: string, details: ConditionDetail[]): string {
  const parts = details.map((d) => {
    const target =
      d.targetValue !== undefined ? ` ${d.targetValue}` : "";
    return `${d.indicator} ${d.op}${target}`;
  });
  return `${symbol} — ${parts.join(" & ")}`;
}