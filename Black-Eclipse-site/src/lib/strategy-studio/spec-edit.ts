// ── Spec editing (the no-code builder's model) ──────────────────────────────
// The builder is a VIEW over the same JSON the editor holds. Every function here
// takes a spec, deep-clones it, and returns a new spec — the original is never
// mutated. Unknown fields are preserved so a template or a hand-written spec
// survives a round-trip through the form.
//
// The builder only understands the FLAT rule shape it can render honestly: a
// group of `{ref|value} op {ref|value}` conditions. A nested group or an
// expression operand is reported as `advanced` and left untouched, so the UI can
// say "edit this part in JSON" instead of silently rewriting it.

export const PRICE_FIELDS = ['open', 'high', 'low', 'close', 'volume', 'hl2', 'hlc3', 'ohlc4'] as const;

export const OPERATORS = [
  '>',
  '>=',
  '<',
  '<=',
  '==',
  '!=',
  'cross_above',
  'cross_below',
] as const;

export type Operator = (typeof OPERATORS)[number];
export type GroupPath = 'rules.entry.long' | 'rules.entry.short' | 'rules.exit.long' | 'rules.exit.short';

export interface FlatCondition {
  advanced: boolean;
  leftRef: string | null;
  op: string;
  rightKind: 'ref' | 'value';
  rightRef: string | null;
  rightValue: number;
  raw: unknown;
}

export interface GroupView {
  combine: 'all' | 'any';
  conditions: FlatCondition[];
  advanced: boolean;
  missing: boolean;
}

export interface IndicatorView {
  index: number;
  id: string;
  type: string;
  params: Array<{ key: string; value: number }>;
}

export interface SpecBasics {
  indicators: IndicatorView[];
  stop: { type: string; value: number } | null;
  target: { type: string; value: number } | null;
  sizing: { type: string; value: number };
  risk: {
    maxPositionPct: number | null;
    maxOpenPositions: number | null;
    allowLong: boolean;
    allowShort: boolean;
  };
  costs: { commission: number; slippage: number; spread: number; fillAt: string };
}

function clone(spec: Record<string, unknown>): Record<string, unknown> {
  return JSON.parse(JSON.stringify(spec)) as Record<string, unknown>;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value);
}

function readPath(root: Record<string, unknown>, path: string): unknown {
  let current: unknown = root;
  for (const token of path.split('.')) {
    if (!isRecord(current) && !Array.isArray(current)) return undefined;
    current = (current as Record<string, unknown>)[token];
  }
  return current;
}

function writePath(root: Record<string, unknown>, path: string, value: unknown): void {
  const tokens = path.split('.');
  let current: Record<string, unknown> = root;
  for (let index = 0; index < tokens.length - 1; index += 1) {
    const token = tokens[index];
    const next = current[token];
    if (!isRecord(next)) current[token] = {};
    current = current[token] as Record<string, unknown>;
  }
  current[tokens[tokens.length - 1]] = value;
}

function asRef(operand: unknown): string | null {
  if (!isRecord(operand)) return null;
  const keys = Object.keys(operand);
  if (keys.length === 1 && typeof operand.ref === 'string') return operand.ref;
  return null;
}

function asValue(operand: unknown): number | null {
  if (!isRecord(operand)) return null;
  const keys = Object.keys(operand);
  if (keys.length === 1 && typeof operand.value === 'number' && Number.isFinite(operand.value)) {
    return operand.value;
  }
  return null;
}

/** Flatten one rule node into the row shape, or mark it advanced. */
export function flattenCondition(node: unknown): FlatCondition {
  const record = isRecord(node) ? node : {};
  const type = record.type ?? 'condition';
  const leftRef = asRef(record.left);
  const rightRef = asRef(record.right);
  const rightValue = asValue(record.right);
  const op = typeof record.op === 'string' ? record.op : '>';
  const advanced =
    type !== 'condition' || leftRef === null || (rightRef === null && rightValue === null);
  return {
    advanced,
    leftRef,
    op,
    rightKind: rightRef !== null ? 'ref' : 'value',
    rightRef,
    rightValue: rightValue ?? 0,
    raw: node,
  };
}

export function toConditionNode(condition: FlatCondition): Record<string, unknown> {
  const left = condition.leftRef ? { ref: condition.leftRef } : null;
  const right =
    condition.rightKind === 'ref'
      ? condition.rightRef
        ? { ref: condition.rightRef }
        : null
      : { value: condition.rightValue };
  return { type: 'condition', left, op: condition.op, right };
}

/** The indicator ids a condition may reference. */
export function indicatorRefs(spec: Record<string, unknown>): string[] {
  const indicators = Array.isArray(spec.indicators) ? spec.indicators : [];
  return indicators
    .map((decl) => (isRecord(decl) && typeof decl.id === 'string' ? decl.id : null))
    .filter((id): id is string => Boolean(id));
}

/** Every operand a condition may reference (price fields first). */
export function availableRefs(spec: Record<string, unknown>): string[] {
  return [...PRICE_FIELDS, ...indicatorRefs(spec)];
}

export function readGroup(spec: Record<string, unknown>, path: GroupPath): GroupView {
  const group = readPath(spec, path);
  if (!isRecord(group)) {
    return { combine: 'all', conditions: [], advanced: false, missing: true };
  }
  const raw = Array.isArray(group.conditions) ? group.conditions : [];
  const conditions = raw.map(flattenCondition);
  return {
    combine: group.combine === 'any' ? 'any' : 'all',
    conditions,
    advanced: conditions.some((condition) => condition.advanced),
    missing: false,
  };
}

function writeGroup(spec: Record<string, unknown>, path: GroupPath, view: GroupView): Record<string, unknown> {
  const next = clone(spec);
  writePath(next, path, {
    type: 'group',
    combine: view.combine,
    conditions: view.conditions.map((condition) =>
      condition.advanced ? condition.raw : toConditionNode(condition),
    ),
  });
  return next;
}

export function addCondition(
  spec: Record<string, unknown>,
  path: GroupPath,
  condition: Partial<FlatCondition> = {},
): Record<string, unknown> {
  const view = readGroup(spec, path);
  const refs = availableRefs(spec);
  view.conditions.push({
    advanced: false,
    leftRef: condition.leftRef ?? refs[0] ?? 'close',
    op: condition.op ?? '>',
    rightKind: condition.rightKind ?? 'value',
    rightRef: condition.rightRef ?? refs[1] ?? refs[0] ?? 'close',
    rightValue: condition.rightValue ?? 0,
    raw: null,
  });
  return writeGroup(spec, path, view);
}

export function updateCondition(
  spec: Record<string, unknown>,
  path: GroupPath,
  index: number,
  patch: Partial<FlatCondition>,
): Record<string, unknown> {
  const view = readGroup(spec, path);
  const current = view.conditions[index];
  if (!current || current.advanced) return spec;
  view.conditions[index] = { ...current, ...patch };
  return writeGroup(spec, path, view);
}

export function removeCondition(
  spec: Record<string, unknown>,
  path: GroupPath,
  index: number,
): Record<string, unknown> {
  const view = readGroup(spec, path);
  if (!view.conditions[index]) return spec;
  view.conditions.splice(index, 1);
  return writeGroup(spec, path, view);
}

export function setCombine(
  spec: Record<string, unknown>,
  path: GroupPath,
  combine: 'all' | 'any',
): Record<string, unknown> {
  const view = readGroup(spec, path);
  view.combine = combine;
  return writeGroup(spec, path, view);
}

// ── Tree view (nested groups) ────────────────────────────────────────────────
// The flat view above is a convenience; the builder uses this tree so a group
// can contain groups. `path` is the list of `conditions` indices from the root
// group ([] = the root itself).

export interface TreeNodeView {
  index: number;
  path: number[];
  condition: FlatCondition | null;
  group: {
    combine: 'all' | 'any';
    children: TreeNodeView[];
    advanced: boolean;
  } | null;
}

export interface RuleTree {
  combine: 'all' | 'any';
  children: TreeNodeView[];
  missing: boolean;
  advanced: boolean;
}

function isGroupNode(node: unknown): node is Record<string, unknown> {
  return isRecord(node) && (node.type === 'group' || Array.isArray(node.conditions));
}

function readTreeNodes(raw: unknown[], basePath: number[]): TreeNodeView[] {
  return raw.map((node, index) => {
    const path = [...basePath, index];
    if (isGroupNode(node)) {
      const children = readTreeNodes(Array.isArray(node.conditions) ? node.conditions : [], path);
      return {
        index,
        path,
        condition: null,
        group: {
          combine: node.combine === 'any' ? 'any' : 'all',
          children,
          advanced: children.some((child) => child.condition?.advanced || child.group?.advanced),
        },
      };
    }
    return { index, path, condition: flattenCondition(node), group: null };
  });
}

export function readTree(spec: Record<string, unknown>, groupPath: GroupPath): RuleTree {
  const group = readPath(spec, groupPath);
  if (!isRecord(group)) {
    return { combine: 'all', children: [], missing: true, advanced: false };
  }
  const children = readTreeNodes(Array.isArray(group.conditions) ? group.conditions : [], []);
  return {
    combine: group.combine === 'any' ? 'any' : 'all',
    children,
    missing: false,
    advanced: children.some((child) => child.condition?.advanced || child.group?.advanced),
  };
}

function cloneAndGroup(
  spec: Record<string, unknown>,
  groupPath: GroupPath,
): { next: Record<string, unknown>; group: Record<string, unknown> } | null {
  const next = clone(spec);
  const group = readPath(next, groupPath);
  if (!isRecord(group)) return null;
  return { next, group };
}

function descend(group: Record<string, unknown>, path: number[]): Record<string, unknown> | null {
  let current: Record<string, unknown> = group;
  for (const index of path) {
    const children = current.conditions;
    if (!Array.isArray(children)) return null;
    const child = children[index];
    if (!isRecord(child)) return null;
    current = child;
  }
  return current;
}

/** Add a condition or a nested group inside the group at `path`. */
export function addTreeNode(
  spec: Record<string, unknown>,
  groupPath: GroupPath,
  path: number[],
  kind: 'condition' | 'group',
): Record<string, unknown> {
  const found = cloneAndGroup(spec, groupPath);
  if (!found) return spec;
  const container = descend(found.group, path);
  if (!container) return spec;
  const children = Array.isArray(container.conditions) ? container.conditions : [];
  if (kind === 'group') {
    children.push({ type: 'group', combine: 'all', conditions: [] });
  } else {
    const refs = availableRefs(found.next);
    children.push({
      type: 'condition',
      left: { ref: refs[0] ?? 'close' },
      op: '>',
      right: { value: 0 },
    });
  }
  container.conditions = children;
  return found.next;
}

/** Update one flat condition at `path`. A group node is left untouched. */
export function updateTreeNode(
  spec: Record<string, unknown>,
  groupPath: GroupPath,
  path: number[],
  patch: Partial<FlatCondition>,
): Record<string, unknown> {
  if (!path.length) return spec;
  const found = cloneAndGroup(spec, groupPath);
  if (!found) return spec;
  const container = descend(found.group, path.slice(0, -1));
  if (!container || !Array.isArray(container.conditions)) return spec;
  const index = path[path.length - 1];
  const node = container.conditions[index];
  if (!isRecord(node) || isGroupNode(node)) return spec;
  const flat = { ...flattenCondition(node), ...patch };
  if (flat.advanced) return spec;
  container.conditions[index] = toConditionNode(flat);
  return found.next;
}

/** Remove the node at `path` (a condition or a whole subgroup). */
export function removeTreeNode(
  spec: Record<string, unknown>,
  groupPath: GroupPath,
  path: number[],
): Record<string, unknown> {
  if (!path.length) return spec;
  const found = cloneAndGroup(spec, groupPath);
  if (!found) return spec;
  const container = descend(found.group, path.slice(0, -1));
  if (!container || !Array.isArray(container.conditions)) return spec;
  const index = path[path.length - 1];
  if (!container.conditions[index]) return spec;
  container.conditions.splice(index, 1);
  return found.next;
}

/** Change the combine mode of the group at `path` ([] = the root group). */
export function setTreeCombine(
  spec: Record<string, unknown>,
  groupPath: GroupPath,
  path: number[],
  combine: 'all' | 'any',
): Record<string, unknown> {
  const found = cloneAndGroup(spec, groupPath);
  if (!found) return spec;
  const target = descend(found.group, path);
  if (!target) return spec;
  target.combine = combine;
  return found.next;
}

// ── Basics (indicators, stops, sizing, risk, costs) ─────────────────────────

export function readBasics(spec: Record<string, unknown>): SpecBasics {
  const indicators = Array.isArray(spec.indicators) ? spec.indicators : [];
  const indicatorViews: IndicatorView[] = indicators.flatMap((decl, index) => {
    if (!isRecord(decl)) return [];
    const params = isRecord(decl.params) ? decl.params : {};
    const numeric = Object.entries(params)
      .filter(([, value]) => typeof value === 'number' && Number.isFinite(value))
      .map(([key, value]) => ({ key, value: value as number }));
    return [
      {
        index,
        id: typeof decl.id === 'string' ? decl.id : `indicator_${index}`,
        type: typeof decl.type === 'string' ? decl.type : 'unknown',
        params: numeric,
      },
    ];
  });

  const exit = isRecord(spec.rules) && isRecord(spec.rules.exit) ? spec.rules.exit : {};
  const stop = isRecord(exit.stop_loss) && typeof exit.stop_loss.value === 'number'
    ? { type: String(exit.stop_loss.type ?? 'atr'), value: exit.stop_loss.value }
    : null;
  const target = isRecord(exit.take_profit) && typeof exit.take_profit.value === 'number'
    ? { type: String(exit.take_profit.type ?? 'risk_reward'), value: exit.take_profit.value }
    : null;

  const sizing = isRecord(spec.position_sizing) ? spec.position_sizing : {};
  const risk = isRecord(spec.risk) ? spec.risk : {};
  const execution = isRecord(spec.execution) ? spec.execution : {};
  const costValue = (key: string) => {
    const block = isRecord(execution[key]) ? (execution[key] as Record<string, unknown>) : null;
    return block && typeof block.value === 'number' ? block.value : 0;
  };

  return {
    indicators: indicatorViews,
    stop,
    target,
    sizing: {
      type: typeof sizing.type === 'string' ? sizing.type : 'percent_equity',
      value: typeof sizing.value === 'number' ? sizing.value : 50,
    },
    risk: {
      maxPositionPct: typeof risk.max_position_pct === 'number' ? risk.max_position_pct : null,
      maxOpenPositions: typeof risk.max_open_positions === 'number' ? risk.max_open_positions : null,
      allowLong: risk.allow_long !== false,
      allowShort: risk.allow_short === true,
    },
    costs: {
      commission: costValue('commission'),
      slippage: costValue('slippage'),
      spread: costValue('spread'),
      fillAt: typeof execution.fill_at === 'string' ? execution.fill_at : 'next_open',
    },
  };
}

export function setIndicatorParam(
  spec: Record<string, unknown>,
  index: number,
  key: string,
  value: number,
): Record<string, unknown> {
  const next = clone(spec);
  const indicators = Array.isArray(next.indicators) ? next.indicators : [];
  const decl = indicators[index];
  if (!isRecord(decl)) return spec;
  const params = isRecord(decl.params) ? decl.params : {};
  params[key] = value;
  decl.params = params;
  return next;
}

export function setStop(spec: Record<string, unknown>, value: number, type = 'atr'): Record<string, unknown> {
  const next = clone(spec);
  const rules = isRecord(next.rules) ? next.rules : (next.rules = {});
  const exit = isRecord(rules.exit) ? rules.exit : (rules.exit = {});
  exit.stop_loss = { type, value };
  return next;
}

export function clearStop(spec: Record<string, unknown>): Record<string, unknown> {
  const next = clone(spec);
  const rules = isRecord(next.rules) ? next.rules : null;
  const exit = rules && isRecord(rules.exit) ? rules.exit : null;
  if (exit) delete exit.stop_loss;
  return next;
}

export function setTarget(
  spec: Record<string, unknown>,
  value: number,
  type = 'risk_reward',
): Record<string, unknown> {
  const next = clone(spec);
  const rules = isRecord(next.rules) ? next.rules : (next.rules = {});
  const exit = isRecord(rules.exit) ? rules.exit : (rules.exit = {});
  exit.take_profit = { type, value };
  return next;
}

export function clearTarget(spec: Record<string, unknown>): Record<string, unknown> {
  const next = clone(spec);
  const rules = isRecord(next.rules) ? next.rules : null;
  const exit = rules && isRecord(rules.exit) ? rules.exit : null;
  if (exit) delete exit.take_profit;
  return next;
}

export function setSizing(
  spec: Record<string, unknown>,
  patch: { type?: string; value?: number },
): Record<string, unknown> {
  const next = clone(spec);
  const sizing = isRecord(next.position_sizing) ? next.position_sizing : (next.position_sizing = {});
  if (patch.type !== undefined) sizing.type = patch.type;
  if (patch.value !== undefined) sizing.value = patch.value;
  return next;
}

export function setRisk(
  spec: Record<string, unknown>,
  patch: Partial<{ maxPositionPct: number; maxOpenPositions: number; allowLong: boolean; allowShort: boolean }>,
): Record<string, unknown> {
  const next = clone(spec);
  const risk = isRecord(next.risk) ? next.risk : (next.risk = {});
  if (patch.maxPositionPct !== undefined) risk.max_position_pct = patch.maxPositionPct;
  if (patch.maxOpenPositions !== undefined) risk.max_open_positions = patch.maxOpenPositions;
  if (patch.allowLong !== undefined) risk.allow_long = patch.allowLong;
  if (patch.allowShort !== undefined) risk.allow_short = patch.allowShort;
  return next;
}

export function setCost(
  spec: Record<string, unknown>,
  key: 'commission' | 'slippage' | 'spread',
  value: number,
): Record<string, unknown> {
  const next = clone(spec);
  const execution = isRecord(next.execution) ? next.execution : (next.execution = {});
  const block = isRecord(execution[key]) ? (execution[key] as Record<string, unknown>) : {};
  block.value = value;
  execution[key] = block;
  return next;
}
