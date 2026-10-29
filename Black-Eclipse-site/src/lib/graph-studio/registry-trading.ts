// Paper-trading node contracts (Phase 8). Split out of `registry.ts` to keep the
// registry file inside its size budget; the definitions are still declared once
// and re-exported into the ONE registry array.

import { z } from 'zod';
import type { NodeDefinition, PortDef } from './types';

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

export const TRADING_DEFINITIONS: NodeDefinition[] = [
  {
    type: 'trading.risk_check',
    version: '1.0.0',
    category: 'trading',
    label: 'Risk check',
    description: 'Pure pre-trade gate: reduces or rejects an order against the risk limits.',
    icon: 'activity',
    inputs: [
      port({ id: 'intent', name: 'Order intent', type: 'order_intent' }),
      port({ id: 'price', name: 'Price', type: 'number', optional: true }),
    ],
    outputs: [
      port({ id: 'intent', name: 'Order intent', type: 'order_intent' }),
      port({ id: 'decision', name: 'Decision', type: 'object' }),
      port({ id: 'approved', name: 'Approved', type: 'boolean' }),
    ],
    configSchema: z.object({
      equity: z.number().min(1).max(1_000_000_000_000).default(100_000),
      price: z.number().min(0).max(1_000_000_000).default(0),
      currentSymbolValue: z.number().min(-1_000_000_000_000).max(1_000_000_000_000).default(0),
      grossExposure: z.number().min(0).max(1_000_000_000_000).default(0),
      openPositions: z.number().int().min(0).max(10_000).default(0),
      stopDistance: z.number().min(0).max(1_000_000_000).default(0),
      hasStop: z.boolean().default(false),
      isOpening: z.boolean().default(true),
      dailyPnl: z.number().min(-1_000_000_000_000).max(1_000_000_000_000).default(0),
      dailyStartEquity: z.number().min(0).max(1_000_000_000_000).default(0),
      maxPositionPct: z.number().min(0).max(100).default(0),
      maxGrossExposure: z.number().min(0).max(100).default(0),
      maxLeverage: z.number().min(0).max(100).default(0),
      maxOpenPositions: z.number().int().min(0).max(1_000).default(0),
      maxDailyLossPct: z.number().min(0).max(100).default(0),
      maxRiskPerTradePct: z.number().min(0).max(100).default(0),
      requireStop: z.boolean().default(false),
      allowLong: z.boolean().default(true),
      allowShort: z.boolean().default(true),
    }),
    defaultConfig: () => ({
      equity: 100_000, price: 0, currentSymbolValue: 0, grossExposure: 0,
      openPositions: 0, stopDistance: 0, hasStop: false, isOpening: true,
      dailyPnl: 0, dailyStartEquity: 0, maxPositionPct: 0, maxGrossExposure: 0,
      maxLeverage: 0, maxOpenPositions: 0, maxDailyLossPct: 0,
      maxRiskPerTradePct: 0, requireStop: false, allowLong: true, allowShort: true,
    }),
    capabilities: ['trading.risk'],
    sideEffects: 'none',
    allowedModes: ['paper'],
    docs: 'Runs harness/quant/risk.py. A limit of 0 disables it. A rejection is an outcome, not an error.',
  },
  {
    type: 'trading.paper_order',
    version: '1.0.0',
    category: 'trading',
    label: 'Paper order',
    description: 'PAPER-only execution adapter: simulates a fill at the supplied price.',
    icon: 'activity',
    inputs: [
      port({ id: 'intent', name: 'Order intent', type: 'order_intent' }),
      port({ id: 'price', name: 'Price', type: 'number', optional: true }),
      port({ id: 'decision', name: 'Risk decision', type: 'object', optional: true }),
    ],
    outputs: [
      port({ id: 'fill', name: 'Fill', type: 'object' }),
      port({ id: 'status', name: 'Status', type: 'string' }),
      port({ id: 'intent', name: 'Order intent', type: 'order_intent' }),
      port({ id: 'account', name: 'Paper account', type: 'object' }),
    ],
    configSchema: z.object({
      price: z.number().min(0).max(1_000_000_000).default(0),
      commissionPct: z.number().min(0).max(10).default(0),
      slippagePct: z.number().min(0).max(10).default(0),
      accountId: z.string().max(80).default('paper'),
      persist: z.boolean().default(true),
      initialCash: z.number().min(0).max(1_000_000_000_000).default(100_000),
    }),
    defaultConfig: () => ({
      price: 0, commissionPct: 0, slippagePct: 0,
      accountId: 'paper', persist: true, initialCash: 100_000,
    }),
    capabilities: ['trading.paper'],
    sideEffects: 'trading',
    allowedModes: ['paper'],
    docs: 'Fills at the supplied price with slippage/commission and (by default) records it in the durable paper account. No broker is contacted and no live order is placed; requires an explicit operator paper-trading grant.',
  },
  {
    type: 'trading.broker_order',
    version: '1.0.0',
    category: 'trading',
    label: 'Broker order (demo mandate)',
    description: 'Submit one order to a demo broker connection under a bounded, revocable mandate.',
    icon: 'activity',
    inputs: [
      port({ id: 'intent', name: 'Order intent', type: 'order_intent' }),
    ],
    outputs: [
      port({ id: 'result', name: 'Result', type: 'object' }),
      port({ id: 'status', name: 'Status', type: 'string' }),
      port({ id: 'orderId', name: 'Order id', type: 'string' }),
    ],
    configSchema: z.object({
      connectionId: z.string().max(80).default(''),
      mandateId: z.string().max(80).default(''),
    }),
    defaultConfig: () => ({ connectionId: '', mandateId: '' }),
    capabilities: ['trading.broker'],
    sideEffects: 'trading',
    allowedModes: ['paper'],
    docs: 'Submits ONE order to a DEMO broker connection under an operator-created, bounded, revocable mandate. There is no per-order approval card; the mandate is the authorization. The connection must be demo, and live trading nodes are refused. The broker service still applies policy, money guardrails and the account-mode check, and consumes one mandate use atomically.',
  },
];
