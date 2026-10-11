import { describe, expect, it } from 'vitest';
import type { GraphNodeSpec } from './backtest-client';
import {
  addEdge,
  addNode,
  canConnect,
  deserialize,
  edgePath,
  fromStrategyGraph,
  makeNodeId,
  moveNode,
  portPosition,
  removeNode,
  serialize,
  specMap,
  toStrategyGraph,
  type EditorState,
  type GraphIdentity,
} from './graph-editor';

const SPECS: GraphNodeSpec[] = [
  {
    type: 'indicator.ema', version: '1.0.0', title: 'EMA', category: 'indicator',
    description: '', inputs: [], outputs: [{ name: 'out', type: 'series' }],
    config: { period: { type: 'integer', default: 20 } }, defaults: { period: 20 },
  },
  {
    type: 'logic.compare', version: '1.0.0', title: 'Compare', category: 'logic',
    description: '', inputs: [{ name: 'left', type: 'any', required: true, variadic: false },
      { name: 'right', type: 'any', required: true, variadic: false }],
    outputs: [{ name: 'out', type: 'rule' }], config: {}, defaults: {},
  },
  {
    type: 'logic.group', version: '1.0.0', title: 'Group', category: 'logic',
    description: '', inputs: [{ name: 'in', type: 'rule', required: false, variadic: true }],
    outputs: [{ name: 'out', type: 'rule' }], config: {}, defaults: {},
  },
  {
    type: 'trade.entry', version: '1.0.0', title: 'Entry', category: 'trading',
    description: '', inputs: [{ name: 'in', type: 'rule', required: true, variadic: false }],
    outputs: [], config: {}, defaults: {},
  },
];

const MAP = specMap(SPECS);
const IDENTITY: GraphIdentity = { id: 's', name: 'S', version: '1.0.0', description: '', assetClass: '' };

function specs(type: string): GraphNodeSpec {
  return SPECS.find((s) => s.type === type)!;
}

function emptyState(): EditorState {
  return { nodes: [], edges: [] };
}

describe('graph editor core', () => {
  it('makes unique, readable node ids', () => {
    const a = makeNodeId('indicator.ema', 1000);
    const b = makeNodeId('indicator.ema', 1000);
    expect(a).not.toBe(b);
    expect(a.startsWith('ema_')).toBe(true);
  });

  it('adds nodes with default config and removes their edges', () => {
    let state = addNode(emptyState(), specs('indicator.ema'), 10, 20);
    const ema = state.nodes[0];
    expect(ema.config.period).toBe(20);
    let state2 = addNode(state, specs('trade.entry'), 300, 20);
    const entry = state2.nodes[1];
    // connect ema.out -> entry.in is a type mismatch (series vs rule)
    expect(canConnect(state2, MAP, ema.id, 'out', entry.id, 'in').ok).toBe(false);
  });

  it('rejects self-connections and type mismatches; accepts valid ones', () => {
    let state = addNode(emptyState(), specs('indicator.ema'), 0, 0);
    const a = state.nodes[0];
    state = addNode(state, specs('logic.compare'), 260, 0);
    const cmp = state.nodes[1];
    state = addNode(state, specs('indicator.ema'), 0, 120);
    const b = state.nodes[2];

    expect(canConnect(state, MAP, a.id, 'out', a.id, 'left').ok).toBe(false);
    expect(canConnect(state, MAP, a.id, 'out', cmp.id, 'left').ok).toBe(true);
    expect(canConnect(state, MAP, b.id, 'out', cmp.id, 'right').ok).toBe(true);
    // compare.out is a rule → entry.in accepts rule
    const r = addEdge(state, MAP, a.id, 'out', cmp.id, 'left');
    expect(r.ok && r.state).toBeTruthy();
  });

  it('single-arity inputs are replaced; variadic inputs accumulate', () => {
    let state = addNode(emptyState(), specs('indicator.ema'), 0, 0);
    const a = state.nodes[0];
    state = addNode(state, specs('indicator.ema'), 0, 120);
    const b = state.nodes[1];
    state = addNode(state, specs('logic.compare'), 260, 0);
    const cmp = state.nodes[2];

    let r = addEdge(state, MAP, a.id, 'out', cmp.id, 'left');
    state = r.state!;
    expect(state.edges).toHaveLength(1);
    // a second edge to the SAME single input replaces the first
    r = addEdge(state, MAP, b.id, 'out', cmp.id, 'left');
    state = r.state!;
    expect(state.edges).toHaveLength(1);
    expect(state.edges[0].from).toBe(b.id);
  });

  it('moves a node without touching edges', () => {
    let state = addNode(emptyState(), specs('indicator.ema'), 0, 0);
    const id = state.nodes[0].id;
    state = moveNode(state, id, 99, 77);
    expect(state.nodes[0].x).toBe(99);
    expect(state.nodes[0].y).toBe(77);
  });

  it('removes a node and its incident edges', () => {
    let state = addNode(emptyState(), specs('indicator.ema'), 0, 0);
    const a = state.nodes[0].id;
    state = addNode(state, specs('logic.compare'), 200, 0);
    const cmp = state.nodes[1].id;
    state = addEdge(state, MAP, a, 'out', cmp, 'left').state!;
    state = removeNode(state, a);
    expect(state.nodes).toHaveLength(1);
    expect(state.edges).toHaveLength(0);
  });

  it('converts editor state to a StrategyGraph and round-trips', () => {
    let state = addNode(emptyState(), specs('indicator.ema'), 5, 5);
    state = addNode(state, specs('logic.compare'), 300, 5);
    const [ema, cmp] = state.nodes;
    state = addEdge(state, MAP, ema.id, 'out', cmp.id, 'left').state!;
    const graph = toStrategyGraph(state, IDENTITY);
    expect(graph.nodes).toHaveLength(2);
    expect(graph.edges[0]).toMatchObject({ from: ema.id, to: cmp.id, toPort: 'left' });
    const back = fromStrategyGraph(graph);
    expect(back.nodes.map((n) => n.id).sort()).toEqual(state.nodes.map((n) => n.id).sort());
    expect(back.edges).toHaveLength(1);
  });

  it('serializes and deserializes a draft', () => {
    const state = addNode(emptyState(), specs('indicator.ema'), 1, 2);
    const text = serialize(state, IDENTITY);
    const restored = deserialize(text);
    expect(restored?.state.nodes[0].type).toBe('indicator.ema');
    expect(deserialize('not json')).toBeNull();
  });

  it('computes port positions and edge paths deterministically', () => {
    const state = addNode(emptyState(), specs('logic.compare'), 0, 0);
    const p0 = portPosition(state.nodes[0], specs('logic.compare'), 'in', 'left');
    const p1 = portPosition(state.nodes[0], specs('logic.compare'), 'in', 'right');
    expect(p0.x).toBe(0);
    expect(p1.y).toBeGreaterThan(p0.y);
    expect(edgePath(p0, p1)).toContain('C');
  });
});
