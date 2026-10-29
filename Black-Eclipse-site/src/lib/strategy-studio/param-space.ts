// ── Parameter axes ──────────────────────────────────────────────────────────
// The research panel used to ask a user to hand-write a JSON parameter space.
// This module derives the tunable axes from the spec the user already has, so a
// checkbox plus a min/max/step is enough to build `paramSpace` / `paramRanges`.
//
// It only proposes paths the engine already accepts (see `quant/params.py`):
// numeric indicator params, sizing, stop/target values and a few risk limits.
// Nothing is assumed about which axis "matters" — every axis is opt-in.

export interface ParamAxis {
  /** Dotted path into the strategy spec, e.g. `indicators.0.params.period`. */
  path: string;
  /** Human label, e.g. `ema_fast.period`. */
  label: string;
  base: number;
  integer: boolean;
  /** Suggested candidate values (derived from the base value). */
  values: number[];
  min: number;
  max: number;
  step: number;
  /** Whether this path is proposed as selected by default. */
  suggested: boolean;
}

export interface AxisRange {
  path: string;
  min: number;
  max: number;
  step: number;
  integer: boolean;
}

const INTEGER_PATH = /params\.(period|fast|slow|signal|length|lookback|window|count)$/;

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function numeric(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function round(value: number, places = 2): number {
  const factor = 10 ** places;
  return Math.round(value * factor) / factor;
}

function uniqueSorted(values: number[]): number[] {
  return [...new Set(values)].sort((a, b) => a - b);
}

/** Derive a sensible search grid around the value the user already chose. */
export function axisFromValue(path: string, label: string, base: number): ParamAxis {
  const integer = INTEGER_PATH.test(path) || path === 'risk.max_open_positions';
  if (integer) {
    const values = uniqueSorted(
      [0.5, 0.75, 1, 1.25, 1.5].map((factor) => Math.max(1, Math.round(base * factor))),
    );
    const min = values[0] ?? 1;
    const max = values[values.length - 1] ?? Math.max(1, Math.round(base));
    return {
      path,
      label,
      base,
      integer: true,
      values,
      min,
      max,
      step: 1,
      suggested: true,
    };
  }
  const values = uniqueSorted([0.75, 1, 1.25].map((factor) => round(base * factor, 4)));
  const min = values[0] ?? base;
  const max = values[values.length - 1] ?? base;
  const step = Math.max(0.01, round((max - min) / 4 || base / 10 || 0.1, 4));
  return {
    path,
    label,
    base,
    integer: false,
    values,
    min,
    max,
    step,
    suggested: true,
  };
}

function indicatorLabel(decl: Record<string, unknown>, key: string): string {
  const name = typeof decl.id === 'string' && decl.id ? decl.id : String(decl.type ?? 'indicator');
  return `${name}.${key}`;
}

/**
 * Every axis the engine can tune for this spec, in a stable order. An unknown
 * or malformed spec simply yields fewer axes — this never throws.
 */
export function deriveParamAxes(spec: Record<string, unknown> | null | undefined): ParamAxis[] {
  if (!spec) return [];
  const axes: ParamAxis[] = [];

  const indicators = Array.isArray(spec.indicators) ? spec.indicators : [];
  indicators.forEach((decl, index) => {
    if (!isRecord(decl) || !isRecord(decl.params)) return;
    for (const [key, value] of Object.entries(decl.params)) {
      if (!numeric(value)) continue;
      // Categorical / boolean-ish params are not treated as numeric axes.
      if (key === 'version') continue;
      axes.push(axisFromValue(`indicators.${index}.params.${key}`, indicatorLabel(decl, key), value));
    }
  });

  const sizing = isRecord(spec.position_sizing) ? spec.position_sizing : null;
  if (sizing && numeric(sizing.value)) {
    axes.push(axisFromValue('position_sizing.value', 'position_sizing.value', sizing.value));
  }

  const exit = isRecord(spec.rules) && isRecord(spec.rules.exit) ? spec.rules.exit : null;
  if (exit) {
    for (const key of ['stop_loss', 'take_profit', 'trailing_stop']) {
      const block = isRecord(exit[key]) ? exit[key] : null;
      if (block && numeric(block.value)) {
        axes.push(axisFromValue(`rules.exit.${key}.value`, `exit.${key}.value`, block.value));
      }
    }
  }

  const risk = isRecord(spec.risk) ? spec.risk : null;
  if (risk) {
    for (const key of ['max_position_pct', 'max_open_positions', 'max_risk_per_trade_pct']) {
      if (numeric(risk[key])) {
        axes.push(axisFromValue(`risk.${key}`, `risk.${key}`, risk[key] as number));
      }
    }
  }

  return axes;
}

/** Build the candidate list for one axis from a user-edited range. */
export function buildAxisValues(range: AxisRange, cap = 50): number[] {
  const step = Number.isFinite(range.step) && range.step > 0 ? range.step : 1;
  const low = Math.min(range.min, range.max);
  const high = Math.max(range.min, range.max);
  const out: number[] = [];
  for (let value = low; value <= high + step / 1000 && out.length < cap; value += step) {
    out.push(range.integer ? Math.round(value) : round(value, 4));
  }
  return uniqueSorted(out);
}

/** The runtime's `paramSpace` / `paramRanges` shape for the selected axes. */
export function buildParamSpace(ranges: AxisRange[]): Record<string, number[]> {
  const space: Record<string, number[]> = {};
  for (const range of ranges) {
    const values = buildAxisValues(range);
    if (values.length) space[range.path] = values;
  }
  return space;
}

/** The default selection: every derived axis at its suggested range. */
export function defaultRanges(axes: ParamAxis[]): AxisRange[] {
  return axes
    .filter((axis) => axis.suggested)
    .map((axis) => ({ path: axis.path, min: axis.min, max: axis.max, step: axis.step, integer: axis.integer }));
}

/** How many combinations the space describes (the engine's grid size). */
export function spaceSize(ranges: AxisRange[]): number {
  return ranges.reduce((total, range) => total * Math.max(1, buildAxisValues(range).length), 1);
}
