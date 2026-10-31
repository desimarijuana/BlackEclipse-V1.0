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

/** One-line explanations shared by every node that uses the key. */
const KEY_HELP: Record<string, string> = {

  objective: 'What the agent should do. A wired query overrides this.',
  agent: 'Agent preset id. Pick a built-in or a preset from Settings › Agents.',
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
  confidence: 'Bootstrap confidence level (0–1).',
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
  cases: 'Comma-separated values; a matching case fires its control output.',
  message: 'Optional message emitted when the run stops.',
  status: 'Status to record when the run stops.',
  ms: 'Pause duration in milliseconds (bounded).',
  label: 'Display label for the result.',
  closeAll: 'Close every open position on the connection.',
  deviation: 'Maximum price deviation in points.',
  continueOnError: 'Keep looping when one iteration fails.',
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
  headersJson: 'Request',
  bodyJson: 'Request',
  credentialEnvJson: 'Request',
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
  'trading.broker_account': ['connectionId'],
  'trading.broker_quote': ['connectionId'],
  'trading.broker_bars': ['connectionId'],
  'trading.broker_close': ['connectionId'],
  'trading.broker_modify': ['connectionId'],
  'trading.broker_cancel': ['connectionId'],
  'integration.http': ['url'],
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
    { key: 'strict', label: 'Strict', kind: 'boolean', help: 'Reject invalid JSON instead of passing the raw text through.' },
  ],
  'trading.broker_order': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
    { key: 'mandateId', label: 'Mandate (live/paper)', kind: 'text' },
  ],
  'trading.broker_account': [
    { key: 'connectionId', label: 'Broker connection', kind: 'text' },
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
    { key: 'operator', label: 'Operator', kind: 'select', inline: true, quick: 1, options: opts('eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'truthy') },
    { key: 'compareTo', label: 'Compare to', kind: 'text', quick: 2 },
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
    { key: 'symbol', label: 'Symbol', kind: 'text', inline: true, quick: 1, placeholder: 'AAPL' },
    { key: 'interval', label: 'Interval', kind: 'select', inline: true, quick: 2, options: opts('1m', '5m', '15m', '1h', '1d') },
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
