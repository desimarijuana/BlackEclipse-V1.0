// Typed-decision node contracts. The editor half of the pair; the runtime half
// is `python/harness/graph_runtime/decision_nodes.py`. Keep the two in lockstep
// and regenerate the manifest (`npm run graph:manifest`).
//
// A decision is INFORMATION, never authorization: these nodes have no write,
// network or trading effect and cannot widen a run's grants. `decision.ask` can
// reach a configured provider (so its class is `model`); `decision.demo` is the
// zero-config path — deterministic rules only, still audited locally.

import { z } from 'zod';
import type { NodeDefinition, PortDef } from './types';

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

const ALL_MODES = ['research', 'backtest', 'paper', 'live'] as const;

const OUTPUTS: PortDef[] = [
  port({ id: 'answers', name: 'Typed answers', type: 'object' }),
  port({ id: 'status', name: 'Status', type: 'string' }),
  port({ id: 'summary', name: 'Summary', type: 'string' }),
  port({ id: 'provider', name: 'Provider', type: 'string' }),
  port({ id: 'recordId', name: 'Audit record', type: 'string' }),
  port({ id: 'reason', name: 'Reason', type: 'string' }),
];

export const DECISION_DEFINITIONS: NodeDefinition[] = [
  {
    type: 'decision.ask',
    version: '1.0.0',
    category: 'decision',
    label: 'Typed decision',
    description: 'Ask choice / score / yes-no questions about a state and get typed answers.',
    icon: 'brain',
    inputs: [port({ id: 'state', name: 'State', type: 'object', optional: true })],
    outputs: OUTPUTS,
    configSchema: z.object({
      provider: z.string().max(80).default(''),
      questionsJson: z.string().max(20_000).default(''),
      stateJson: z.string().max(20_000).default(''),
      minConfidence: z.number().min(0).max(1).default(0.6),
      minProbability: z.number().min(0).max(1).default(0.6),
      timeoutMs: z.number().int().min(100).max(120_000).default(15_000),
    }),
    defaultConfig: () => ({
      provider: '',
      questionsJson: '',
      stateJson: '',
      minConfidence: 0.6,
      minProbability: 0.6,
      timeoutMs: 15_000,
    }),
    capabilities: ['decision.ask'],
    sideEffects: 'model',
    allowedModes: [...ALL_MODES],
    docs: 'A state plus a closed question template ({id: {type: "choice"|"score"|"noul", instructions, criteria?}}) in; typed answers out. `status` is the only field to branch on: `answered` cleared every policy threshold, `review` is a hint inside the abstain band, and `unavailable` means nothing was inferred. A partial answer, a type mismatch or a provider error is always `unavailable`, never a guess. An answer is a model judgment, never a verified financial fact or an authorization. The request is recorded on the audit trail.',
  },
  {
    type: 'decision.demo',
    version: '1.0.0',
    category: 'decision',
    label: 'Typed decision (demo)',
    description: 'Zero-config demonstration of a typed judgment — no key, no network.',
    icon: 'brain',
    inputs: [port({ id: 'state', name: 'State (optional)', type: 'object', optional: true })],
    outputs: OUTPUTS,
    configSchema: z.object({
      scenario: z.enum(['risk_gate', 'route_ticket']).default('risk_gate'),
    }),
    defaultConfig: () => ({ scenario: 'risk_gate' }),
    capabilities: ['decision.ask'],
    sideEffects: 'local_write',
    allowedModes: [...ALL_MODES],
    docs: 'Runs the SAME request → provider → confidence-policy → audit pipeline a real provider would, using the deterministic rule provider and a built-in sample state (a wired state overrides it). Use it to see the answer shape and the `answered` / `review` / `unavailable` status without configuring anything. The result is a demonstration, not a statement about your portfolio.',
  },
];
