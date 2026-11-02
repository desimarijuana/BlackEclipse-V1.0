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
import { MEMORY_TYPES } from './registry-utility';

type Override = Omit<ConfigFieldDef, 'key'> & { key: string };

const opts = (...values: string[]): ConfigFieldDef['options'] =>
  values.map((value) => ({ value, label: value }));

/** Bar intervals the quant pack accepts (resample + benchmark annualization). */
const QUANT_INTERVALS = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1mo'];

/** One-line explanations shared by every node that uses the key. */
const KEY_HELP: Record<string, string> = {

  objective: 'What the agent should do. A wired query overrides this.',
  agent: 'Agent preset id. Pick a built-in or a preset from Settings › Agents.',
  botId: 'Saved bot to run. The graph resolves it at run time; a deleted bot fails by name.',
  agentVersion: '0 uses the preset’s current version; a positive value pins a snapshot.',
  maxSteps: 'Maximum model turns for one bounded run.',
  maxTasks: 'Maximum delegated tasks (1–6).',
  tasksJson: 'JSON array of tasks, used when no tasks wire is connected.',
  connectionId: 'Saved broker connection used for this node.',
  mandateId: 'Active mandate that authorizes this order or unattended run.',
  scope: 'Named write scope configured by the operator.',
  path: 'Relative path inside the selected scope.',
  append: 'Append to the existing file instead of replacing it.',
  workflowId: 'Saved workflow used as the loop body or subworkflow.',
  version: 'Pinned version of the referenced workflow.',
  condition: 'Safe formula over value, index and iterations.',
  maxIterations: 'Hard stop on loop iterations (1–1000).',
  maxDurationMs: 'Optional wall-clock cap in milliseconds (0 = none).',
  count: 'How many times the body runs.',
  timezone: 'IANA timezone, e.g. UTC or America/New_York.',
  cron: 'Five-field cron expression, e.g. 0 9 * * 1-5.',
  symbol: 'Instrument symbol, e.g. AAPL or EURUSD.',
  interval: 'Bar interval used for the series.',
  lookback: 'How many bars or series points to read.',
  period: 'Indicator lookback period.',
  expression: 'Safe arithmetic expression (no eval).',
  template: 'Text template; use {{name}} placeholders.',
  timeoutMs: 'Maximum time for this node’s work.',
  freshness: 'Data freshness requirement.',
  limit: 'Maximum number of rows/items returned.',
  preset: 'Preset strategy. A custom strategy JSON overrides the preset.',
  fast: 'Fast moving-average period.',
  slow: 'Slow moving-average period.',
  sizePct: 'Percent of equity committed to each entry.',
  stopPct: 'Initial stop distance as a percent of entry price.',
  reward: 'Take-profit multiple of the stop distance.',
  initialCapital: 'Starting equity for the simulation.',
  randomSeed: 'Same seed and data produce the same result.',
  maxBars: 'Cap the number of bars used (0 = all).',
  includeSeries: 'Include equity/trade curves in the result payload.',
  strategyJson: 'Optional full StrategySpec JSON; overrides the preset.',
  paramSpaceJson: 'Optional parameter grid/search space as JSON.',
  method: 'Optimization or simulation method.',
  simulations: 'Number of Monte Carlo paths.',
  ruinThreshold: 'Equity fraction that counts as ruin (0–1).',
  oosFraction: 'Fraction of bars held out for out-of-sample testing.',
  targetInterval: 'Interval to aggregate the bars up to (never finer than the source).',
  sourceInterval: 'Interval of the incoming bars; blank reads it from the series payload.',
  assetClass: 'Annualization convention: equities use ~252 sessions, crypto 365.',
  minTrades: 'Closed trades needed before an edge can be told apart from luck.',
  goodTrades: 'Trade count that earns a full sample score.',
  highProbabilityOfLoss: 'Monte Carlo loss probability (%) that raises a warning.',
  confidence: 'Confidence level (0–1) for a bootstrap or historical VaR/CVaR.',
  trainBars: 'Bars per training window.',
  testBars: 'Bars per test window.',
  stepBars: 'Bars to advance between windows.',
  dataType: 'How the literal is converted before it leaves the node.',
  strict: 'Reject invalid JSON instead of passing the raw text through.',
  ttlHours: 'Optional expiry for the stored dataset (0 = no expiry).',
  variables: 'Named values merged over an optional input object.',
  adjusted: 'Use split/dividend-adjusted prices.',
  start: 'Optional ISO start date.',
  end: 'Optional ISO end date.',
  market: 'Optional market override; empty = auto-detect.',
  compareTo: 'Value to compare against (ignored by truthy).',
  operator: 'Comparison operator.',
  field: 'Dotted field path inside each object.',
  groupBy: 'Optional dotted field to group rows by.',
  op: 'Aggregate operation.',
  keys: 'Comma-separated fields that define a duplicate.',
  leftKey: 'Dotted key on the left rows; comma-separate for a composite key.',
  rightKey: 'Dotted key on the right rows; defaults to the left key.',
  onMissing: 'What a selected field that does not exist should do.',
  offset: 'Rows to skip before taking the limit.',
  onDuplicate: 'What to do when several right rows share a key.',
  caseInsensitive: 'Match text keys without regard to case.',
  suffix: 'Suffix for right-side columns whose name collides with a left column.',
  cases: 'Comma-separated values; a matching case fires its control output.',
  message: 'Optional message emitted when the run stops.',
  status: 'Status to record when the run stops.',
  ms: 'Pause duration in milliseconds (bounded).',
  label: 'Display label for the result.',
  closeAll: 'Close every open position on the connection.',
  deviation: 'Maximum price deviation in points.',
  continueOnError: 'Keep looping when one iteration fails.',
  depth: 'Levels of book depth to request.',
  window: 'Aggregation window, e.g. 1d or 24h.',
  exchange: 'Optional exchange or venue filter; empty = the gateway default.',
  expiration: 'Optional expiration (YYYY-MM-DD); empty = the nearest listed.',
  greeks: 'Calculate Black-Scholes Greeks when the provider does not supply them.',
  seriesType: 'Optional bond series type, e.g. treasury or corporate.',
  chain: 'Protocol/chain name, or an EVM chain for an address.',
  address: 'Account address to inspect.',
  history: 'Historical funding points to return (0 = current only).',
  base: 'Base currency of the FX pair.',
  quote: 'Quote currency of the FX pair.',
  inputKind: 'How the incoming series is interpreted before the math runs.',
  periodsPerYear: 'Annualization factor (252 trading days by default).',
};

/** A stable section for fields that otherwise have no explicit override. */
const GROUP_BY_KEY: Record<string, string> = {
  connectionId: 'Connection',
  mandateId: 'Connection',
  workflowId: 'Body workflow',
  version: 'Body workflow',
  agent: 'Agent',
  agentVersion: 'Agent',
  objective: 'Agent',
  maxSteps: 'Agent',
  maxTasks: 'Agent',
  tasksJson: 'Agent',
  url: 'Request',
  method: 'Request',
  queryJson: 'Request',
  headersJson: 'Request',
  bodyJson: 'Body',
  bodyMode: 'Body',
  credentialEnvJson: 'Auth',
  secretEnv: 'Auth',
  deliveryId: 'Advanced',
  responseType: 'Response',
  maxResponseBytes: 'Response',
  onOversize: 'Response',
  failOnHttpError: 'Response',
  followRedirects: 'Advanced',
  maxRedirects: 'Advanced',
  retries: 'Advanced',
  retryBackoffMs: 'Advanced',
  retryUnsafe: 'Advanced',
  timeoutMs: 'Request',
  maxPositionPct: 'Risk limits',
  maxGrossExposure: 'Risk limits',
  maxLeverage: 'Risk limits',
  maxOpenPositions: 'Risk limits',
  maxDailyLossPct: 'Risk limits',
  maxRiskPerTradePct: 'Risk limits',
  requireStop: 'Risk limits',
  allowLong: 'Risk limits',
  allowShort: 'Risk limits',
  initialCapital: 'Risk & costs',
  sizePct: 'Risk & costs',
  stopPct: 'Risk & costs',
  reward: 'Risk & costs',
  riskFreeRate: 'Risk & costs',
  fast: 'Strategy',
  slow: 'Strategy',
  rsiPeriod: 'Strategy',
  oversold: 'Strategy',
  overbought: 'Strategy',
  atrPeriod: 'Strategy',
  atrMult: 'Strategy',
  preset: 'Strategy',
  strategyJson: 'Strategy',
  randomSeed: 'Advanced',
  maxBars: 'Advanced',
  includeSeries: 'Advanced',
};

/** Parameters the inspector marks with a required asterisk. */
const REQUIRED_FIELDS: Record<string, string[]> = {
  'file.write': ['path'],
  'flow.for_each': ['workflowId'],
  'flow.repeat': ['workflowId'],
  'flow.while': ['workflowId'],
  'flow.subworkflow': ['workflowId'],
  'trading.broker_order': ['connectionId', 'mandateId'],
  'trading.order_preview': ['connectionId'],
  'trading.broker_account': ['connectionId'],
  'trading.broker_positions': ['connectionId'],
  'trading.broker_orders': ['connectionId'],
  'trading.broker_fills': ['connectionId'],
  'trading.broker_quote': ['connectionId'],
  'trading.broker_bars': ['connectionId'],
  'trading.broker_close': ['connectionId'],
  'trading.broker_modify': ['connectionId'],
  'trading.broker_cancel': ['connectionId'],
  'integration.http': ['url'],
  'integration.webhook_send': ['url', 'secretEnv'],
};

// Shared quant parameter presentation. Every quant node reuses the same
// strategy/risk vocabulary, so one definition keeps the labels consistent.
const quantInstrument: Override[] = [
  { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, group: 'Instrument & series', placeholder: 'AAPL' },
  { key: 'interval', label: 'Interval', kind: 'select', inline: true, group: 'Instrument & series', options: opts('1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1mo') },
];
const quantStrategy: Override[] = [
  { key: 'preset', label: 'Strategy preset', kind: 'select', inline: true, group: 'Strategy', options: opts('ema_cross', 'rsi_reversion') },
  { key: 'fast', label: 'Fast EMA', kind: 'number', group: 'Strategy', min: 2, max: 500 },
  { key: 'slow', label: 'Slow EMA', kind: 'number', group: 'Strategy', min: 2, max: 2_000 },
  { key: 'rsiPeriod', label: 'RSI period', kind: 'number', group: 'Strategy', min: 2, max: 500 },
  { key: 'oversold', label: 'Oversold level', kind: 'number', group: 'Strategy', min: 0, max: 100 },
  { key: 'overbought', label: 'Overbought level', kind: 'number', group: 'Strategy', min: 0, max: 100 },
  { key: 'atrPeriod', label: 'ATR period', kind: 'number', group: 'Strategy', min: 2, max: 500 },
  { key: 'atrMult', label: 'ATR multiple', kind: 'number', group: 'Strategy', min: 0, max: 100 },
  { key: 'strategyJson', label: 'Custom strategy (JSON)', kind: 'json', group: 'Strategy', help: 'A full StrategySpec. Leave empty to use the preset.' },
];
const quantRisk: Override[] = [
  { key: 'initialCapital', label: 'Initial capital', kind: 'number', group: 'Risk & costs', min: 1 },
  { key: 'sizePct', label: 'Position size %', kind: 'number', group: 'Risk & costs', min: 1, max: 100 },
  { key: 'stopPct', label: 'Stop loss %', kind: 'number', group: 'Risk & costs', min: 0, max: 100 },
  { key: 'reward', label: 'Reward : risk', kind: 'number', group: 'Risk & costs', min: 0, max: 100 },
  { key: 'riskFreeRate', label: 'Risk-free rate', kind: 'number', group: 'Risk & costs' },
];
const quantAdvanced: Override[] = [
  { key: 'randomSeed', label: 'Random seed', kind: 'number', group: 'Advanced' },
  { key: 'maxBars', label: 'Max bars (0 = all)', kind: 'number', group: 'Advanced', min: 0 },
  { key: 'includeSeries', label: 'Include series curves', kind: 'boolean', group: 'Advanced' },
  { key: 'objective', label: 'Objective', kind: 'select', group: 'Advanced', options: opts('sharpe', 'sortino', 'total_return', 'calmar', 'profit_factor') },
  { key: 'method', label: 'Method', kind: 'select', group: 'Advanced', options: opts('grid', 'random', 'evolutionary', 'bayesian', 'trade_reshuffle', 'return_bootstrap', 'regime_block') },
  { key: 'maxEvaluations', label: 'Max evaluations', kind: 'number', group: 'Advanced', min: 1 },
  { key: 'paramSpaceJson', label: 'Parameter space (JSON)', kind: 'json', group: 'Advanced' },
  { key: 'objectivesJson', label: 'Objectives (JSON)', kind: 'json', group: 'Advanced' },
  { key: 'leaderboardSize', label: 'Leaderboard size', kind: 'number', group: 'Advanced', min: 1 },
  { key: 'trainBars', label: 'Train bars', kind: 'number', group: 'Advanced', min: 1 },
  { key: 'testBars', label: 'Test bars', kind: 'number', group: 'Advanced', min: 1 },
  { key: 'stepBars', label: 'Step bars', kind: 'number', group: 'Advanced', min: 1 },
  { key: 'anchored', label: 'Anchored windows', kind: 'boolean', group: 'Advanced' },
  { key: 'simulations', label: 'Simulations', kind: 'number', group: 'Advanced', min: 1 },
  { key: 'ruinThreshold', label: 'Ruin threshold', kind: 'number', group: 'Advanced', min: 0, max: 1, step: 0.01 },
  { key: 'regimeMix', label: 'Regime mix', kind: 'select', group: 'Advanced', options: opts('resample', 'preserve') },
  { key: 'regimeBlockLength', label: 'Regime block length', kind: 'number', group: 'Advanced', min: 1 },
  { key: 'perturbationPct', label: 'Perturbation %', kind: 'number', group: 'Advanced', min: 0, max: 100, step: 0.1 },
  { key: 'perturbationJson', label: 'Perturbation (JSON)', kind: 'json', group: 'Advanced' },
  { key: 'executionPerturbationJson', label: 'Execution perturbation (JSON)', kind: 'json', group: 'Advanced' },
  { key: 'oosFraction', label: 'OOS fraction', kind: 'number', group: 'Advanced', min: 0, max: 1, step: 0.01 },
  { key: 'oosStartIndex', label: 'OOS start index', kind: 'number', group: 'Advanced', min: 0 },
  { key: 'bootstrapIterations', label: 'Bootstrap iterations', kind: 'number', group: 'Advanced', min: 1 },
  { key: 'confidence', label: 'Confidence', kind: 'number', group: 'Advanced', min: 0, max: 1, step: 0.01 },
];

const pickQuantAdvanced = (...keys: string[]): Override[] =>
  quantAdvanced.filter((field) => keys.includes(field.key));

const FIELD_OVERRIDES: Record<string, Override[]> = {
  // trigger.manual is deliberately zero-config (n8n-style): Start is the run
  // input or null. Stored defaults belong in data.value / data.set_variables.
  // trigger.schedule is zero-config; its schedule is edited in the Schedule tab.
  'data.value': [
    { key: 'value', label: 'Value', kind: 'textarea', inline: true, help: 'A literal. Object/array types accept JSON; a wired input overrides it.' },
    { key: 'dataType', label: 'Type', kind: 'select', inline: true, options: opts('string', 'number', 'boolean', 'object', 'array') },
  ],
  'data.set_variables': [
    { key: 'variables', label: 'Variables', kind: 'keyvalue', help: 'Named values merged over the input object. Configured keys win.' },
  ],
  'data.json.parse': [
    { key: 'text', label: 'JSON text', kind: 'code', help: 'Used when the Text port is not wired. The wire wins when connected.' },
    { key: 'strict', label: 'Strict', kind: 'boolean', help: 'Reject invalid JSON instead of passing the raw text through.' },
  ],
  'trading.broker_order': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'mandateId', label: 'Mandate (live/paper)', kind: 'text' },
    { key: 'dryRun', label: 'Dry run (preview only)', kind: 'boolean', help: 'Sends nothing and creates no approval; `ok` then means the order would be allowed.' },
  ],
  'trading.order_preview': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'mandateId', label: 'Mandate (optional)', kind: 'text', help: 'Also check the mandate scope. Verifying does not consume a use.' },
  ],
  'trading.order_intent': [
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'EURUSD' },
    { key: 'side', label: 'Side', kind: 'select', inline: true, options: opts('buy', 'sell') },
    { key: 'orderType', label: 'Order type', kind: 'select', inline: true, options: opts('market', 'limit', 'stop') },
    { key: 'quantity', label: 'Quantity', kind: 'number', min: 0, help: 'Wired values win over these.' },
    { key: 'price', label: 'Order price', kind: 'number', min: 0, help: 'Required for a limit or stop order.' },
    { key: 'stopLoss', label: 'Stop loss', kind: 'number', min: 0, inline: true },
    { key: 'takeProfit', label: 'Take profit', kind: 'number', min: 0, inline: true },
    { key: 'timeInForce', label: 'Time in force', kind: 'select', options: opts('gtc', 'day') },
  ],
  'trading.paper_account': [
    { key: 'accountId', label: 'Paper account', kind: 'text', inline: true },
    { key: 'initialCash', label: 'Initial cash', kind: 'number', min: 0 },
  ],
  'trading.broker_account': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
  ],
  'trading.broker_positions': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
  ],
  'trading.broker_orders': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
  ],
  'trading.broker_fills': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'limit', label: 'Max fills', kind: 'number', min: 1, max: 200 },
  ],
  'trading.order_ledger': [
    { key: 'connectionId', label: 'Broker connection (optional)', kind: 'text' },
    { key: 'limit', label: 'Max rows', kind: 'number', min: 1, max: 200 },
  ],
  'trading.broker_quote': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'XAUUSD' },
  ],
  'trading.broker_bars': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'XAUUSD' },
    { key: 'timeframe', label: 'Timeframe', kind: 'select', options: opts('M1', 'M5', 'M15', 'M30', 'H1', 'H4', 'D1', 'W1') },
    { key: 'count', label: 'Bars', kind: 'number', min: 1, max: 500 },
  ],
  'trading.broker_close': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'symbol', label: 'Symbol (close all in it)', kind: 'text', inline: true, placeholder: 'XAUUSD' },
    { key: 'closeAll', label: 'Close all positions', kind: 'boolean' },
    { key: 'deviation', label: 'Deviation (points)', kind: 'number', min: 0, max: 1_000 },
  ],
  'trading.broker_modify': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
  ],
  'trading.broker_cancel': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
  ],
  'file.write': [
    { key: 'path', label: 'Path (relative)', kind: 'text', inline: true, placeholder: 'reports/aapl.csv', help: 'Relative to the scope root; ".." and absolute paths are refused.' },
    { key: 'scope', label: 'Write scope', kind: 'combobox', options: opts('workspace'), placeholder: 'workspace', help: 'A named scope the operator granted for this run.' },
    { key: 'append', label: 'Append', kind: 'boolean', help: 'Append instead of replacing the file.' },
  ],
  'data.dataset.save': [
    { key: 'name', label: 'Dataset name', kind: 'combobox', inline: true, placeholder: 'bars', help: 'A label for the stored payload; the ref is returned by the node.' },
    { key: 'ttlHours', label: 'TTL (hours)', kind: 'number', min: 0, max: 8_760, help: '0 means no expiry. Stored datasets are local scratch, not market data.' },
    { key: 'valueJson', label: 'Payload (JSON)', kind: 'code', help: 'Used when the Value port is not wired. The wire wins when connected.' },
  ],
  'data.dataset.load': [
    { key: 'ref', label: 'Dataset ref', kind: 'text', placeholder: 'gds:…', help: 'Pick a saved dataset above, or paste a ref. A wired Ref port wins.' },
  ],
  'transform.template': [
    {
      key: 'template',
      label: 'Template',
      kind: 'textarea',
      placeholder: '{{a}}',
      help: '{{a}} · {{a.price}} dotted path · {{a.price:.2f}} number format · {{a.ts:date:%Y-%m-%d}} · {{a?}} renders blank when null. Rows: {{#each a}}{{symbol}}{{/each}} — inside a block {{this}} and {{index}} work too, and \\{{ is a literal brace.',
    },
  ],
  'transform.formula': [
    {
      key: 'expression',
      label: 'Expression',
      kind: 'text',
      inline: true,
      placeholder: 'x',
      help: 'x and y are the wired inputs (a series resolves to its latest value). if(cond,a,b), div(a,b,fallback), nz, clamp, round (half-up), min, max, abs, sqrt, log, sign.',
    },
  ],
  'transform.select': [
    {
      key: 'fields',
      label: 'Fields',
      kind: 'text',
      inline: true,
      placeholder: 'symbol, pe=fundamentals.pe',
      help: 'Comma-separated dotted paths. `pe=fundamentals.pe` renames on the way out. Empty keeps every column.',
    },
    { key: 'rename', label: 'Rename', kind: 'keyvalue', jsonString: true, help: 'Old → new column names, applied after selection.' },
    {
      key: 'onMissing',
      label: 'Missing field',
      kind: 'select',
      options: opts('null', 'drop', 'error'),
      help: 'null: emit a null column · drop: drop the row · error: fail the node.',
    },
  ],
  'transform.sort_limit': [
    {
      key: 'field',
      label: 'Sort keys',
      kind: 'text',
      inline: true,
      placeholder: 'date desc, symbol',
      help: 'One or more dotted keys; append asc/desc per key. Numeric strings sort as numbers and nulls always sort last.',
    },
    { key: 'order', label: 'Default order', kind: 'select', inline: true, options: opts('asc', 'desc') },
    { key: 'limit', label: 'Limit (0 = all)', kind: 'number', min: 0, max: 100_000 },
    { key: 'offset', label: 'Offset', kind: 'number', min: 0, max: 100_000 },
    { key: 'caseInsensitive', label: 'Ignore key case', kind: 'boolean' },
  ],
  'transform.join': [
    {
      key: 'leftKey',
      label: 'Left key(s)',
      kind: 'text',
      inline: true,
      placeholder: 'symbol, date',
      help: 'Comma-separated for a composite key.',
    },
    { key: 'rightKey', label: 'Right key(s)', kind: 'text', inline: true, placeholder: 'symbol, date' },
    {
      key: 'how',
      label: 'Join',
      kind: 'select',
      options: opts('inner', 'left', 'right', 'full', 'anti'),
      help: 'anti keeps left rows with no match.',
    },
    {
      key: 'onDuplicate',
      label: 'Duplicate right keys',
      kind: 'select',
      options: opts('first', 'last', 'all'),
      help: 'first/last keep one row per key; all emits every match (bounded by 100 000 rows).',
    },
    { key: 'caseInsensitive', label: 'Ignore key case', kind: 'boolean' },
    {
      key: 'suffix',
      label: 'Right column suffix',
      kind: 'text',
      placeholder: '_right',
      help: 'Keep colliding right columns (close_right) instead of letting the left value win.',
    },
  ],
  'logic.condition': [
    { key: 'operator', label: 'Operator', kind: 'select', inline: true, quick: 1, options: opts('eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'truthy') },
    { key: 'compareTo', label: 'Compare to', kind: 'text', quick: 2 },
  ],
  'logic.aggregate': [
    { key: 'field', label: 'Field', kind: 'text', inline: true },
    {
      key: 'op',
      label: 'Aggregate',
      kind: 'select',
      inline: true,
      options: opts('sum', 'avg', 'min', 'max', 'count', 'median', 'stddev', 'percentile'),
    },
    { key: 'groupBy', label: 'Group by', kind: 'text' },
    {
      key: 'percentile',
      label: 'Percentile',
      kind: 'number',
      min: 0,
      max: 100,
      help: 'Only used by the percentile op. 50 is the median; 95 is the usual tail cut.',
    },
  ],
  'logic.deduplicate': [
    { key: 'keys', label: 'Keys', kind: 'text', inline: true, placeholder: 'id, symbol' },
    { key: 'keep', label: 'Keep', kind: 'select', inline: true, options: opts('first', 'last') },
    { key: 'caseInsensitive', label: 'Ignore key case', kind: 'boolean' },
  ],
  'flow.gate': [
    {
      key: 'require',
      label: 'Require',
      kind: 'select',
      inline: true,
      options: opts('any', 'all'),
      help: 'any: runs when a control input fires · all: every wired control input must fire (a join).',
    },
  ],
  'logic.merge': [
    {
      key: 'strategy',
      label: 'Strategy',
      kind: 'select',
      inline: true,
      options: [
        { value: 'first_present', label: 'First present' },
        { value: 'object', label: 'Object { a, b }' },
        { value: 'first', label: 'First present (legacy name)' },
      ],
      help: 'A branch is present unless it is null or empty, so an empty A does not shadow a populated B.',
    },
  ],
  'logic.switch': [
    {
      key: 'cases',
      label: 'Cases (one output each)',
      kind: 'text',
      inline: true,
      placeholder: 'buy, sell, hold',
      help: 'Values in order: case 1 is the first output, case 2 the second, and so on. Anything unmatched uses Default. Use a JSON array (["a,b", "c"]) when a value itself contains a comma.',
    },
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
    {
      key: 'status',
      label: 'Status',
      kind: 'select',
      options: opts('succeeded', 'failed'),
      help: 'Failed fails the whole run with this message; succeeded ends it cleanly.',
    },
  ],
  'integration.http': [
    { key: 'url', label: 'URL', kind: 'text', inline: true, placeholder: 'https://…' },
    { key: 'method', label: 'Method', kind: 'select', inline: true, options: opts('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'HEAD', 'OPTIONS') },
    { key: 'bodyJson', label: 'Body', kind: 'json' },
    { key: 'headersJson', label: 'Headers', kind: 'json' },
    { key: 'credentialEnvJson', label: 'Credentials (ENV names)', kind: 'json' },
    { key: 'timeoutMs', label: 'Timeout (ms)', kind: 'number', min: 1_000, max: 60_000 },
  ],
  // `1.1.0` extras. The type-level overrides above still apply; these add the
  // controls that version introduced without showing them on a saved 1.0.0 node.
  'integration.http@1.1.0': [
    { key: 'queryJson', label: 'Query params (JSON)', kind: 'json', group: 'Request' },
    { key: 'bodyMode', label: 'Body format', kind: 'select', options: opts('json', 'text', 'form'), group: 'Body' },
    { key: 'responseType', label: 'Parse response as', kind: 'select', options: opts('auto', 'json', 'text'), group: 'Response' },
    { key: 'maxResponseBytes', label: 'Max response bytes', kind: 'number', min: 1_000, max: 10_000_000, group: 'Response' },
    { key: 'onOversize', label: 'If response is too big', kind: 'select', options: opts('error', 'truncate'), group: 'Response' },
    { key: 'failOnHttpError', label: 'Fail on 4xx/5xx', kind: 'boolean', group: 'Response' },
    { key: 'followRedirects', label: 'Follow redirects', kind: 'boolean', group: 'Advanced', help: 'Every hop is SSRF-checked; HTTPS cannot downgrade to HTTP.' },
    { key: 'maxRedirects', label: 'Max redirects', kind: 'number', min: 0, max: 5, group: 'Advanced' },
    { key: 'retries', label: 'Retries', kind: 'number', min: 0, max: 3, group: 'Advanced', help: 'Only network errors, 408, 429 and 5xx are retried.' },
    { key: 'retryBackoffMs', label: 'Retry backoff (ms)', kind: 'number', min: 100, max: 10_000, group: 'Advanced' },
    { key: 'retryUnsafe', label: 'Retry POST/PATCH', kind: 'boolean', group: 'Advanced' },
  ],
  'integration.webhook_send': [
    { key: 'url', label: 'URL', kind: 'text', inline: true, placeholder: 'https://…' },
    { key: 'secretEnv', label: 'Signing secret (ENV name)', kind: 'text', inline: true, placeholder: 'WEBHOOK_SECRET' },
    { key: 'bodyJson', label: 'Body', kind: 'json' },
    { key: 'headersJson', label: 'Extra headers', kind: 'json' },
    { key: 'deliveryId', label: 'Delivery id', kind: 'text', placeholder: 'auto' },
    { key: 'failOnHttpError', label: 'Fail on 4xx/5xx', kind: 'boolean' },
    { key: 'retries', label: 'Retries', kind: 'number', min: 0, max: 3 },
    { key: 'retryBackoffMs', label: 'Retry backoff (ms)', kind: 'number', min: 100, max: 10_000 },
    { key: 'maxResponseBytes', label: 'Max response bytes', kind: 'number', min: 1_000, max: 10_000_000 },
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
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, quick: 1, placeholder: 'AAPL' },
    { key: 'interval', label: 'Interval', kind: 'select', inline: true, quick: 2, options: opts('1m', '5m', '15m', '1h', '1d') },
    { key: 'lookback', label: 'Lookback bars', kind: 'number', min: 1, max: 5_000 },
  ],
  'finance.instrument': [
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'AAPL' },
    { key: 'market', label: 'Market', kind: 'text', placeholder: 'auto' },
  ],
  'finance.orderbook': [
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'BTC-USD' },
    { key: 'depth', label: 'Depth', kind: 'number', inline: true, min: 1, max: 200 },
    { key: 'market', label: 'Market', kind: 'text' },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'daily', 'slow', 'any') },
  ],
  'finance.trades': [
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'AAPL' },
    { key: 'limit', label: 'Trades', kind: 'number', inline: true, min: 1, max: 1_000 },
    { key: 'market', label: 'Market', kind: 'text' },
    { key: 'start', label: 'Start', kind: 'text', placeholder: 'ISO date' },
    { key: 'end', label: 'End', kind: 'text', placeholder: 'ISO date' },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'daily', 'slow', 'any') },
  ],
  'finance.volume': [
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'AAPL' },
    { key: 'window', label: 'Window', kind: 'text', inline: true, placeholder: '1d' },
    { key: 'market', label: 'Market', kind: 'text' },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'daily', 'slow', 'any') },
  ],
  'finance.market_cap': [
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'AAPL' },
    { key: 'market', label: 'Market', kind: 'text' },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'daily', 'slow', 'any') },
  ],
  'finance.fx_rate': [
    { key: 'symbol', label: 'Pair', kind: 'text', inline: true, placeholder: 'EURUSD', help: 'A pair such as EURUSD. Leave empty to use Base + Quote.' },
    { key: 'base', label: 'Base', kind: 'text', inline: true, placeholder: 'EUR', help: 'Base currency; requires Quote when no pair is set.' },
    { key: 'quote', label: 'Quote', kind: 'text', placeholder: 'USD', help: 'Quote currency; requires Base when no pair is set.' },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'daily', 'slow', 'any') },
  ],
  'finance.options_chain': [
    { key: 'symbol', label: 'Underlying', kind: 'text', inline: true, placeholder: 'AAPL' },
    { key: 'expiration', label: 'Expiration', kind: 'text', inline: true, placeholder: 'YYYY-MM-DD' },
    { key: 'market', label: 'Market', kind: 'text' },
    { key: 'greeks', label: 'Calculate Greeks', kind: 'boolean' },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'daily', 'slow', 'any') },
  ],
  'finance.bond': [
    { key: 'symbol', label: 'Bond / tenor', kind: 'text', inline: true, placeholder: 'US10Y' },
    { key: 'seriesType', label: 'Series type', kind: 'text', inline: true, placeholder: 'treasury' },
    { key: 'market', label: 'Market', kind: 'text' },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'daily', 'slow', 'any') },
  ],
  'finance.funding_rate': [
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'BTC-USD' },
    { key: 'history', label: 'History points', kind: 'number', inline: true, min: 0, max: 500 },
    { key: 'exchange', label: 'Exchange', kind: 'text', placeholder: 'auto' },
    { key: 'market', label: 'Market', kind: 'text' },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'daily', 'slow', 'any') },
  ],
  'finance.open_interest': [
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'BTC-USD' },
    { key: 'window', label: 'Window', kind: 'text', inline: true, placeholder: '24h' },
    { key: 'exchange', label: 'Exchange', kind: 'text', placeholder: 'auto' },
    { key: 'market', label: 'Market', kind: 'text' },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'daily', 'slow', 'any') },
  ],
  'finance.supply': [
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'BTC' },
    { key: 'market', label: 'Market', kind: 'text' },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'daily', 'slow', 'any') },
  ],
  'finance.tvl': [
    { key: 'symbol', label: 'Protocol / chain', kind: 'text', inline: true, placeholder: 'aave' },
    { key: 'chain', label: 'Chain', kind: 'text', inline: true, placeholder: 'ethereum' },
    { key: 'market', label: 'Market', kind: 'text' },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'daily', 'slow', 'any') },
  ],
  'finance.onchain': [
    { key: 'address', label: 'Address', kind: 'text', inline: true, placeholder: '0x…' },
    { key: 'chain', label: 'Chain', kind: 'text', inline: true, placeholder: 'ethereum' },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'daily', 'slow', 'any') },
  ],
  'finance.liquidations': [
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'BTC' },
    { key: 'window', label: 'Window', kind: 'text', inline: true, placeholder: '24h' },
    { key: 'exchange', label: 'Exchange', kind: 'text', placeholder: 'auto' },
    { key: 'market', label: 'Market', kind: 'text' },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'daily', 'slow', 'any') },
  ],
  'finance.long_short_ratio': [
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, placeholder: 'BTC' },
    { key: 'interval', label: 'Interval', kind: 'text', inline: true, placeholder: '1h' },
    { key: 'limit', label: 'Points', kind: 'number', min: 1, max: 500 },
    { key: 'exchange', label: 'Exchange', kind: 'text', placeholder: 'auto' },
    { key: 'market', label: 'Market', kind: 'text' },
    { key: 'freshness', label: 'Freshness', kind: 'select', options: opts('realtime', 'intraday', 'daily', 'slow', 'any') },
  ],
  'quant.risk_metrics': [
    { key: 'inputKind', label: 'Input', kind: 'select', inline: true, options: opts('returns', 'prices') },
    { key: 'confidence', label: 'VaR confidence', kind: 'number', inline: true, min: 0.5, max: 0.999, step: 0.001 },
    { key: 'riskFreeRate', label: 'Risk-free rate', kind: 'number', min: -0.5, max: 0.5, step: 0.001 },
    { key: 'periodsPerYear', label: 'Periods / year', kind: 'number', min: 1, max: 1_000 },
  ],
  'quant.drawdown': [
    { key: 'inputKind', label: 'Input', kind: 'select', inline: true, options: opts('equity', 'returns') },
  ],
  'quant.correlation': [
    { key: 'method', label: 'Method', kind: 'select', inline: true, options: opts('pearson', 'spearman') },
    { key: 'window', label: 'Rolling window (0 = full)', kind: 'number', inline: true, min: 0, max: 2_000 },
  ],
  'quant.beta': [
    { key: 'inputKind', label: 'Input', kind: 'select', inline: true, options: opts('returns', 'prices') },
    { key: 'window', label: 'Rolling window (0 = full)', kind: 'number', inline: true, min: 0, max: 2_000 },
    { key: 'riskFreeRate', label: 'Risk-free rate', kind: 'number', min: -0.5, max: 0.5, step: 0.001 },
    { key: 'periodsPerYear', label: 'Periods / year', kind: 'number', min: 1, max: 1_000 },
  ],
  'quant.grade': [
    { key: 'minTrades', label: 'Minimum trades', kind: 'number', inline: true, min: 1, max: 10_000 },
    { key: 'goodTrades', label: 'Good trade count', kind: 'number', min: 1, max: 100_000 },
    { key: 'highProbabilityOfLoss', label: 'High loss probability (%)', kind: 'number', min: 0, max: 100, step: 0.1 },
  ],
  'quant.benchmark': [
    { key: 'interval', label: 'Interval', kind: 'select', inline: true, options: opts(...QUANT_INTERVALS) },
    { key: 'assetClass', label: 'Asset class', kind: 'select', inline: true, options: opts('equity', 'crypto') },
    { key: 'riskFreeRate', label: 'Risk-free rate', kind: 'number', min: -0.5, max: 0.5, step: 0.001 },
  ],
  'quant.resample': [
    { key: 'targetInterval', label: 'Target interval', kind: 'select', inline: true, options: opts(...QUANT_INTERVALS) },
    { key: 'sourceInterval', label: 'Source interval (blank = from series)', kind: 'text', inline: true, placeholder: '1h' },
  ],
  'quant.robustness': [
    ...quantInstrument, ...quantStrategy, ...quantRisk,
    ...pickQuantAdvanced('randomSeed', 'objective', 'paramSpaceJson'),
    { key: 'costMultipliersJson', label: 'Cost multipliers (JSON)', kind: 'json', group: 'Robustness', placeholder: '[1, 2, 5]' },
    { key: 'costMaterialDrop', label: 'Material cost drop', kind: 'number', group: 'Robustness', min: 0, max: 1, step: 0.01 },
    { key: 'concentrationTopN', label: 'Concentration top N', kind: 'number', group: 'Robustness', min: 1, max: 100 },
    { key: 'concentrationThreshold', label: 'Concentration threshold', kind: 'number', group: 'Robustness', min: 0, max: 1, step: 0.01 },
    { key: 'minTrades', label: 'Minimum trades', kind: 'number', group: 'Robustness', min: 1, max: 10_000 },
    { key: 'splits', label: 'Regime splits', kind: 'number', group: 'Robustness', min: 1, max: 20 },
  ],
  'quant.trade_analysis': [
    { key: 'maxEntries', label: 'Max analysed entries', kind: 'number', inline: true, min: 1, max: 5_000 },
    { key: 'symbol', label: 'Symbol (blank = from series)', kind: 'text', inline: true, placeholder: 'AAPL' },
  ],
  'quant.multiple_testing': [
    { key: 'periodsPerYear', label: 'Periods / year', kind: 'number', inline: true, min: 1, max: 1_000 },
    { key: 'nSplits', label: 'CSCV splits', kind: 'number', min: 2, max: 64 },
    { key: 'trialSharpesJson', label: 'Trial Sharpes (JSON)', kind: 'text', placeholder: '[1.2, 0.8, …]' },
    { key: 'returnsMatrixJson', label: 'Returns matrix (JSON)', kind: 'text', placeholder: '[[…], […]]' },
  ],
  'quant.align': [
    { key: 'join', label: 'Join', kind: 'select', inline: true, options: opts('inner', 'outer') },
    { key: 'column', label: 'Column', kind: 'text', inline: true, placeholder: 'close' },
    { key: 'fill', label: 'Fill', kind: 'select', inline: true, options: opts('none', 'ffill', 'zero') },
  ],
  'quant.regime': [
    { key: 'fast', label: 'Fast trend window', kind: 'number', inline: true, min: 1, max: 500 },
    { key: 'slow', label: 'Slow trend window', kind: 'number', inline: true, min: 2, max: 500 },
    { key: 'atrPeriod', label: 'ATR period', kind: 'number', min: 1, max: 500 },
    { key: 'volPeriod', label: 'Volatility window', kind: 'number', min: 1, max: 500 },
    { key: 'volBaseline', label: 'Volatility baseline', kind: 'number', min: 1, max: 2_000 },
    { key: 'trendThreshold', label: 'Trend threshold (ATR)', kind: 'number', min: 0, max: 10, step: 0.1 },
    { key: 'highVolRatio', label: 'High-vol ratio', kind: 'number', min: 1, max: 10, step: 0.1 },
    { key: 'lowVolRatio', label: 'Low-vol ratio', kind: 'number', min: 0.01, max: 1, step: 0.01 },
  ],
  'quant.position_size': [
    { key: 'method', label: 'Method', kind: 'select', inline: true, options: opts(
      'fixed_quantity', 'fixed_dollar', 'percent_equity', 'percent_risk', 'atr',
      'volatility', 'kelly', 'fractional_kelly', 'risk_parity', 'equal_weight',
    ) },
    { key: 'value', label: 'Method value', kind: 'number', inline: true },
    { key: 'equity', label: 'Equity', kind: 'number', inline: true, min: 0 },
    { key: 'atrMultiplier', label: 'ATR multiplier', kind: 'number', min: 0.1, max: 20, step: 0.1 },
    { key: 'maxFraction', label: 'Max equity fraction', kind: 'number', min: 0, max: 10, step: 0.05 },
    { key: 'kellyFraction', label: 'Kelly fraction', kind: 'number', min: 0, max: 1, step: 0.05 },
    { key: 'winRate', label: 'Win rate', kind: 'number', min: 0, max: 1, step: 0.01 },
    { key: 'payoff', label: 'Win/loss payoff', kind: 'number', min: 0.1, max: 100, step: 0.1 },
    { key: 'realizedVol', label: 'Realized volatility', kind: 'number', min: 0, max: 10, step: 0.01 },
    { key: 'weight', label: 'Target weight', kind: 'number', min: 0, max: 1, step: 0.01 },
    { key: 'minQuantity', label: 'Venue minimum', kind: 'number', min: 0 },
    { key: 'lotSize', label: 'Lot size', kind: 'number', min: 0 },
    { key: 'quantityPrecision', label: 'Quantity precision', kind: 'number', min: 0, max: 12 },
    { key: 'contractMultiplier', label: 'Contract multiplier', kind: 'number', min: 0.0001, max: 10_000 },
  ],
  'quant.portfolio_backtest': [
    // A portfolio has no single `symbol` and no single `strategyJson`; those two
    // single-series fields are dropped from the shared presentation blocks.
    ...quantInstrument.filter((field) => field.key !== 'symbol'),
    ...quantStrategy.filter((field) => field.key !== 'strategyJson'),
    ...quantRisk,
    ...pickQuantAdvanced('randomSeed', 'maxBars', 'includeSeries'),
    { key: 'strategiesJson', label: 'Strategies (JSON array)', kind: 'json', group: 'Strategy', help: 'One StrategySpec per strategy; each must declare universe.symbols. Empty = the preset on every symbol.' },
  ],
  'quant.costs': [
    { key: 'kind', label: 'Cost family', kind: 'select', inline: true, options: opts('transaction', 'slippage', 'spread', 'impact') },
    { key: 'executionJson', label: 'Execution model (JSON)', kind: 'json', help: 'The engine’s execution block: commission, slippage, spread, marketImpact.' },
    { key: 'randomSeed', label: 'Random seed', kind: 'number' },
  ],
  'quant.edge_report': [],
  'quant.options_strategy': [
    { key: 'spotMin', label: 'Payoff range min', kind: 'number', inline: true, min: 0 },
    { key: 'spotMax', label: 'Payoff range max', kind: 'number', inline: true, min: 0 },
    { key: 'points', label: 'Payoff points', kind: 'number', inline: true, min: 3, max: 2_001 },
    { key: 'riskFree', label: 'Risk-free rate', kind: 'number', min: -0.5, max: 0.5, step: 0.001 },
  ],
  'quant.futures_continuous': [
    { key: 'rollDatesJson', label: 'Roll dates (JSON)', kind: 'json', inline: true, placeholder: '["2024-03-15"]' },
    { key: 'adjustment', label: 'Adjustment', kind: 'select', inline: true, options: opts('none', 'difference', 'ratio') },
    { key: 'symbol', label: 'Series symbol', kind: 'text', inline: true, placeholder: 'CONTINUOUS' },
    { key: 'interval', label: 'Interval', kind: 'select', options: opts(...QUANT_INTERVALS) },
  ],
  'agent.team': [
    { key: 'objective', label: 'Objective', kind: 'text', inline: true, quick: 1, port: 'objective', help: 'What the committee decides on. A wired objective wins.' },
    { key: 'universe', label: 'Universe', kind: 'text', help: 'Optional symbols/instruments the committee covers.' },
    { key: 'horizon', label: 'Horizon', kind: 'text', help: 'Optional time horizon, e.g. 1-3 months.' },
    { key: 'timeoutS', label: 'Timeout (s)', kind: 'number', min: 30, max: 3_600 },
  ],
  'output.chart': [
    { key: 'kind', label: 'Chart', kind: 'select', inline: true, options: opts('line', 'area', 'bar', 'scatter', 'pie', 'donut') },
    { key: 'title', label: 'Title', kind: 'text', inline: true },
    { key: 'xLabel', label: 'X label', kind: 'text' },
    { key: 'yLabel', label: 'Y label', kind: 'text' },
    { key: 'xField', label: 'X field (rows payload)', kind: 'text' },
    { key: 'yField', label: 'Y field (rows payload)', kind: 'text' },
  ],
  'output.notify': [
    { key: 'channel', label: 'Channel', kind: 'text', inline: true, quick: 1, help: 'A channel configured in Settings, e.g. telegram, slack, discord, google_chat, lark, webhook.' },
    { key: 'destination', label: 'Destination', kind: 'text', inline: true, quick: 2, help: 'Chat / channel id the message goes to.' },
    { key: 'title', label: 'Title', kind: 'text', help: 'Optional first line of the message.' },
    { key: 'message', label: 'Message', kind: 'textarea', help: 'Used when the Message port is not wired.' },
  ],
  'research.source_rank': [
    { key: 'halfLifeDays', label: 'Freshness half-life (days)', kind: 'number', inline: true, min: 1, max: 3_650, help: 'An item this old scores 0.5 on freshness. Confidence and freshness are averaged.' },
  ],
  'logic.human_approval': [
    { key: 'title', label: 'Title', kind: 'text', inline: true, quick: 1, help: 'What the operator is approving.' },
    { key: 'message', label: 'Message', kind: 'textarea', help: 'Shown on the approval card. The Message port wins.' },
    { key: 'risk', label: 'Risk', kind: 'select', inline: true, options: opts('low', 'medium', 'high') },
    { key: 'ttlHours', label: 'Expires after (hours)', kind: 'number', min: 1, max: 24, help: 'An expired request is never approved.' },
    { key: 'pollSeconds', label: 'Re-check every (s)', kind: 'number', min: 2, max: 60, help: 'Also the durable job’s pause interval.' },
    { key: 'maxWaitS', label: 'Max wait (s, synchronous runs)', kind: 'number', min: 10, max: 3_600 },
  ],
  'logic.assert': [
    { key: 'expect', label: 'Expect', kind: 'select', inline: true, options: opts('truthy', 'falsy', 'present') },
    { key: 'message', label: 'Failure message', kind: 'text', inline: true, quick: 1, help: 'Shown as the node error (and the run error with fail-fast).' },
  ],
  'data.extract': [
    { key: 'path', label: 'Path', kind: 'text', inline: true, quick: 1, help: 'Dotted path, e.g. data.items.0.price. A numeric segment indexes a list.' },
    { key: 'onMissing', label: 'When missing', kind: 'select', inline: true, options: opts('null', 'error') },
  ],
  'memory.recall': [
    { key: 'query', label: 'Query', kind: 'text', inline: true, quick: 1 },
    { key: 'types', label: 'Memory types', kind: 'text', help: 'Comma separated. Blank reads all types the policy allows.' },
    { key: 'limit', label: 'Limit', kind: 'number', min: 1, max: 50 },
    { key: 'scope', label: 'Scope', kind: 'text', help: 'Blank uses the memory service default.' },
  ],
  'memory.remember': [
    { key: 'content', label: 'Content', kind: 'textarea', inline: true, quick: 1 },
    { key: 'memoryType', label: 'Type', kind: 'select', inline: true, options: MEMORY_TYPES.map((value) => ({ value, label: value })) },
    { key: 'scope', label: 'Scope', kind: 'text' },
    { key: 'subject', label: 'Subject', kind: 'text' },
    { key: 'importance', label: 'Importance', kind: 'number', min: 0, max: 1, step: 0.1 },
  ],
  'agent.classify': [
    { key: 'labels', label: 'Labels (comma separated)', kind: 'text', inline: true, quick: 1, help: 'At least two. The model must return one of these exactly; anything else fails the node.' },
    { key: 'instructions', label: 'Instructions', kind: 'textarea', help: 'Optional guidance for the classifier. It cannot widen the label set.' },
  ],
  'agent.extract': [
    { key: 'schemaJson', label: 'Target schema (JSON)', kind: 'code', help: 'JSON Schema subset used to CHECK the extraction: type, required, properties, items. Empty = no check.' },
    { key: 'instructions', label: 'Instructions', kind: 'textarea', help: 'What to extract and how to read the text.' },
  ],
  'agent.summarize': [
    { key: 'maxWords', label: 'Max words', kind: 'number', inline: true, min: 10, max: 2_000 },
    { key: 'style', label: 'Style', kind: 'select', inline: true, options: opts('prose', 'bullets') },
  ],
  'agent.critique': [
    { key: 'rubric', label: 'Rubric (optional)', kind: 'textarea', help: 'What counts as support. Blank uses the built-in rubric.' },
  ],
  'agent.bot': [
    { key: 'botId', label: 'Bot', kind: 'text', quick: 1, help: 'Saved bot to run. Pick one above; the node resolves it at run time.' },
    { key: 'objective', label: 'Objective (optional)', kind: 'text', quick: 2, port: 'query', help: 'Overrides the bot’s saved objective for this run. A wired query wins.' },
    { key: 'maxSteps', label: 'Max steps', kind: 'number', min: 1, max: 32 },
  ],
  'skill.invoke': [
    { key: 'skillId', label: 'Skill', kind: 'text', inline: true, quick: 1, help: 'Installed skill id. Pick one above; the runtime re-checks its status and permissions at run time.' },
    { key: 'version', label: 'Version (blank = latest)', kind: 'text', help: 'Pin a skill version. Blank uses the registry’s current version.' },
    { key: 'inputJson', label: 'Input (JSON)', kind: 'code', help: 'Used when the Input port is not wired; wired keys win over these.' },
    { key: 'timeoutMs', label: 'Timeout (ms)', kind: 'number', min: 1_000, max: 900_000 },
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
  'quant.backtest': [
    ...quantInstrument, ...quantStrategy, ...quantRisk,
    ...pickQuantAdvanced('randomSeed', 'maxBars', 'includeSeries'),
  ],
  'quant.walkforward': [
    ...quantInstrument, ...quantStrategy, ...quantRisk,
    ...pickQuantAdvanced(
      'randomSeed', 'maxEvaluations', 'method', 'objective', 'paramSpaceJson',
      'trainBars', 'testBars', 'stepBars', 'anchored',
    ),
  ],
  'quant.optimize': [
    ...quantInstrument, ...quantStrategy, ...quantRisk,
    ...pickQuantAdvanced(
      'randomSeed', 'maxEvaluations', 'method', 'objective', 'paramSpaceJson',
      'objectivesJson', 'leaderboardSize',
    ),
  ],
  'quant.montecarlo': [
    ...quantInstrument, ...quantStrategy, ...quantRisk,
    ...pickQuantAdvanced(
      'randomSeed', 'method', 'simulations', 'ruinThreshold', 'regimeMix',
      'regimeBlockLength', 'perturbationPct', 'perturbationJson',
      'executionPerturbationJson',
    ),
  ],
  'quant.oos': [
    ...quantInstrument, ...quantStrategy, ...quantRisk,
    ...pickQuantAdvanced(
      'randomSeed', 'oosFraction', 'oosStartIndex', 'bootstrapIterations',
      'confidence', 'objective',
    ),
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
    { key: 'objective', label: 'Objective', kind: 'text', inline: true, quick: 1, port: 'query' },
    { key: 'agent', label: 'Agent', kind: 'text', quick: 2 },
    { key: 'agentVersion', label: 'Agent version (0 = latest)', kind: 'number', min: 0 },
    { key: 'maxSteps', label: 'Max steps', kind: 'number', min: 1, max: 32 },
  ],
  'agent.plan': [
    { key: 'objective', label: 'Objective', kind: 'text', inline: true },
  ],
  'agent.delegate': [
    { key: 'agent', label: 'Agent', kind: 'text', inline: true },
    { key: 'agentVersion', label: 'Agent version (0 = latest)', kind: 'number', min: 0 },
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
    { key: 'equity', label: 'Equity', kind: 'number', inline: true, min: 1, help: 'Used only when no `equity`/`account` input is wired.' },
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
  // A type-level override applies to every version; a `type@version` entry
  // refines it for one version (an older saved node never grows a new field).
  const exact = FIELD_OVERRIDES[`${def.type}@${def.version}`] ?? [];
  const overrides = new Map(
    [...(FIELD_OVERRIDES[def.type] ?? []), ...exact].map((field) => [field.key, field]),
  );
  const keys = [...Object.keys(defaults)];
  for (const key of overrides.keys()) {
    if (!keys.includes(key)) keys.push(key);
  }
  const fields = keys.map((key): ConfigFieldDef => {
    const base: ConfigFieldDef = {
      key,
      label: humanize(key),
      kind: inferKind(defaults[key]),
      help: KEY_HELP[key],
      required: (REQUIRED_FIELDS[def.type] ?? []).includes(key),
      group: GROUP_BY_KEY[key],
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
    .map((field, index) => ({ field, index }))
    .filter(({ field }) => (field.inline || field.quick !== undefined) && field.kind !== 'json')
    .sort((a, b) => (a.field.quick ?? 1_000) - (b.field.quick ?? 1_000) || a.index - b.index)
    .slice(0, 2)
    .map(({ field }) => field);
  inlineCache.set(def, fields);
  return fields;
}

const EMPTY: ConfigFieldDef[] = [];
