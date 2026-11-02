// Advanced quant contracts: portfolio backtest, explicit cost models, the Edge
// Report, and the instrument-specific options / futures nodes.
//
// The Python twins live in `graph_runtime/quant_portfolio_nodes.py` (portfolio),
// `graph_runtime/quant_validation_nodes.py` (costs, report) and
// `graph_runtime/quant_instruments_nodes.py` (options, futures). All are adapters
// over `harness/quant/{engine,costs,edge_report,options,futures}.py`.

import { z } from 'zod';
import type { NodeDefinition, PortDef } from './types';

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

const MODES: NodeDefinition['allowedModes'] = ['research', 'backtest', 'paper', 'live'];

export const QUANT_ADVANCED_DEFINITIONS: NodeDefinition[] = [
  {
    type: 'quant.portfolio_backtest',
    version: '1.0.0',
    category: 'quant',
    label: 'Portfolio backtest',
    description: 'Runs several strategies on one shared book over a {symbol: OHLCV} map.',
    icon: 'chart',
    inputs: [port({ id: 'series', name: 'Series map', type: 'object' })],
    outputs: [
      port({ id: 'result', name: 'Result', type: 'object' }),
      port({ id: 'metrics', name: 'Metrics', type: 'object' }),
      port({ id: 'trades', name: 'Trades', type: 'array' }),
    ],
    configSchema: z.object({
      preset: z.enum(['ema_cross', 'rsi_reversion']).default('ema_cross'),
      interval: z.string().max(10).default('1d'),
      strategiesJson: z.string().max(40_000).default(''),
      includeSeries: z.boolean().default(false),
      maxBars: z.number().int().min(0).max(20_000).default(0),
      initialCapital: z.number().min(1_000).max(1_000_000_000).default(100_000),
      riskFreeRate: z.number().min(-0.5).max(0.5).default(0),
      randomSeed: z.number().int().min(0).max(2_147_483_647).default(42),
      fast: z.number().int().min(1).max(500).default(12),
      slow: z.number().int().min(2).max(500).default(50),
      atrPeriod: z.number().int().min(1).max(500).default(14),
      atrMult: z.number().min(0.1).max(20).default(2),
      reward: z.number().min(0.1).max(20).default(2),
      sizePct: z.number().min(1).max(100).default(90),
      rsiPeriod: z.number().int().min(2).max(500).default(14),
      oversold: z.number().min(1).max(49).default(30),
      overbought: z.number().min(51).max(99).default(55),
      stopPct: z.number().min(0.1).max(100).default(5),
    }),
    defaultConfig: () => ({
      preset: 'ema_cross', interval: '1d', strategiesJson: '', includeSeries: false,
      maxBars: 0, initialCapital: 100_000, riskFreeRate: 0, randomSeed: 42,
      fast: 12, slow: 50, atrPeriod: 14, atrMult: 2, reward: 2, sizePct: 90,
      rsiPeriod: 14, oversold: 30, overbought: 55, stopPct: 5,
    }),
    capabilities: ['quant.compute'],
    sideEffects: 'none',
    allowedModes: MODES,
    docs: 'Default is one preset strategy per symbol; strategiesJson replaces that with explicit StrategySpecs that each declare universe.symbols. A symbol claimed twice, referenced but absent, or an invalid spec is an explicit failure.',
  },
  {
    type: 'quant.costs',
    version: '1.0.0',
    category: 'quant',
    label: 'Transaction costs',
    description: 'One cost family over an order list, with the exact model made auditable.',
    icon: 'activity',
    inputs: [port({ id: 'orders', name: 'Orders', type: 'array' })],
    outputs: [
      port({ id: 'costs', name: 'Costs', type: 'object' }),
      port({ id: 'total', name: 'Total', type: 'number' }),
      port({ id: 'summary', name: 'Summary', type: 'string' }),
    ],
    configSchema: z.object({
      kind: z.enum(['transaction', 'slippage', 'spread', 'impact']).default('transaction'),
      executionJson: z.string().max(20_000).default(''),
      randomSeed: z.number().int().min(0).max(2_147_483_647).default(42),
    }),
    defaultConfig: () => ({ kind: 'transaction', executionJson: '', randomSeed: 42 }),
    capabilities: ['quant.compute'],
    sideEffects: 'none',
    allowedModes: MODES,
    docs: 'Orders need side, quantity and price (symbol/atr/volume optional). A model missing its input (volume for impact, a bar spread for historical spread) reports a warning and contributes zero — never a guessed cost.',
  },
  {
    type: 'quant.edge_report',
    version: '1.0.0',
    category: 'quant',
    label: 'Edge report',
    description: 'Grades a backtest artifact and renders the Markdown report with its charts.',
    icon: 'text',
    inputs: [
      port({ id: 'result', name: 'Backtest result', type: 'object' }),
      port({ id: 'monteCarlo', name: 'Monte Carlo', type: 'object', optional: true }),
    ],
    outputs: [
      port({ id: 'report', name: 'Report (Markdown)', type: 'string' }),
      port({ id: 'charts', name: 'Charts', type: 'array' }),
      port({ id: 'verdict', name: 'Verdict', type: 'object' }),
    ],
    configSchema: z.object({}),
    defaultConfig: () => ({}),
    capabilities: ['quant.compute'],
    sideEffects: 'none',
    allowedModes: MODES,
    docs: 'The document and figures come from the same artifact the verdict grades. Without a Monte Carlo or an equity curve the report says which figures are absent instead of drawing empty ones.',
  },
  {
    type: 'quant.options_strategy',
    version: '1.0.0',
    category: 'quant',
    label: 'Options strategy',
    description: 'Multi-leg expiry payoff, break-evens and boundedness, with Greeks when supplied.',
    icon: 'activity',
    inputs: [
      port({ id: 'legs', name: 'Legs', type: 'array' }),
      port({ id: 'spot', name: 'Spot', type: 'number', optional: true }),
      port({ id: 'timeToExpiry', name: 'Time to expiry (years)', type: 'number', optional: true }),
      port({ id: 'iv', name: 'Implied volatility', type: 'number', optional: true }),
    ],
    outputs: [
      port({ id: 'analysis', name: 'Analysis', type: 'object' }),
      port({ id: 'summary', name: 'Summary', type: 'string' }),
    ],
    configSchema: z.object({
      spotMin: z.number().min(0).default(0),
      spotMax: z.number().min(0).default(0),
      points: z.number().int().min(3).max(2_001).default(201),
      riskFree: z.number().min(-0.5).max(0.5).default(0.05),
    }),
    defaultConfig: () => ({ spotMin: 0, spotMax: 0, points: 201, riskFree: 0.05 }),
    capabilities: ['quant.compute'],
    sideEffects: 'none',
    allowedModes: MODES,
    docs: 'Legs are [{type, strike, quantity, premium}] (multiplier/iv optional). Spot + time-to-expiry add net Greeks. An unbounded tail is null with `bounded: false`, never a made-up max loss; the payoff range is configured or derived and the payload says which.',
  },
  {
    type: 'quant.futures_continuous',
    version: '1.0.0',
    category: 'quant',
    label: 'Continuous futures',
    description: 'Splices ordered contracts at roll dates into one back-adjusted series.',
    icon: 'chart',
    inputs: [port({ id: 'contracts', name: 'Contracts', type: 'array' })],
    outputs: [
      port({ id: 'series', name: 'OHLCV', type: 'ohlcv' }),
      port({ id: 'metadata', name: 'Metadata', type: 'object' }),
    ],
    configSchema: z.object({
      rollDatesJson: z.string().max(4_000).default(''),
      adjustment: z.enum(['none', 'difference', 'ratio']).default('difference'),
      symbol: z.string().max(40).default(''),
      interval: z.string().max(10).default('1d'),
    }),
    defaultConfig: () => ({ rollDatesJson: '', adjustment: 'difference', symbol: '', interval: '1d' }),
    capabilities: ['quant.compute'],
    sideEffects: 'none',
    allowedModes: MODES,
    docs: 'Contracts are near→far with rows; rollDatesJson needs one ISO date per roll. The series is marked `proxy: true`: a continuous series is a backtest proxy, not a deliverable contract, and the most recent contract stays unadjusted.',
  },
];
