// Trade-learning node contracts. The editor half of the pair; the runtime half
// is `python/harness/graph_runtime/trade_learning_nodes.py`. Keep the two in
// lockstep and regenerate the manifest (`npm run graph:manifest`).
//
// The pack is deliberately split by authority: review and improve are pure and
// can run anywhere; commit changes the envelope future orders are checked
// against and is an operator-run write.

import { z } from 'zod';
import type { NodeDefinition, PortDef } from './types';

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

const ALL_MODES = ['research', 'backtest', 'paper', 'live'] as const;

export const LEARNING_DEFINITIONS: NodeDefinition[] = [
  {
    type: 'trade.journal',
    version: '1.0.0',
    category: 'learning',
    label: 'Journal trades',
    description: 'Loads a bounded window of journal trades and their execution log.',
    icon: 'activity',
    inputs: [port({ id: 'trades', name: 'Trades', type: 'array', optional: true })],
    outputs: [
      port({ id: 'trades', name: 'Trades', type: 'array' }),
      port({ id: 'executions', name: 'Execution log', type: 'object' }),
      port({ id: 'completeness', name: 'Data completeness', type: 'object' }),
      port({ id: 'provenance', name: 'Provenance', type: 'object' }),
    ],
    configSchema: z.object({
      lookbackDays: z.number().int().min(1).max(3650).default(90),
      status: z.enum(['closed', 'open', 'all']).default('closed'),
      symbols: z.string().max(400).default(''),
      strategyId: z.string().max(80).default(''),
      setupId: z.string().max(80).default(''),
      limit: z.number().int().min(1).max(500).default(200),
      includeExecutions: z.boolean().default(true),
    }),
    defaultConfig: () => ({
      lookbackDays: 90, status: 'closed', symbols: '', strategyId: '',
      setupId: '', limit: 200, includeExecutions: true,
    }),
    capabilities: ['journal.read'],
    sideEffects: 'read',
    allowedModes: [...ALL_MODES],
    docs: 'Reads the journal through the authenticated, read-only JDDS bridge. Owner-scoped and bounded to 500 trades. A wired `trades` input wins over the bridge. Missing fields stay null; the payload reports completeness so the loop can refuse to learn from a thin sample.',
  },
  {
    type: 'trade.review',
    version: '1.0.0',
    category: 'learning',
    label: 'Review trades',
    description: 'Finds process mistakes with deterministic detectors and names the field.',
    icon: 'check',
    inputs: [
      port({ id: 'trades', name: 'Trades', type: 'array' }),
      port({ id: 'executions', name: 'Execution log', type: 'object', optional: true }),
      port({ id: 'playbook', name: 'Playbook', type: 'object', optional: true }),
    ],
    outputs: [
      port({ id: 'findings', name: 'Findings', type: 'array' }),
      port({ id: 'summary', name: 'Summary', type: 'object' }),
      port({ id: 'reviewed', name: 'Clean trades', type: 'array' }),
      port({ id: 'coverage', name: 'Data coverage', type: 'object' }),
    ],
    configSchema: z.object({
      detectors: z.string().max(400).default(''),
      riskPct: z.number().min(0).max(100).default(1),
      accountEquity: z.number().min(0).max(1_000_000_000_000_000).default(0),
      maxTradesPerDay: z.number().int().min(0).max(100).default(3),
      revengeWindowMin: z.number().int().min(0).max(1440).default(30),
      duplicateWindowMin: z.number().int().min(0).max(1440).default(60),
      reviewGraceHours: z.number().int().min(0).max(8760).default(24),
      minRForEarlyExit: z.number().min(0).max(100).default(1),
      includeOpen: z.boolean().default(false),
    }),
    defaultConfig: () => ({
      detectors: '', riskPct: 1, accountEquity: 0, maxTradesPerDay: 3,
      revengeWindowMin: 30, duplicateWindowMin: 60, reviewGraceHours: 24,
      minRForEarlyExit: 1, includeOpen: false,
    }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: [...ALL_MODES],
    docs: 'Pure: same trades produce the same findings. A finding always cites the field it saw; a missing field is reported as unavailable, never guessed. A losing trade that followed the plan is NOT a finding.',
  },
  {
    type: 'trade.learn',
    version: '1.0.0',
    category: 'learning',
    label: 'Learn from review',
    description: 'Records findings, counts recurrence and drafts inert lesson candidates.',
    icon: 'sparkles',
    inputs: [
      port({ id: 'findings', name: 'Findings', type: 'array' }),
      port({ id: 'coverage', name: 'Data coverage', type: 'object', optional: true }),
    ],
    outputs: [
      port({ id: 'recorded', name: 'Findings recorded', type: 'number' }),
      port({ id: 'recurring', name: 'Recurring patterns', type: 'array' }),
      port({ id: 'candidates', name: 'Inert candidates', type: 'array' }),
      port({ id: 'thresholds', name: 'Thresholds', type: 'object' }),
    ],
    configSchema: z.object({
      minOccurrences: z.number().int().min(1).max(100).default(3),
      windowDays: z.number().int().min(1).max(3650).default(90),
      minCostR: z.number().min(0).max(1_000_000).default(1),
      minCoverage: z.number().min(0).max(1).default(0.8),
      draftCandidates: z.boolean().default(true),
    }),
    defaultConfig: () => ({
      minOccurrences: 3, windowDays: 90, minCostR: 1, minCoverage: 0.8,
      draftCandidates: true,
    }),
    capabilities: ['learning.write'],
    sideEffects: 'local_write',
    allowedModes: [...ALL_MODES],
    docs: 'Writes derived observations to the runtime store only (never the journal). Recurrence is the ONE LearningRecurrence ledger, keyed by trade id so re-reviewing a trade cannot inflate a pattern. A candidate is inert: it enables nothing. A test run is refused because recurrence is durable evidence, not scratch.',
  },
  {
    type: 'trade.improve',
    version: '1.0.0',
    category: 'learning',
    label: 'Improve playbook',
    description: 'Runs a seeded recursive climb and ranks playbook variants out-of-sample.',
    icon: 'activity',
    inputs: [
      port({ id: 'trades', name: 'Trades', type: 'array' }),
      port({ id: 'findings', name: 'Findings', type: 'array', optional: true }),
      port({ id: 'playbook', name: 'Playbook', type: 'object', optional: true }),
    ],
    outputs: [
      port({ id: 'candidates', name: 'Ranked candidates', type: 'array' }),
      port({ id: 'best', name: 'Best playbook', type: 'object' }),
      port({ id: 'accepted', name: 'Improved', type: 'boolean' }),
      port({ id: 'reason', name: 'Reason', type: 'string' }),
      port({ id: 'baseline', name: 'Baseline (in/out of sample)', type: 'object' }),
    ],
    configSchema: z.object({
      boundsJson: z.string().max(8_000).default(''),
      k: z.number().int().min(1).max(5).default(3),
      generations: z.number().int().min(1).max(3).default(2),
      splitPct: z.number().min(0.5).max(0.95).default(0.7),
      minValidationTrades: z.number().int().min(2).max(1_000).default(10),
      minLiftR: z.number().min(0).max(100).default(0.02),
      seed: z.number().int().min(0).max(1_000_000_000).default(7),
      equity: z.number().min(0).max(1_000_000_000_000_000).default(0),
    }),
    defaultConfig: () => ({
      boundsJson: '', k: 3, generations: 2, splitPct: 0.7,
      minValidationTrades: 10, minLiftR: 0.02, seed: 7, equity: 0,
    }),
    capabilities: [],
    sideEffects: 'none',
    allowedModes: [...ALL_MODES],
    docs: 'Proposes and measures only; it changes nothing. Variants are mutated from previously measured states (including losers), but acceptance compares against the current champion on the HOLDOUT window. The operator bounds are authority; the climb can only tighten and only inside them. All numbers are a simulation over recorded trades.',
  },
  {
    type: 'trade.commit',
    version: '1.0.0',
    category: 'learning',
    label: 'Commit playbook',
    description: 'Appends a playbook version the risk gate enforces; operator run only.',
    icon: 'check',
    inputs: [
      port({ id: 'candidate', name: 'Candidate', type: 'object' }),
      port({ id: 'bounds', name: 'Bounds', type: 'object', optional: true }),
    ],
    outputs: [
      port({ id: 'playbook', name: 'Active playbook', type: 'object' }),
      port({ id: 'changed', name: 'Changed', type: 'boolean' }),
      port({ id: 'revertsAt', name: 'Reverts at', type: 'string' }),
    ],
    configSchema: z.object({
      reason: z.string().max(500).default('operator commit'),
      ttlDays: z.number().int().min(1).max(90).default(14),
    }),
    defaultConfig: () => ({ reason: 'operator commit', ttlDays: 14 }),
    capabilities: ['learning.write', 'learning.self_modify'],
    sideEffects: 'write',
    allowedModes: [...ALL_MODES],
    docs: 'Append-only on the runtime store. The runtime re-validates every change against the operator bounds and refuses any transition that widens risk (`NOT_A_TIGHTENING` / `OUT_OF_BOUNDS`). A test run is refused. It never places or modifies an order.',
  },
  {
    type: 'trade.playbook',
    version: '1.0.0',
    category: 'learning',
    label: 'Read playbook',
    description: 'Reads the active risk envelope and its version history.',
    icon: 'activity',
    inputs: [],
    outputs: [
      port({ id: 'playbook', name: 'Playbook', type: 'object' }),
      port({ id: 'versions', name: 'Versions', type: 'array' }),
      port({ id: 'provenance', name: 'Provenance', type: 'object' }),
    ],
    configSchema: z.object({
      includeHistory: z.boolean().default(false),
      limit: z.number().int().min(1).max(50).default(10),
    }),
    defaultConfig: () => ({ includeHistory: false, limit: 10 }),
    capabilities: ['learning.read'],
    sideEffects: 'read',
    allowedModes: [...ALL_MODES],
    docs: 'Feeds `trading.risk_check` so future orders are gated by the learned envelope. A missing playbook is an explicit null, never an empty object pretending to be a policy.',
  },
];
