// Quant structure node contracts: alignment, regime labels, position size.
//
// Split from `registry-market.ts` so neither file grows without bound. The
// Python twins live in `graph_runtime/quant_structure_nodes.py` and are adapters
// over `harness/quant/{transform,regime,sizing}.py`; the parity suite compares
// every port, field and bound.

import { z } from 'zod';
import type { NodeDefinition, PortDef } from './types';

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

const MODES: NodeDefinition['allowedModes'] = ['research', 'backtest', 'paper', 'live'];

const SIZING_TYPES = [
  'fixed_quantity', 'fixed_dollar', 'percent_equity', 'percent_risk', 'atr',
  'volatility', 'kelly', 'fractional_kelly', 'risk_parity', 'equal_weight',
] as const;

export const QUANT_STRUCTURE_DEFINITIONS: NodeDefinition[] = [
  {
    type: 'quant.align',
    version: '1.0.0',
    category: 'quant',
    label: 'Align instruments',
    description: 'Aligns several instruments onto one timestamp axis with an explicit join and fill.',
    icon: 'merge',
    inputs: [port({ id: 'series', name: 'Series map', type: 'object' })],
    outputs: [
      port({ id: 'aligned', name: 'Aligned', type: 'object' }),
      port({ id: 'metadata', name: 'Metadata', type: 'object' }),
    ],
    configSchema: z.object({
      join: z.enum(['inner', 'outer']).default('inner'),
      column: z.string().max(20).default('close'),
      fill: z.enum(['none', 'ffill', 'zero']).default('none'),
    }),
    defaultConfig: () => ({ join: 'inner', column: 'close', fill: 'none' }),
    capabilities: ['quant.compute'],
    sideEffects: 'none',
    allowedModes: MODES,
    docs: 'Input is {symbol: OHLCV rows}. `fill: none` leaves gaps null and counts them per symbol; ffill/zero impute only on explicit request and `imputed` records that they did.',
  },
  {
    type: 'quant.regime',
    version: '1.0.0',
    category: 'quant',
    label: 'Regime labels',
    description: 'Labels every bar trend × volatility through the existing regime classifier.',
    icon: 'activity',
    inputs: [port({ id: 'series', name: 'OHLCV', type: 'ohlcv' })],
    outputs: [
      port({ id: 'regimes', name: 'Regimes', type: 'object' }),
      port({ id: 'summary', name: 'Summary', type: 'string' }),
    ],
    configSchema: z.object({
      fast: z.number().int().min(1).max(500).default(20),
      slow: z.number().int().min(2).max(500).default(50),
      atrPeriod: z.number().int().min(1).max(500).default(14),
      volPeriod: z.number().int().min(1).max(500).default(20),
      volBaseline: z.number().int().min(1).max(2_000).default(100),
      trendThreshold: z.number().min(0).max(10).default(0.5),
      highVolRatio: z.number().min(1).max(10).default(1.5),
      lowVolRatio: z.number().min(0.01).max(1).default(0.67),
    }),
    defaultConfig: () => ({
      fast: 20, slow: 50, atrPeriod: 14, volPeriod: 20, volBaseline: 100,
      trendThreshold: 0.5, highVolRatio: 1.5, lowVolRatio: 0.67,
    }),
    capabilities: ['quant.compute'],
    sideEffects: 'none',
    allowedModes: MODES,
    docs: 'Trend (up/down/flat) × volatility (high/normal/low) per bar plus counts and confidence. `warmupBars` counts the leading bars before the first informed trend label; those bars are `flat` and never presented as a measured trend.',
  },
  {
    type: 'quant.position_size',
    version: '1.0.0',
    category: 'quant',
    label: 'Position size',
    description: 'Computes a position size with the engine’s own PositionSizing contract.',
    icon: 'sigma',
    inputs: [
      port({ id: 'price', name: 'Price', type: 'number' }),
      port({ id: 'atr', name: 'ATR', type: 'number', optional: true }),
      port({ id: 'stop', name: 'Stop distance', type: 'number', optional: true }),
    ],
    outputs: [
      port({ id: 'size', name: 'Size', type: 'object' }),
      port({ id: 'quantity', name: 'Quantity', type: 'number' }),
    ],
    configSchema: z.object({
      method: z.enum(SIZING_TYPES).default('percent_equity'),
      value: z.number().default(1),
      equity: z.number().min(0).max(1_000_000_000).default(100_000),
      atrMultiplier: z.number().min(0.1).max(20).default(1),
      maxFraction: z.number().min(0).max(10).default(1),
      kellyFraction: z.number().min(0).max(1).default(0.5),
      winRate: z.number().min(0).max(1).default(0.5),
      payoff: z.number().min(0.1).max(100).default(2),
      realizedVol: z.number().min(0).max(10).default(0),
      weight: z.number().min(0).max(1).default(0),
      minQuantity: z.number().min(0).default(0),
      lotSize: z.number().min(0).default(0),
      quantityPrecision: z.number().int().min(0).max(12).default(0),
      contractMultiplier: z.number().min(0.0001).max(10_000).default(1),
    }),
    defaultConfig: () => ({
      method: 'percent_equity', value: 1, equity: 100_000, atrMultiplier: 1,
      maxFraction: 1, kellyFraction: 0.5, winRate: 0.5, payoff: 2, realizedVol: 0,
      weight: 0, minQuantity: 0, lotSize: 0, quantityPrecision: 0, contractMultiplier: 1,
    }),
    capabilities: ['quant.compute'],
    sideEffects: 'none',
    allowedModes: MODES,
    docs: 'A method whose input is missing (no stop for percent_risk, no ATR for atr, no trade statistics for Kelly) fails and names it — never a guessed size.',
  },
];
