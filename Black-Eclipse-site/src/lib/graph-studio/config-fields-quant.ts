// Quant node presentation. Split out of config-fields.ts so both files stay
// inside the source size budget; merged back into the ONE map there.

import type { ConfigFieldDef } from './types';

type Override = Omit<ConfigFieldDef, 'key'> & { key: string };

const opts = (...values: string[]): ConfigFieldDef['options'] =>
  values.map((value) => ({ value, label: value }));

/** Bar intervals the quant pack accepts (resample + benchmark annualization). */
const QUANT_INTERVALS = ['1m', '5m', '15m', '30m', '1h', '4h', '1d', '1w', '1mo'];

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

/** Quant nodes' field presentation (the Parameters tab). */
export const QUANT_FIELD_OVERRIDES: Record<string, Override[]> = {
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
};
