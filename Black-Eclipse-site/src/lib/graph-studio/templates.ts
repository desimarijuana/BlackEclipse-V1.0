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
      { id: 'trigger', type: 'trigger.manual' },
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
      { id: 'trigger', type: 'trigger.manual' },
      { id: 'value', type: 'data.value', config: { dataType: 'string', value: 'go' } },
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
      { id: 'trigger', type: 'trigger.manual' },
      { id: 'market', type: 'finance.market_data', config: { symbol: 'AAPL', interval: '1d', lookback: 200 } },
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

function dataPipeline(): WorkflowIR {
  return buildGraph(
    'Data pipeline (six nodes)',
    'Constant → parse JSON → set variables → save/load dataset → write file. A test run stops at Write file by design; use an operator run and grant the workspace scope.',
    [
      { id: 'trigger', type: 'trigger.manual' },
      {
        id: 'constant',
        type: 'data.value',
        config: { dataType: 'string', value: '{"symbol": "AAPL", "rows": [1, 2, 3]}' },
      },
      { id: 'parse', type: 'data.json.parse', config: { strict: true } },
      { id: 'variables', type: 'data.set_variables', config: { variables: { env: 'demo' } } },
      { id: 'save', type: 'data.dataset.save', config: { name: 'demo_payload', ttlHours: 0 } },
      { id: 'load', type: 'data.dataset.load' },
      {
        id: 'path',
        type: 'data.value',
        config: { dataType: 'string', value: 'demo/payload.json' },
      },
      { id: 'write', type: 'file.write', config: { scope: 'workspace', path: 'demo/payload.json', append: false } },
      { id: 'result', type: 'output.result', config: { label: 'Dataset' } },
    ],
    [
      { source: 'trigger', sourceHandle: 'start', target: 'constant', targetHandle: 'in' },
      { source: 'constant', sourceHandle: 'value', target: 'parse', targetHandle: 'text' },
      { source: 'parse', sourceHandle: 'value', target: 'variables', targetHandle: 'in' },
      { source: 'variables', sourceHandle: 'variables', target: 'save', targetHandle: 'value' },
      { source: 'save', sourceHandle: 'ref', target: 'load', targetHandle: 'ref' },
      { source: 'load', sourceHandle: 'value', target: 'write', targetHandle: 'content' },
      { source: 'path', sourceHandle: 'value', target: 'write', targetHandle: 'path' },
      { source: 'load', sourceHandle: 'value', target: 'result', targetHandle: 'value' },
    ],
  );
}

function webhookHttp(): WorkflowIR {
  return buildGraph(
    'Webhook to HTTP (demo)',
    'An inbound signed webhook calls a public echo API and returns the response and status. Open the Webhook tab, create the endpoint, then arm it with network access.',
    [
      { id: 'hook', type: 'trigger.webhook' },
      {
        id: 'http',
        type: 'integration.http',
        config: {
          url: 'https://postman-echo.com/get',
          method: 'GET',
          queryJson: '{"demo":"eclipse"}',
          responseType: 'auto',
          failOnHttpError: true,
          timeoutMs: 15_000,
        },
      },
      { id: 'response', type: 'output.result', config: { label: 'HTTP response' } },
      { id: 'status', type: 'output.result', config: { label: 'HTTP status' } },
    ],
    [
      { source: 'hook', sourceHandle: 'start', target: 'http', targetHandle: 'body' },
      { source: 'http', sourceHandle: 'body', target: 'response', targetHandle: 'value' },
      { source: 'http', sourceHandle: 'status', target: 'status', targetHandle: 'value' },
    ],
  );
}

function signedWebhookDemo(): WorkflowIR {
  return buildGraph(
    'Signed webhook (demo)',
    'Manual trigger → signed outbound webhook. Set ECLIPSE_DEMO_WEBHOOK_SECRET in the runtime environment, then run as an operator with network access.',
    [
      { id: 'trigger', type: 'trigger.manual' },
      {
        id: 'send',
        type: 'integration.webhook_send',
        config: {
          url: 'https://postman-echo.com/post',
          bodyJson: '{"event":"demo","source":"eclipse"}',
          secretEnv: 'ECLIPSE_DEMO_WEBHOOK_SECRET',
          deliveryId: 'eclipse-demo-1',
        },
      },
      { id: 'result', type: 'output.result', config: { label: 'Delivery' } },
    ],
    [
      { source: 'trigger', sourceHandle: 'start', target: 'send', targetHandle: 'body' },
      { source: 'send', sourceHandle: 'body', target: 'result', targetHandle: 'value' },
    ],
  );
}

function backtestVerdict(): WorkflowIR {
  return buildGraph(
    'Backtest and grade',
    'Read daily bars, backtest an EMA cross, stress its robustness, and grade the evidence. A stored series must exist for the symbol first (research-data tools).',
    [
      { id: 'trigger', type: 'trigger.manual' },
      { id: 'market', type: 'finance.market_data', config: { symbol: 'AAPL', interval: '1d', lookback: 500 } },
      {
        id: 'backtest',
        type: 'quant.backtest',
        config: { preset: 'ema_cross', fast: 12, slow: 50, includeSeries: true },
      },
      { id: 'robustness', type: 'quant.robustness', config: { preset: 'ema_cross', fast: 12, slow: 50 } },
      { id: 'grade', type: 'quant.grade' },
      { id: 'result', type: 'output.result', config: { label: 'Verdict summary' } },
      { id: 'detail', type: 'output.result', config: { label: 'Verdict detail' } },
      { id: 'conclusions', type: 'output.result', config: { label: 'Robustness conclusions' } },
    ],
    [
      { source: 'trigger', sourceHandle: 'start', target: 'market', targetHandle: 'symbol' },
      { source: 'market', sourceHandle: 'series', target: 'backtest', targetHandle: 'series' },
      { source: 'market', sourceHandle: 'series', target: 'robustness', targetHandle: 'series' },
      { source: 'backtest', sourceHandle: 'metrics', target: 'grade', targetHandle: 'metrics' },
      { source: 'backtest', sourceHandle: 'trades', target: 'grade', targetHandle: 'trades' },
      { source: 'backtest', sourceHandle: 'result', target: 'grade', targetHandle: 'result' },
      { source: 'grade', sourceHandle: 'summary', target: 'result', targetHandle: 'value' },
      { source: 'grade', sourceHandle: 'verdict', target: 'detail', targetHandle: 'value' },
      { source: 'robustness', sourceHandle: 'conclusions', target: 'conclusions', targetHandle: 'value' },
    ],
  );
}

function riskSnapshot(): WorkflowIR {
  return buildGraph(
    'Risk snapshot',
    'Read daily bars, compute volatility/Sharpe/VaR directly from the bars, and capture the live quote. Needs a configured market-data provider.',
    [
      { id: 'trigger', type: 'trigger.manual' },
      {
        id: 'bars',
        type: 'finance.history',
        config: { symbol: 'AAPL', interval: '1d', limit: 250, freshness: 'slow' },
      },
      { id: 'risk', type: 'quant.risk_metrics', config: { inputKind: 'prices', periodsPerYear: 252 } },
      { id: 'quote', type: 'finance.quote', config: { symbol: 'AAPL', freshness: 'intraday' } },
      { id: 'result', type: 'output.result', config: { label: 'Risk metrics' } },
      { id: 'price', type: 'output.result', config: { label: 'Live quote' } },
    ],
    [
      { source: 'trigger', sourceHandle: 'start', target: 'bars', targetHandle: 'symbol' },
      { source: 'trigger', sourceHandle: 'start', target: 'quote', targetHandle: 'symbol' },
      { source: 'bars', sourceHandle: 'series', target: 'risk', targetHandle: 'values' },
      { source: 'risk', sourceHandle: 'metrics', target: 'result', targetHandle: 'value' },
      { source: 'quote', sourceHandle: 'quote', target: 'price', targetHandle: 'value' },
    ],
  );
}

function derivativesMonitor(): WorkflowIR {
  return buildGraph(
    'Derivatives monitor',
    'Read funding, open interest and liquidations for one perpetual and capture each summary. Crypto provider required.',
    [
      { id: 'trigger', type: 'trigger.manual' },
      { id: 'funding', type: 'finance.funding_rate', config: { symbol: 'BTC-USD', freshness: 'realtime' } },
      { id: 'oi', type: 'finance.open_interest', config: { symbol: 'BTC-USD', window: '24h' } },
      { id: 'liq', type: 'finance.liquidations', config: { symbol: 'BTC-USD', window: '24h' } },
      { id: 'fundingOut', type: 'output.result', config: { label: 'Funding' } },
      { id: 'oiOut', type: 'output.result', config: { label: 'Open interest' } },
      { id: 'liqOut', type: 'output.result', config: { label: 'Liquidations' } },
    ],
    [
      { source: 'trigger', sourceHandle: 'start', target: 'funding', targetHandle: 'symbol' },
      { source: 'trigger', sourceHandle: 'start', target: 'oi', targetHandle: 'symbol' },
      { source: 'trigger', sourceHandle: 'start', target: 'liq', targetHandle: 'symbol' },
      { source: 'funding', sourceHandle: 'summary', target: 'fundingOut', targetHandle: 'value' },
      { source: 'oi', sourceHandle: 'summary', target: 'oiOut', targetHandle: 'value' },
      { source: 'liq', sourceHandle: 'summary', target: 'liqOut', targetHandle: 'value' },
    ],
  );
}

function ratesCheck(): WorkflowIR {
  return buildGraph(
    'FX + bond yield check',
    'Read an FX pair and a government yield, then capture both summaries and provenance.',
    [
      { id: 'trigger', type: 'trigger.manual' },
      { id: 'fx', type: 'finance.fx_rate', config: { base: 'EUR', quote: 'USD', freshness: 'realtime' } },
      { id: 'bond', type: 'finance.bond', config: { symbol: 'US10Y', seriesType: 'treasury', freshness: 'slow' } },
      { id: 'fxOut', type: 'output.result', config: { label: 'FX rate' } },
      { id: 'bondOut', type: 'output.result', config: { label: 'Bond yield' } },
      { id: 'fxMeta', type: 'output.result', config: { label: 'FX provenance' } },
    ],
    [
      { source: 'trigger', sourceHandle: 'start', target: 'fx', targetHandle: 'symbol' },
      { source: 'trigger', sourceHandle: 'start', target: 'bond', targetHandle: 'symbol' },
      { source: 'fx', sourceHandle: 'summary', target: 'fxOut', targetHandle: 'value' },
      { source: 'bond', sourceHandle: 'summary', target: 'bondOut', targetHandle: 'value' },
      { source: 'fx', sourceHandle: 'provenance', target: 'fxMeta', targetHandle: 'value' },
    ],
  );
}

function researchBrief(): WorkflowIR {
  return buildGraph(
    'Research brief',
    'Resolve a stored research run, read its evidence, scan conflicts, audit citations and build a report.',
    [
      { id: 'trigger', type: 'trigger.manual' },
      { id: 'latest', type: 'research.latest', config: { questionMatch: 'NVDA revenue' } },
      { id: 'evidence', type: 'research.evidence', config: { limit: 200 } },
      { id: 'scan', type: 'research.conflict_scan', config: { mergeStored: true } },
      { id: 'audit', type: 'research.citation_audit', config: { requireCitations: true } },
      { id: 'report', type: 'research.report', config: { maxItems: 50 } },
      { id: 'result', type: 'output.result', config: { label: 'Research report' } },
      { id: 'conflicts', type: 'output.result', config: { label: 'Conflicts found' } },
    ],
    [
      { source: 'trigger', sourceHandle: 'start', target: 'latest', targetHandle: 'question' },
      { source: 'latest', sourceHandle: 'researchId', target: 'evidence', targetHandle: 'researchId' },
      { source: 'evidence', sourceHandle: 'evidence', target: 'scan', targetHandle: 'evidence' },
      { source: 'evidence', sourceHandle: 'evidence', target: 'audit', targetHandle: 'evidence' },
      { source: 'latest', sourceHandle: 'researchId', target: 'report', targetHandle: 'researchId' },
      { source: 'report', sourceHandle: 'report', target: 'result', targetHandle: 'value' },
      { source: 'scan', sourceHandle: 'conflicts', target: 'conflicts', targetHandle: 'value' },
    ],
  );
}

function fileImport(): WorkflowIR {
  return buildGraph(
    'File import',
    'Upload a CSV/JSON/Excel file, parse it, select columns and return the rows.',
    [
      { id: 'trigger', type: 'trigger.manual' },
      {
        id: 'when',
        type: 'logic.condition',
        config: { operator: 'neq', compareTo: 'skip' },
        label: 'Run has started',
      },
      { id: 'file', type: 'data.file.attach', config: { parseAs: 'auto', header: true } },
      {
        id: 'select',
        type: 'transform.select',
        config: { fields: '', onMissing: 'null' },
      },
      { id: 'result', type: 'output.result', config: { label: 'Rows' } },
    ],
    [
      { source: 'trigger', sourceHandle: 'start', target: 'when', targetHandle: 'value' },
      { source: 'when', sourceHandle: 'true', target: 'file', targetHandle: 'in' },
      { source: 'file', sourceHandle: 'rows', target: 'select', targetHandle: 'rows' },
      { source: 'select', sourceHandle: 'rows', target: 'result', targetHandle: 'value' },
    ],
  );
}

function candleReview(): WorkflowIR {
  return buildGraph(
    'Candle option review',
    'Read several candidate candle images, then ask an agent to compare the readings and pick the best setup.',
    [
      { id: 'trigger', type: 'trigger.manual' },
      {
        id: 'batch',
        type: 'image.batch',
        config: {
          questionsJson: '["Describe the candle anatomy.","What pattern is this and what would confirm it?"]',
          mode: 'analyze',
          concurrency: 1,
          maxImages: 8,
        },
      },
      {
        id: 'agent',
        type: 'agent.task',
        config: {
          task: 'Compare the image readings and say which candle option best matches a valid entry setup. Explain why and state what is unverified.',
          memoryMode: 'read',
          memoryScope: 'workflow',
          outputMode: 'text',
          includeInput: true,
        },
      },
      { id: 'summary', type: 'output.result', config: { label: 'Batch summary' } },
      { id: 'result', type: 'output.result', config: { label: 'Option review' } },
    ],
    [
      { source: 'trigger', sourceHandle: 'start', target: 'batch', targetHandle: 'images' },
      { source: 'batch', sourceHandle: 'results', target: 'agent', targetHandle: 'input' },
      { source: 'batch', sourceHandle: 'summary', target: 'summary', targetHandle: 'value' },
      { source: 'agent', sourceHandle: 'output', target: 'result', targetHandle: 'value' },
    ],
  );
}

export const WORKFLOW_TEMPLATES: WorkflowTemplate[] = [
  { id: 'blank', name: 'Blank', description: 'A trigger and a result. Start here.', build: blank },
  { id: 'if-else', name: 'If / else', description: 'Branch on a value with control gates.', build: ifElse },
  { id: 'market-scan', name: 'Market scan', description: 'Stored bars → SMA → z-score → branch.', build: marketScan },
  { id: 'price-check', name: 'Price + indicator', description: 'Market data → SMA → branch.', build: priceCheck },
  { id: 'risk-snapshot', name: 'Risk snapshot', description: 'Daily bars → risk metrics → quote.', build: riskSnapshot },
  {
    id: 'derivatives-monitor',
    name: 'Derivatives monitor',
    description: 'Funding + open interest + liquidations.',
    build: derivativesMonitor,
  },
  { id: 'rates-check', name: 'FX + bond yield', description: 'FX pair and a government yield.', build: ratesCheck },
  {
    id: 'backtest-verdict',
    name: 'Backtest and grade',
    description: 'Bars → EMA-cross backtest → edge verdict (A–F).',
    build: backtestVerdict,
  },
  { id: 'http-fetch', name: 'HTTP request', description: 'Fetch an external endpoint.', build: httpFetch },
  { id: 'webhook-http', name: 'Webhook to HTTP', description: 'Signed inbound webhook → public API → result.', build: webhookHttp },
  { id: 'signed-webhook', name: 'Signed webhook', description: 'Manual trigger → signed outbound webhook.', build: signedWebhookDemo },
  { id: 'data-pipeline', name: 'Data pipeline', description: 'Six data nodes wired end to end.', build: dataPipeline },
  {
    id: 'candle-review',
    name: 'Candle option review',
    description: 'Read 1–8 candle images, then compare the readings with an agent.',
    build: candleReview,
  },
  {
    id: 'file-import',
    name: 'File import',
    description: 'Upload a file, parse it, select columns and return the rows.',
    build: fileImport,
  },
  {
    id: 'research-brief',
    name: 'Research brief',
    description: 'Stored run → evidence → conflict scan → citation audit → report.',
    build: researchBrief,
  },
];

export function buildTemplate(id: string): WorkflowIR | null {
  const template = WORKFLOW_TEMPLATES.find((t) => t.id === id);
  return template ? template.build() : null;
}
