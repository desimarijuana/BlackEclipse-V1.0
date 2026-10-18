import { describe, expect, it } from 'vitest';
import { getNodeDefinition, listNodeDefinitions, nodesByCategory } from './registry';
import { validateConfig } from './validation';

describe('node registry', () => {
  const defs = listNodeDefinitions();

  it('has unique type@version keys', () => {
    const keys = defs.map((d) => `${d.type}@${d.version}`);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('every definition has unique port ids per direction', () => {
    for (const def of defs) {
      const inIds = def.inputs.map((p) => p.id);
      const outIds = def.outputs.map((p) => p.id);
      expect(new Set(inIds).size, def.type).toBe(inIds.length);
      expect(new Set(outIds).size, def.type).toBe(outIds.length);
    }
  });

  it('every default config validates against its own schema', () => {
    for (const def of defs) {
      expect(validateConfig(def, def.defaultConfig()), def.type).toBeNull();
    }
  });

  it('resolves by type and by type+version', () => {
    expect(getNodeDefinition('output.result')?.terminal).toBe(true);
    expect(getNodeDefinition('output.result', '1.0.0')?.type).toBe('output.result');
    expect(getNodeDefinition('does.not.exist')).toBeUndefined();
  });

  it('groups nodes by category', () => {
    const groups = nodesByCategory();
    expect(Object.keys(groups).length).toBeGreaterThan(0);
    expect(groups.trigger.some((d) => d.type === 'trigger.manual')).toBe(true);
  });
});
