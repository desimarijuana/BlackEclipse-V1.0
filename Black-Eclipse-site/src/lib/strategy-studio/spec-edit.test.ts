import { describe, expect, it } from 'vitest';
import {
  addCondition,
  addTreeNode,
  availableRefs,
  clearStop,
  readBasics,
  readGroup,
  readTree,
  removeCondition,
  removeTreeNode,
  setCombine,
  setCost,
  setIndicatorParam,
  setRisk,
  setSizing,
  setStop,
  setTarget,
  setTreeCombine,
  updateCondition,
  updateTreeNode,
} from './spec-edit';

function baseSpec() {
  return {
    strategy: { id: 'ema_cross', name: 'EMA Cross', version: '1.0.0' },
    universe: { symbols: ['BTC-USD'] },
    indicators: [
      { id: 'ema_fast', type: 'ema', params: { period: 20 } },
      { id: 'ema_slow', type: 'ema', params: { period: 50 } },
      { id: 'atr', type: 'atr', params: { period: 14 } },
    ],
    rules: {
      entry: {
        long: {
          type: 'group',
          combine: 'all',
          conditions: [
            { type: 'condition', left: { ref: 'ema_fast' }, op: 'cross_above', right: { ref: 'ema_slow' } },
          ],
        },
      },
      exit: {
        long: {
          type: 'group',
          combine: 'any',
          conditions: [{ type: 'condition', left: { ref: 'close' }, op: '<', right: { ref: 'ema_fast' } }],
        },
        stop_loss: { type: 'atr', value: 2 },
        take_profit: { type: 'risk_reward', value: 3 },
      },
    },
    position_sizing: { type: 'percent_equity', value: 50 },
    risk: { max_position_pct: 100, max_open_positions: 1, allow_long: true, allow_short: false },
    execution: {
      commission: { type: 'percentage', value: 0.1 },
      slippage: { type: 'percentage', value: 0.05 },
      spread: { type: 'bps', value: 5 },
      fill_at: 'next_open',
    },
    metadata: { keep: 'me' },
  };
}

describe('spec editing', () => {
  it('reads a flat group without touching the spec', () => {
    const spec = baseSpec();
    const before = JSON.stringify(spec);
    const group = readGroup(spec, 'rules.entry.long');
    expect(group.combine).toBe('all');
    expect(group.advanced).toBe(false);
    expect(group.conditions).toHaveLength(1);
    expect(group.conditions[0]).toMatchObject({ leftRef: 'ema_fast', op: 'cross_above', rightKind: 'ref' });
    expect(JSON.stringify(spec)).toBe(before);
  });

  it('marks nested groups and expression operands as advanced', () => {
    const spec = baseSpec();
    const rules = spec.rules as Record<string, unknown>;
    const entry = rules.entry as Record<string, unknown>;
    entry.long = {
      type: 'group',
      combine: 'all',
      conditions: [
        {
          type: 'condition',
          left: { expr: { op: '+', left: { ref: 'close' }, right: { value: 1 } } },
          op: '>',
          right: { value: 0 },
        },
      ],
    };
    expect(readGroup(spec as unknown as Record<string, unknown>, 'rules.entry.long').advanced).toBe(true);
  });

  it('reports a missing group instead of inventing one', () => {
    const spec = baseSpec();
    delete (spec.rules.entry as Record<string, unknown>).long;
    const group = readGroup(spec as unknown as Record<string, unknown>, 'rules.entry.long');
    expect(group.missing).toBe(true);
    expect(group.conditions).toEqual([]);
  });

  it('adds, updates and removes a condition', () => {
    const spec = baseSpec();
    const added = addCondition(spec, 'rules.entry.long', { leftRef: 'rsi', rightKind: 'value', rightValue: 30 });
    expect(readGroup(added, 'rules.entry.long').conditions).toHaveLength(2);
    expect(readGroup(added, 'rules.entry.long').conditions[1].rightValue).toBe(30);

    const updated = updateCondition(added, 'rules.entry.long', 1, { op: '<' });
    expect(readGroup(updated, 'rules.entry.long').conditions[1].op).toBe('<');

    const removed = removeCondition(updated, 'rules.entry.long', 0);
    expect(readGroup(removed, 'rules.entry.long').conditions).toHaveLength(1);
    expect(readGroup(spec, 'rules.entry.long').conditions).toHaveLength(1);
  });

  it('changes the combine mode without disturbing conditions', () => {
    const spec = baseSpec();
    const next = setCombine(spec, 'rules.exit.long', 'all');
    expect(readGroup(next, 'rules.exit.long').combine).toBe('all');
    expect(readGroup(next, 'rules.exit.long').conditions).toHaveLength(1);
  });

  it('preserves fields the builder does not understand', () => {
    const spec = baseSpec();
    const next = addCondition(spec, 'rules.entry.long', { leftRef: 'close' });
    expect((next.metadata as Record<string, unknown>).keep).toBe('me');
    expect(next.strategy).toEqual(spec.strategy);
  });

  it('shows only refs the engine knows', () => {
    const refs = availableRefs(baseSpec());
    expect(refs).toContain('close');
    expect(refs).toContain('ema_fast');
    expect(refs).toContain('ema_slow');
    expect(refs).not.toContain('ema_unknown');
  });

  it('reads the basics the form needs', () => {
    const basics = readBasics(baseSpec());
    expect(basics.indicators.map((indicator) => indicator.id)).toEqual(['ema_fast', 'ema_slow', 'atr']);
    expect(basics.indicators[0].params).toEqual([{ key: 'period', value: 20 }]);
    expect(basics.stop).toEqual({ type: 'atr', value: 2 });
    expect(basics.target).toEqual({ type: 'risk_reward', value: 3 });
    expect(basics.sizing).toEqual({ type: 'percent_equity', value: 50 });
    expect(basics.risk.maxOpenPositions).toBe(1);
    expect(basics.costs.commission).toBe(0.1);
    expect(basics.costs.fillAt).toBe('next_open');
  });

  it('edits indicators, stops, sizing, risk and costs immutably', () => {
    const spec = baseSpec();
    expect(readBasics(setIndicatorParam(spec, 0, 'period', 30)).indicators[0].params[0].value).toBe(30);
    expect(readBasics(setStop(spec, 3.5)).stop).toEqual({ type: 'atr', value: 3.5 });
    expect(readBasics(clearStop(spec)).stop).toBeNull();
    expect(readBasics(setTarget(spec, 4)).target).toEqual({ type: 'risk_reward', value: 4 });
    expect(readBasics(setSizing(spec, { value: 25 })).sizing.value).toBe(25);
    expect(readBasics(setRisk(spec, { allowShort: true })).risk.allowShort).toBe(true);
    expect(readBasics(setCost(spec, 'commission', 0.2)).costs.commission).toBe(0.2);
    // The original is untouched.
    expect(readBasics(spec).stop).toEqual({ type: 'atr', value: 2 });
  });

  it('reads a nested group as a group, not as an advanced condition', () => {
    const spec = baseSpec();
    const added = addTreeNode(spec, 'rules.entry.long', [], 'group');
    const tree = readTree(added, 'rules.entry.long');
    expect(tree.children).toHaveLength(2);
    expect(tree.children[1].group).not.toBeNull();
    expect(tree.children[1].group?.children).toEqual([]);
    expect(tree.advanced).toBe(false);
  });

  it('adds and edits a condition inside a nested group', () => {
    let spec = addTreeNode(baseSpec(), 'rules.entry.long', [], 'group');
    spec = addTreeNode(spec, 'rules.entry.long', [1], 'condition');
    spec = updateTreeNode(spec, 'rules.entry.long', [1, 0], { leftRef: 'rsi', rightKind: 'value', rightValue: 30 });
    const tree = readTree(spec, 'rules.entry.long');
    const nested = tree.children[1].group?.children[0];
    expect(nested?.condition?.leftRef).toBe('rsi');
    expect(nested?.condition?.rightValue).toBe(30);

    // The JSON carries a real nested group.
    const raw = (spec.rules as Record<string, unknown>).entry as Record<string, unknown>;
    const long = raw.long as Record<string, unknown>;
    const conditions = long.conditions as Array<Record<string, unknown>>;
    expect(conditions[1].type).toBe('group');
    expect(Array.isArray(conditions[1].conditions)).toBe(true);
  });

  it('removes a whole nested group without touching its sibling', () => {
    let spec = addTreeNode(baseSpec(), 'rules.entry.long', [], 'group');
    spec = removeTreeNode(spec, 'rules.entry.long', [1]);
    const tree = readTree(spec, 'rules.entry.long');
    expect(tree.children).toHaveLength(1);
    expect(tree.children[0].condition?.leftRef).toBe('ema_fast');
  });

  it('changes the combine mode of a nested group', () => {
    let spec = addTreeNode(baseSpec(), 'rules.entry.long', [], 'group');
    spec = setTreeCombine(spec, 'rules.entry.long', [1], 'any');
    expect(readTree(spec, 'rules.entry.long').children[1].group?.combine).toBe('any');
    // The root is untouched.
    expect(readTree(spec, 'rules.entry.long').combine).toBe('all');
  });

  it('still reports an expression condition as advanced', () => {
    const spec = baseSpec();
    const rules = spec.rules as Record<string, unknown>;
    const entry = rules.entry as Record<string, unknown>;
    entry.long = {
      type: 'group',
      combine: 'all',
      conditions: [
        {
          type: 'condition',
          left: { expr: { op: '+', left: { ref: 'close' }, right: { value: 1 } } },
          op: '>',
          right: { value: 0 },
        },
      ],
    };
    expect(readTree(spec as unknown as Record<string, unknown>, 'rules.entry.long').advanced).toBe(true);
  });
});
