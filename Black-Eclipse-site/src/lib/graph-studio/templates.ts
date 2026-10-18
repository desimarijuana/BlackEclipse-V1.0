// ── Starter templates ─────────────────────────────────────────────────────────
// Real, VALID graphs (they pass `validateWorkflow`) used to seed a new workflow
// and to demonstrate the model. Like everything else, a template is just an IR
// document — never a static diagram.

import { createWorkflowIR } from './ir';
import { autoLayout } from './layout';
import { getNodeDefinition } from './registry';
import { requiredCapabilitiesFor } from './validation';
import type { WorkflowEdge, WorkflowIR, WorkflowNode } from './types';

export interface WorkflowTemplate {
  id: string;
  name: string;
  description: string;
  build: () => WorkflowIR;
}

interface NodeSpec {
  id: string;
  type: string;
  config?: Record<string, unknown>;
  label?: string;
}

interface EdgeSpec {
  source: string;
  sourceHandle: string;
  target: string;
  targetHandle: string;
}

function buildGraph(name: string, description: string, nodeSpecs: NodeSpec[], edgeSpecs: EdgeSpec[]): WorkflowIR {
  const nodes: WorkflowNode[] = nodeSpecs.map((spec) => {
    const def = getNodeDefinition(spec.type);
    if (!def) throw new Error(`Template references unknown node type "${spec.type}"`);
    return {
      id: spec.id,
      type: def.type,
      version: def.version,
      label: spec.label,
      config: { ...def.defaultConfig(), ...(spec.config ?? {}) },
      layout: { x: 0, y: 0 },
    };
  });
  const edges: WorkflowEdge[] = edgeSpecs.map((spec, index) => ({ id: `e${index + 1}`, ...spec }));
  let ir = createWorkflowIR({ name, description, nodes, edges });
  const positions = autoLayout(ir);
  ir = { ...ir, nodes: ir.nodes.map((n) => ({ ...n, layout: positions[n.id] ?? n.layout })) };
  ir = { ...ir, requiredCapabilities: requiredCapabilitiesFor(ir) };
  return ir;
}

function blank(): WorkflowIR {
  return buildGraph(
    'Blank workflow',
    'A trigger wired to a result — the smallest valid graph.',
    [
      { id: 'trigger', type: 'trigger.manual' },
      { id: 'result', type: 'output.result' },
    ],
    [{ source: 'trigger', sourceHandle: 'start', target: 'result', targetHandle: 'value' }],
  );
}

function priceCheck(): WorkflowIR {
  return buildGraph(
    'Price + indicator check',
    'Read a daily series, compute an SMA, and branch on the result.',
    [
      { id: 'trigger', type: 'trigger.manual', config: { seed: 'AAPL' } },
      { id: 'market', type: 'finance.market_data', config: { symbol: 'AAPL', interval: '1d', lookback: 200 } },
      { id: 'indicator', type: 'finance.indicator', config: { kind: 'sma', period: 50 } },
      { id: 'condition', type: 'logic.condition', config: { operator: 'truthy' } },
      { id: 'result', type: 'output.result', config: { label: 'Signal' } },
    ],
    [
      { source: 'trigger', sourceHandle: 'start', target: 'market', targetHandle: 'symbol' },
      { source: 'market', sourceHandle: 'series', target: 'indicator', targetHandle: 'series' },
      { source: 'indicator', sourceHandle: 'values', target: 'condition', targetHandle: 'value' },
      { source: 'condition', sourceHandle: 'result', target: 'result', targetHandle: 'value' },
    ],
  );
}

function httpFetch(): WorkflowIR {
  return buildGraph(
    'HTTP request',
    'Call an external endpoint and capture the response.',
    [
      { id: 'trigger', type: 'trigger.manual' },
      { id: 'http', type: 'integration.http', config: { url: 'https://api.example.com/data', method: 'GET' } },
      { id: 'result', type: 'output.result', config: { label: 'Response' } },
    ],
    [
      { source: 'trigger', sourceHandle: 'start', target: 'http', targetHandle: 'body' },
      { source: 'http', sourceHandle: 'body', target: 'result', targetHandle: 'value' },
    ],
  );
}

function ifElse(): WorkflowIR {
  return buildGraph(
    'If / else',
    'Branch on a value: only the taken gate runs.',
    [
      { id: 'trigger', type: 'trigger.manual', config: { seed: 'go' } },
      { id: 'value', type: 'data.value', config: { dataType: 'string', value: '' } },
      { id: 'condition', type: 'logic.condition', config: { operator: 'eq', compareTo: 'go' } },
      { id: 'taken', type: 'flow.gate' },
      { id: 'otherwise', type: 'flow.gate' },
      { id: 'result', type: 'output.result', config: { label: 'Taken' } },
      { id: 'fallback', type: 'output.result', config: { label: 'Otherwise' } },
    ],
    [
      { source: 'trigger', sourceHandle: 'start', target: 'value', targetHandle: 'in' },
      { source: 'value', sourceHandle: 'value', target: 'condition', targetHandle: 'value' },
      { source: 'condition', sourceHandle: 'true', target: 'taken', targetHandle: 'in' },
      { source: 'condition', sourceHandle: 'false', target: 'otherwise', targetHandle: 'in' },
      { source: 'value', sourceHandle: 'value', target: 'taken', targetHandle: 'value' },
      { source: 'value', sourceHandle: 'value', target: 'otherwise', targetHandle: 'value' },
      { source: 'taken', sourceHandle: 'value', target: 'result', targetHandle: 'value' },
      { source: 'otherwise', sourceHandle: 'value', target: 'fallback', targetHandle: 'value' },
    ],
  );
}

function marketScan(): WorkflowIR {
  return buildGraph(
    'Market scan (SMA z-score)',
    'Read stored bars, smooth them, z-score the trend, and branch when it is stretched. Fill the bars with the research-data tools first.',
    [
      { id: 'trigger', type: 'trigger.manual', config: { seed: 'AAPL' } },
      { id: 'market', type: 'finance.market_data', config: { symbol: '', interval: '1d', lookback: 200 } },
      { id: 'sma', type: 'finance.indicator', config: { kind: 'sma', period: 50 } },
      { id: 'z', type: 'quant.zscore', config: { period: 20 } },
      { id: 'stretched', type: 'logic.condition', config: { operator: 'gt', compareTo: '1' } },
      { id: 'result', type: 'output.result', config: { label: 'Stretched?' } },
      { id: 'provenance', type: 'output.result', config: { label: 'Data provenance' } },
    ],
    [
      { source: 'trigger', sourceHandle: 'start', target: 'market', targetHandle: 'symbol' },
      { source: 'market', sourceHandle: 'series', target: 'sma', targetHandle: 'series' },
      { source: 'sma', sourceHandle: 'values', target: 'z', targetHandle: 'values' },
      { source: 'z', sourceHandle: 'values', target: 'stretched', targetHandle: 'value' },
      { source: 'stretched', sourceHandle: 'result', target: 'result', targetHandle: 'value' },
      { source: 'market', sourceHandle: 'provenance', target: 'provenance', targetHandle: 'value' },
    ],
  );
}

export const WORKFLOW_TEMPLATES: WorkflowTemplate[] = [
  { id: 'blank', name: 'Blank', description: 'A trigger and a result. Start here.', build: blank },
  { id: 'if-else', name: 'If / else', description: 'Branch on a value with control gates.', build: ifElse },
  { id: 'market-scan', name: 'Market scan', description: 'Stored bars → SMA → z-score → branch.', build: marketScan },
  { id: 'price-check', name: 'Price + indicator', description: 'Market data → SMA → branch.', build: priceCheck },
  { id: 'http-fetch', name: 'HTTP request', description: 'Fetch an external endpoint.', build: httpFetch },
];

export function buildTemplate(id: string): WorkflowIR | null {
  const template = WORKFLOW_TEMPLATES.find((t) => t.id === id);
  return template ? template.build() : null;
}
