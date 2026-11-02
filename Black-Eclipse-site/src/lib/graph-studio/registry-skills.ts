// Skill node contracts. Split out of `registry.ts` to keep the main registry
// under the size budget.
//
// ONE generic node, not one per installed skill: skills are runtime data
// (`skill.json` on disk), while this registry is a static contract with a
// generated manifest and a Python mirror. A per-skill node type would make the
// manifest depend on disk state and churn on every install. The inspector
// resolves `skillId` against the LIVE skill list instead.
//
// The node is a thin adapter over the existing skill runtime
// (`AgenticService.run_skill` → `skills/runtime.execute_skill`): no second
// skill runtime, tool allowlist or permission check.

import { z } from 'zod';
import type { ExecutionMode, NodeDefinition, PortDef } from './types';

const ALL_MODES: ExecutionMode[] = ['research', 'backtest', 'paper', 'live'];

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

export const SKILL_DEFINITIONS: NodeDefinition[] = [
  {
    type: 'skill.invoke',
    version: '1.0.0',
    category: 'skills',
    label: 'Run skill',
    description: 'Runs an installed skill through the existing skill runtime.',
    icon: 'sparkles',
    // Optional: the inspector's Input (JSON) is a valid alternative, and the
    // wire wins for the keys it supplies.
    inputs: [port({ id: 'input', name: 'Input', type: 'object', optional: true })],
    outputs: [
      port({ id: 'output', name: 'Output', type: 'string' }),
      port({ id: 'result', name: 'Result', type: 'object' }),
      port({ id: 'evidence', name: 'Evidence', type: 'array' }),
    ],
    configSchema: z.object({
      /** Empty is invalid at run time — the inspector's picker sets it. */
      skillId: z.string().max(120).default(''),
      /** Empty = the registry's current version; a value pins that snapshot. */
      version: z.string().max(40).default(''),
      inputJson: z.string().max(20_000).default(''),
      timeoutMs: z.number().int().min(1_000).max(900_000).default(300_000),
    }),
    defaultConfig: () => ({ skillId: '', version: '', inputJson: '', timeoutMs: 300_000 }),
    // A skill call is a model call on the agent plane: a test/dry run may run a
    // skill whose required tools are all read-only, and the runtime refuses one
    // that needs anything else (the node names the tools).
    capabilities: ['agent.run'],
    sideEffects: 'model',
    allowedModes: ALL_MODES,
    docs: 'Runs exactly the skill the chat surface runs, with the same permission check. A skill that is not enabled/executable, is missing a tool or is denied a permission FAILS this node with its code — it never returns an empty success. A test run may only execute a skill whose declared tools are all read-only.',
  },
];
