// ── Config field presentation ────────────────────────────────────────────────
// The registry stores config schemas (validation) and defaults (shape) but no
// presentation metadata. This module is the ONE place that maps a config key to
// a label, editor kind and — for a small set of high-value keys — `inline: true`
// so the value can be edited directly on the canvas node.
//
// The map is keyed by node type and merged over the defaults-derived fallback,
// so every registered node keeps a complete Parameters tab even when it has no
// overrides. Presentation only: persisted config and semantics are untouched.

import type { ConfigFieldDef, NodeDefinition } from './types';

type Override = Omit<ConfigFieldDef, 'key'> & { key: string };

const opts = (...values: string[]): ConfigFieldDef['options'] =>
  values.map((value) => ({ value, label: value }));

const FIELD_OVERRIDES: Record<string, Override[]> = {
  'trigger.manual': [
    { key: 'seed', label: 'Seed', kind: 'text', inline: true, placeholder: 'e.g. AAPL' },
  ],
  'trigger.schedule': [
    { key: 'cron', label: 'Cron', kind: 'text', inline: true, placeholder: '0 9 * * 1-5' },
    { key: 'timezone', label: 'Timezone', kind: 'text', placeholder: 'UTC' },
  ],
  'data.value': [
    { key: 'value', label: 'Value', kind: 'text', inline: true },
    { key: 'dataType', label: 'Type', kind: 'select', inline: true, options: opts('string', 'number', 'boolean', 'object', 'array') },
  ],
  'data.set_variables': [
    { key: 'variables', label: 'Variables', kind: 'json' },
  ],
  'data.json.parse': [
    { key: 'strict', label: 'Strict', kind: 'boolean' },
  ],
  'data.dataset.save': [
    { key: 'name', label: 'Dataset name', kind: 'text', inline: true },
    { key: 'ttlHours', label: 'TTL (hours)', kind: 'number', min: 0 },
  ],
  'transform.template': [
    { key: 'template', label: 'Template', kind: 'text', inline: true, placeholder: '{{a}}' },
  ],
  'transform.formula': [
    { key: 'expression', label: 'Expression', kind: 'text', inline: true, placeholder: 'x' },
  ],
  'transform.select': [
    { key: 'fields', label: 'Fields', kind: 'text', inline: true, placeholder: 'a, b.c' },
    { key: 'rename', label: 'Rename', kind: 'json' },
  ],
  'transform.sort_limit': [
    { key: 'field', label: 'Field', kind: 'text', inline: true },
    { key: 'order', label: 'Order', kind: 'select', inline: true, options: opts('asc', 'desc') },
    { key: 'limit', label: 'Limit', kind: 'number', min: 0, max: 100_000 },
  ],
  'transform.join': [
    { key: 'leftKey', label: 'Left key', kind: 'text', inline: true },
    { key: 'rightKey', label: 'Right key', kind: 'text', inline: true },
    { key: 'how', label: 'Join', kind: 'select', options: opts('inner', 'left') },
  ],
  'logic.condition': [
    { key: 'operator', label: 'Operator', kind: 'select', inline: true, options: opts('eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'truthy') },
    { key: 'compareTo', label: 'Compare to', kind: 'text' },
  ],
  'logic.aggregate': [
    { key: 'field', label: 'Field', kind: 'text', inline: true },
    { key: 'op', label: 'Aggregate', kind: 'select', inline: true, options: opts('sum', 'avg', 'min', 'max', 'count') },
    { key: 'groupBy', label: 'Group by', kind: 'text' },
  ],
  'logic.deduplicate': [
    { key: 'keys', label: 'Keys', kind: 'text', inline: true, placeholder: 'id, symbol' },
  ],
  'logic.switch': [
    { key: 'cases', label: 'Cases', kind: 'text', inline: true, placeholder: 'a, b, c' },
  ],
  'logic.map': [
    { key: 'expression', label: 'Expression', kind: 'text', inline: true, placeholder: 'value' },
  ],
  'logic.filter': [
    { key: 'expression', label: 'Expression', kind: 'text', inline: true, placeholder: 'value != 0' },
  ],
  'logic.reduce': [
    { key: 'expression', label: 'Expression', kind: 'text', inline: true, placeholder: 'acc + value' },
    { key: 'initial', label: 'Initial', kind: 'number' },
  ],
  'logic.wait': [
    { key: 'ms', label: 'Wait (ms)', kind: 'number', inline: true, min: 0, max: 86_400_000 },
  ],
  'logic.stop': [
    { key: 'message', label: 'Message', kind: 'text', inline: true },
    { key: 'status', label: 'Status', kind: 'select', options: opts('succeeded', 'failed') },
  ],
  'integration.http': [
    { key: 'url', label: 'URL', kind: 'text', inline: true, placeholder: 'https://…' },
    { key: 'method', label: 'Method', kind: 'select', inline: true, options: opts('GET', 'POST', 'PUT', 'PATCH', 'DELETE') },
    { key: 'bodyJson', label: 'Body', kind: 'json' },
    { key: 'headersJson', label: 'Headers', kind: 'json' },
    { key: 'credentialEnvJson', label: 'Credentials (ENV names)', kind: 'json' },
    { key: 'timeoutMs', label: 'Timeout (ms)', kind: 'number', min: 1_000, max: 60_000 },
  ],
  'finance.quote': [
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'AAPL' },
    { key: 'market', label: 'Market', kind: 'text', placeholder: 'auto' },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'slow', 'any') },
  ],
  'finance.history': [
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'AAPL' },
    { key: 'interval', label: 'Interval', kind: 'select', inline: true, options: opts('1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1mo') },
    { key: 'market', label: 'Market', kind: 'text' },
    { key: 'start', label: 'Start', kind: 'text', placeholder: 'ISO date' },
    { key: 'end', label: 'End', kind: 'text', placeholder: 'ISO date' },
    { key: 'adjusted', label: 'Adjusted', kind: 'boolean' },
    { key: 'limit', label: 'Limit', kind: 'number', min: 0, max: 5_000 },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'slow', 'any') },
  ],
  'finance.market_data': [
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'AAPL' },
    { key: 'interval', label: 'Interval', kind: 'select', inline: true, options: opts('1m', '5m', '15m', '1h', '1d') },
    { key: 'lookback', label: 'Lookback bars', kind: 'number', min: 1, max: 5_000 },
  ],
  'video.render': [
    { key: 'title', label: 'Title', kind: 'text', inline: true },
    { key: 'mode', label: 'Mode', kind: 'select', inline: true, options: opts('draft', 'final') },
  ],
  'finance.indicator': [
    { key: 'kind', label: 'Indicator', kind: 'select', inline: true, options: opts('sma', 'ema', 'rsi', 'macd', 'atr', 'adx', 'vwap', 'bollinger') },
    { key: 'period', label: 'Period', kind: 'number', inline: true, min: 1, max: 500 },
    { key: 'fast', label: 'Fast', kind: 'number', min: 1, max: 500 },
    { key: 'slow', label: 'Slow', kind: 'number', min: 1, max: 500 },
    { key: 'signal', label: 'Signal', kind: 'number', min: 1, max: 500 },
  ],
  'quant.returns': [
    { key: 'kind', label: 'Returns', kind: 'select', inline: true, options: opts('simple', 'log') },
    { key: 'period', label: 'Period', kind: 'number', inline: true, min: 1, max: 500 },
  ],
  'quant.zscore': [
    { key: 'period', label: 'Period', kind: 'number', inline: true, min: 2, max: 500 },
  ],
  'quant.volatility': [
    { key: 'period', label: 'Period', kind: 'number', inline: true, min: 2, max: 500 },
    { key: 'annualize', label: 'Annualize', kind: 'boolean', inline: true },
    { key: 'periodsPerYear', label: 'Periods / year', kind: 'number', min: 1, max: 1_000 },
  ],
  'agent.research': [
    { key: 'objective', label: 'Objective', kind: 'text', inline: true },
    { key: 'agent', label: 'Agent', kind: 'text' },
    { key: 'maxSteps', label: 'Max steps', kind: 'number', min: 1, max: 32 },
  ],
  'agent.plan': [
    { key: 'objective', label: 'Objective', kind: 'text', inline: true },
  ],
  'agent.delegate': [
    { key: 'agent', label: 'Agent', kind: 'text', inline: true },
    { key: 'tasksJson', label: 'Tasks', kind: 'json' },
    { key: 'maxSteps', label: 'Max steps', kind: 'number', min: 1, max: 32 },
    { key: 'maxTasks', label: 'Max tasks', kind: 'number', min: 1, max: 6 },
  ],
  'research.evidence': [
    { key: 'researchId', label: 'Research id', kind: 'text', inline: true },
    { key: 'query', label: 'Query', kind: 'text', inline: true },
    { key: 'limit', label: 'Limit', kind: 'number', min: 1, max: 1_000 },
  ],
  'research.citations': [
    { key: 'researchId', label: 'Research id', kind: 'text', inline: true },
    { key: 'limit', label: 'Limit', kind: 'number', min: 1, max: 1_000 },
  ],
  'research.conflicts': [
    { key: 'researchId', label: 'Research id', kind: 'text', inline: true },
    { key: 'limit', label: 'Limit', kind: 'number', min: 1, max: 1_000 },
  ],
  'research.completeness': [
    { key: 'researchId', label: 'Research id', kind: 'text', inline: true },
  ],
  'research.report': [
    { key: 'researchId', label: 'Research id', kind: 'text', inline: true },
  ],
  'research.web_search': [
    { key: 'query', label: 'Query', kind: 'text', inline: true },
    { key: 'limit', label: 'Results', kind: 'number', inline: true, min: 1, max: 15 },
    { key: 'domains', label: 'Include domains', kind: 'json' },
    { key: 'excludeDomains', label: 'Exclude domains', kind: 'json' },
  ],
  'research.web_fetch': [
    { key: 'url', label: 'URL', kind: 'text', inline: true, placeholder: 'https://…' },
    { key: 'researchId', label: 'Research id', kind: 'text' },
    { key: 'maxChars', label: 'Max chars', kind: 'number', min: 500, max: 100_000 },
    { key: 'allowBrowser', label: 'Allow browser', kind: 'boolean' },
  ],
  'research.web_crawl': [
    { key: 'url', label: 'Start URL', kind: 'text', inline: true, placeholder: 'https://…' },
    { key: 'maxPages', label: 'Max pages', kind: 'number', min: 1, max: 10 },
    { key: 'maxChars', label: 'Max chars / page', kind: 'number', min: 500, max: 100_000 },
    { key: 'sameDomain', label: 'Same domain', kind: 'boolean' },
  ],
  'research.claim_verify': [
    { key: 'claim', label: 'Claim', kind: 'text', inline: true },
    { key: 'researchId', label: 'Research id', kind: 'text' },
    { key: 'evidenceIds', label: 'Evidence ids', kind: 'json' },
  ],
  'trading.risk_check': [
    { key: 'equity', label: 'Equity', kind: 'number', inline: true, min: 1 },
    { key: 'price', label: 'Price', kind: 'number', min: 0 },
    { key: 'maxPositionPct', label: 'Max position %', kind: 'number', min: 0, max: 100 },
    { key: 'maxLeverage', label: 'Max leverage', kind: 'number', min: 0, max: 100 },
    { key: 'requireStop', label: 'Require stop', kind: 'boolean' },
  ],
  'trading.paper_order': [
    { key: 'price', label: 'Price', kind: 'number', inline: true, min: 0 },
    { key: 'accountId', label: 'Paper account', kind: 'text', inline: true },
    { key: 'initialCash', label: 'Initial cash', kind: 'number', min: 0 },
    { key: 'commissionPct', label: 'Commission %', kind: 'number', min: 0, max: 10 },
    { key: 'slippagePct', label: 'Slippage %', kind: 'number', min: 0, max: 10 },
    { key: 'persist', label: 'Persist fill', kind: 'boolean' },
  ],
  'output.result': [
    { key: 'label', label: 'Result label', kind: 'text', inline: true },
  ],
};

function inferKind(value: unknown): ConfigFieldDef['kind'] {
  if (typeof value === 'boolean') return 'boolean';
  if (typeof value === 'number') return 'number';
  if (value && typeof value === 'object') return 'json';
  return 'text';
}

function humanize(key: string): string {
  return key
    .replace(/([a-z0-9])([A-Z])/g, '$1 $2')
    .replace(/[_-]+/g, ' ')
    .replace(/^./, (char) => char.toUpperCase());
}

const cache = new WeakMap<NodeDefinition, ConfigFieldDef[]>();

function buildFields(def: NodeDefinition): ConfigFieldDef[] {
  const defaults = def.defaultConfig();
  const overrides = new Map((FIELD_OVERRIDES[def.type] ?? []).map((field) => [field.key, field]));
  const keys = [...Object.keys(defaults)];
  for (const key of overrides.keys()) {
    if (!keys.includes(key)) keys.push(key);
  }
  const fields = keys.map((key): ConfigFieldDef => {
    const base: ConfigFieldDef = {
      key,
      label: humanize(key),
      kind: inferKind(defaults[key]),
    };
    const override = overrides.get(key);
    return override ? { ...base, ...override } : base;
  });
  // JSON/object editing stays in the inspector; the card only carries scalar
  // values. Keep the declared order so the two inline slots are deterministic.
  return fields;
}

/** All fields for a definition, in stable order (cached per definition). */
export function fieldsFor(def: NodeDefinition): ConfigFieldDef[] {
  const cached = cache.get(def);
  if (cached) return cached;
  const fields = buildFields(def);
  cache.set(def, fields);
  return fields;
}

const inlineCache = new WeakMap<NodeDefinition, ConfigFieldDef[]>();

/** The scalar fields rendered directly on the canvas node (max two). */
export function inlineFieldsFor(def: NodeDefinition | undefined): ConfigFieldDef[] {
  if (!def) return EMPTY;
  const cached = inlineCache.get(def);
  if (cached) return cached;
  const fields = fieldsFor(def)
    .filter((field) => field.inline && field.kind !== 'json')
    .slice(0, 2);
  inlineCache.set(def, fields);
  return fields;
}

const EMPTY: ConfigFieldDef[] = [];
