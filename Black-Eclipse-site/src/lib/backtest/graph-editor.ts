// ── Strategy graph editor core ───────────────────────────────────────────────
// Pure, DOM-free logic for the Visual Strategy Builder canvas: node/edge
// mutation, connection rules (typed ports, single vs variadic inputs), the
// editor ⇄ `StrategyGraph` conversion and draft persistence. Keeping this pure
// makes the canvas a thin renderer and the rules unit-testable.
//
// The graph is a *strategy* graph (data/indicator/logic/trading/sizing/risk),
// not a general workflow graph. It compiles to the canonical StrategySpec IR on
// the runtime; the UI never invents financial semantics.

import type { GraphNodeSpec, StrategyGraph } from './backtest-client';

export interface EditorNode {
  id: string;
  type: string;
  config: Record<string, unknown>;
  x: number;
  y: number;
}

export interface EditorEdge {
  from: string;
  fromPort: string;
  to: string;
  toPort: string;
}

export interface EditorState {
  nodes: EditorNode[];
  edges: EditorEdge[];
}

export interface GraphIdentity {
  id: string;
  name: string;
  version: string;
  description: string;
  assetClass: string;
}

export type SpecMap = Record<string, GraphNodeSpec>;

export const NODE_WIDTH = 208;
export const PORT_ROW = 22;
export const NODE_HEADER = 30;

let idCounter = 0;

/** A stable, human-readable, unique node id. */
export function makeNodeId(type: string, now = Date.now()): string {
  idCounter += 1;
  const short = type.split('.').pop() ?? 'node';
  return `${short}_${now.toString(36)}_${idCounter}`;
}

export function specMap(specs: GraphNodeSpec[]): SpecMap {
  return Object.fromEntries(specs.map((s) => [s.type, s]));
}

export function defaultConfig(spec: GraphNodeSpec): Record<string, unknown> {
  return { ...spec.defaults };
}

// ── Mutations ────────────────────────────────────────────────────────────────

export function addNode(state: EditorState, spec: GraphNodeSpec, x: number, y: number): EditorState {
  const node: EditorNode = { id: makeNodeId(spec.type), type: spec.type, config: defaultConfig(spec), x, y };
  return { nodes: [...state.nodes, node], edges: state.edges };
}

export function removeNode(state: EditorState, id: string): EditorState {
  return {
    nodes: state.nodes.filter((n) => n.id !== id),
    edges: state.edges.filter((e) => e.from !== id && e.to !== id),
  };
}

export function moveNode(state: EditorState, id: string, x: number, y: number): EditorState {
  return { nodes: state.nodes.map((n) => (n.id === id ? { ...n, x, y } : n)), edges: state.edges };
}

export function updateConfig(state: EditorState, id: string, key: string, value: unknown): EditorState {
  return {
    nodes: state.nodes.map((n) => (n.id === id ? { ...n, config: { ...n.config, [key]: value } } : n)),
    edges: state.edges,
  };
}

// ── Connection rules ─────────────────────────────────────────────────────────

export interface ConnectResult {
  ok: boolean;
  reason?: string;
  /** The edge to add (may replace an existing edge on a single-input port). */
  state?: EditorState;
}

/** Can `from.fromPort` connect to `to.toPort`? Validates types and arity. */
export function canConnect(
  state: EditorState,
  specs: SpecMap,
  from: string,
  fromPort: string,
  to: string,
  toPort: string,
): { ok: boolean; reason?: string } {
  if (from === to) return { ok: false, reason: 'cannot connect a node to itself' };
  const fromNode = state.nodes.find((n) => n.id === from);
  const toNode = state.nodes.find((n) => n.id === to);
  if (!fromNode || !toNode) return { ok: false, reason: 'unknown node' };
  const fromSpec = specs[fromNode.type];
  const toSpec = specs[toNode.type];
  if (!fromSpec || !toSpec) return { ok: false, reason: 'unknown node type' };
  const out = fromSpec.outputs.find((p) => p.name === fromPort);
  const inp = toSpec.inputs.find((p) => p.name === toPort);
  if (!out) return { ok: false, reason: `no output ${fromPort}` };
  if (!inp) return { ok: false, reason: `no input ${toPort}` };
  if (inp.type !== 'any' && out.type !== inp.type) {
    return { ok: false, reason: `type mismatch: ${out.type} → ${inp.type}` };
  }
  const dup = state.edges.some(
    (e) => e.from === from && e.fromPort === fromPort && e.to === to && e.toPort === toPort,
  );
  if (dup) return { ok: false, reason: 'already connected' };
  return { ok: true };
}

/** Add an edge, replacing an existing one when the input port is single-arity. */
export function addEdge(
  state: EditorState,
  specs: SpecMap,
  from: string,
  fromPort: string,
  to: string,
  toPort: string,
): ConnectResult {
  const check = canConnect(state, specs, from, fromPort, to, toPort);
  if (!check.ok) return check;
  const toSpec = specs[state.nodes.find((n) => n.id === to)!.type];
  const variadic = toSpec.inputs.find((p) => p.name === toPort)?.variadic ?? false;
  let edges = state.edges;
  if (!variadic) {
    edges = edges.filter((e) => !(e.to === to && e.toPort === toPort));
  }
  edges = [...edges, { from, fromPort, to, toPort }];
  return { ok: true, state: { nodes: state.nodes, edges } };
}

export function removeEdge(state: EditorState, from: string, fromPort: string, to: string, toPort: string): EditorState {
  return {
    nodes: state.nodes,
    edges: state.edges.filter(
      (e) => !(e.from === from && e.fromPort === fromPort && e.to === to && e.toPort === toPort),
    ),
  };
}

// ── Geometry (for the SVG renderer; pure + testable) ─────────────────────────

export function portPosition(node: EditorNode, spec: GraphNodeSpec | undefined, kind: 'in' | 'out', port: string): { x: number; y: number } {
  const list = kind === 'in' ? spec?.inputs ?? [] : spec?.outputs ?? [];
  const idx = Math.max(0, list.findIndex((p) => p.name === port));
  const y = node.y + NODE_HEADER + idx * PORT_ROW + PORT_ROW / 2;
  const x = kind === 'in' ? node.x : node.x + NODE_WIDTH;
  return { x, y };
}

export function edgePath(from: { x: number; y: number }, to: { x: number; y: number }): string {
  const dx = Math.max(40, Math.abs(to.x - from.x) * 0.5);
  return `M ${from.x} ${from.y} C ${from.x + dx} ${from.y}, ${to.x - dx} ${to.y}, ${to.x} ${to.y}`;
}

// ── Conversion + persistence ─────────────────────────────────────────────────

export function toStrategyGraph(state: EditorState, identity: GraphIdentity): StrategyGraph {
  return {
    schemaVersion: '1.0.0',
    strategy: {
      id: identity.id,
      name: identity.name,
      version: identity.version,
      description: identity.description,
      assetClass: identity.assetClass || null,
    },
    nodes: state.nodes.map((n) => ({ id: n.id, type: n.type, config: n.config })),
    edges: state.edges.map((e) => ({ from: e.from, fromPort: e.fromPort, to: e.to, toPort: e.toPort })),
  };
}

export function fromStrategyGraph(graph: StrategyGraph): EditorState {
  return {
    nodes: graph.nodes.map((n, i) => ({
      id: n.id,
      type: n.type,
      config: { ...(n.config ?? {}) },
      x: 60 + (i % 4) * 260,
      y: 60 + Math.floor(i / 4) * 180,
    })),
    edges: (graph.edges ?? []).map((e) => ({
      from: e.from, fromPort: e.fromPort ?? 'out', to: e.to, toPort: e.toPort ?? 'in',
    })),
  };
}

export function serialize(state: EditorState, identity: GraphIdentity): string {
  return JSON.stringify({ identity, state });
}

export function deserialize(text: string): { state: EditorState; identity: GraphIdentity } | null {
  try {
    const parsed = JSON.parse(text) as { identity: GraphIdentity; state: EditorState };
    if (!parsed.state?.nodes || !parsed.identity) return null;
    return parsed;
  } catch {
    return null;
  }
}

export const DRAFT_KEY = 'black-eclipse:strategy-graph-draft';
