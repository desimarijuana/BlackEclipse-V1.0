// Agent node contracts (Phase 7). Split out of `registry.ts` to keep the
// registry inside its size budget; the definitions are still declared once and
// spread into the ONE registry array.

import { z } from 'zod';
import type { NodeDefinition, PortDef } from './types';

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

export const AGENT_DEFINITIONS: NodeDefinition[] = [
  {
    type: 'agent.research',
    version: '1.0.0',
    category: 'agent',
    label: 'Research agent',
    description: 'Runs a bounded agent turn and returns a structured finding.',
    icon: 'bot',
    // Optional because the inspector's Objective field is a valid alternative
    // (the executor uses the input when present, else the configured value).
    inputs: [port({ id: 'query', name: 'Query', type: 'string', optional: true })],
    outputs: [
      port({ id: 'finding', name: 'Finding', type: 'research_finding' }),
      port({ id: 'evidence', name: 'Evidence', type: 'evidence' }),
    ],
    configSchema: z.object({
      agent: z.string().max(80).default('eclipse-agent'),
      /** 0 = the preset's current version; >0 pins an immutable snapshot. */
      agentVersion: z.number().int().min(0).max(1_000_000).default(0),
      objective: z.string().max(2_000).default(''),
      maxSteps: z.number().int().min(1).max(32).default(8),
    }),
    defaultConfig: () => ({ agent: 'eclipse-agent', agentVersion: 0, objective: '', maxSteps: 8 }),
    capabilities: ['agent.run'],
    sideEffects: 'model',
    allowedModes: ['research', 'backtest', 'paper', 'live'],
    docs: 'Invokes the existing Python agent runtime — not a second agent loop.',
  },
  {
    type: 'agent.plan',
    version: '1.0.0',
    category: 'agent',
    label: 'Plan steps',
    description: 'One bounded model call that proposes 1-8 independent steps.',
    icon: 'bot',
    inputs: [port({ id: 'objective', name: 'Objective', type: 'string', optional: true })],
    outputs: [
      port({ id: 'plan', name: 'Plan', type: 'object' }),
      port({ id: 'steps', name: 'Steps', type: 'array' }),
      port({ id: 'summary', name: 'Summary', type: 'object' }),
    ],
    configSchema: z.object({ objective: z.string().max(2_000).default('') }),
    defaultConfig: () => ({ objective: '' }),
    capabilities: ['agent.run'],
    sideEffects: 'model',
    allowedModes: ['research', 'backtest', 'paper', 'live'],
    docs: 'Returns a structured plan only; it never executes the steps. Wire them into agent.delegate or the graph.',
  },
  {
    type: 'agent.delegate',
    version: '1.0.0',
    category: 'agent',
    label: 'Delegate tasks',
    description: 'Runs up to six independent tasks as bounded agent turns.',
    icon: 'bot',
    inputs: [port({ id: 'tasks', name: 'Tasks', type: 'array', optional: true })],
    outputs: [
      port({ id: 'findings', name: 'Findings', type: 'array' }),
      port({ id: 'summary', name: 'Summary', type: 'object' }),
    ],
    configSchema: z.object({
      tasksJson: z.string().max(20_000).default(''),
      agent: z.string().max(80).default('eclipse-agent'),
      agentVersion: z.number().int().min(0).max(1_000_000).default(0),
      maxSteps: z.number().int().min(1).max(32).default(8),
      maxTasks: z.number().int().min(1).max(6).default(4),
    }),
    defaultConfig: () => ({
      tasksJson: '',
      agent: 'eclipse-agent',
      agentVersion: 0,
      maxSteps: 8,
      maxTasks: 4,
    }),
    capabilities: ['agent.run'],
    sideEffects: 'model',
    allowedModes: ['research', 'backtest', 'paper', 'live'],
    docs: 'Each task is one bounded turn on the existing agent plane; a failed part is reported as failed, never hidden.',
  },
];
