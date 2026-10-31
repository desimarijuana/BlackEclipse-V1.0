// Scoped write node contracts (Phase 5). Split out of `registry.ts` to keep the
// main registry under the size budget.

import { z } from 'zod';
import type { ExecutionMode, NodeDefinition, PortDef } from './types';

const ALL_MODES: ExecutionMode[] = ['research', 'backtest', 'paper', 'live'];

function port(p: PortDef): PortDef {
  return { kind: 'data', ...p };
}

export const WRITE_DEFINITIONS: NodeDefinition[] = [
  {
    type: 'file.write',
    version: '1.0.0',
    category: 'data',
    label: 'Write file',
    description: 'Writes a payload inside a named, operator-configured scope.',
    icon: 'text',
    inputs: [
      port({ id: 'content', name: 'Content', type: 'any' }),
      port({ id: 'path', name: 'Path', type: 'string', optional: true }),
    ],
    outputs: [
      port({ id: 'path', name: 'Path', type: 'string' }),
      port({ id: 'bytes', name: 'Bytes', type: 'number' }),
      port({ id: 'scope', name: 'Scope', type: 'string' }),
    ],
    configSchema: z.object({
      scope: z.string().max(80).default('workspace'),
      path: z.string().max(500).default(''),
      append: z.boolean().default(false),
    }),
    defaultConfig: () => ({ scope: 'workspace', path: '', append: false }),
    capabilities: ['file.write'],
    sideEffects: 'write',
    allowedModes: ALL_MODES,
    docs: 'Relative paths only; "..", absolute paths and symlink escapes are refused; 8 MB cap; normal writes are atomic. Requires an operator run that granted this scope.',
  },
];
