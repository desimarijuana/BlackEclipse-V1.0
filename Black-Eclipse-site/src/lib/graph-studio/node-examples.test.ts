import { describe, expect, it } from 'vitest';
import { EXAMPLE_NODE_TYPES, exampleFor } from './node-examples';
import { getNodeDefinition, listNodeDefinitions } from './registry';

describe('node examples', () => {
  it('covers every logic and control-flow node', () => {
    const pack = listNodeDefinitions()
      .filter((def) => def.type.startsWith('logic.') || def.type.startsWith('flow.'))
      .map((def) => def.type);
    const missing = pack.filter((type) => !exampleFor(type));
    expect(missing).toEqual([]);
  });

  it('only names node types that exist', () => {
    const unknown = EXAMPLE_NODE_TYPES.filter((type) => !getNodeDefinition(type));
    expect(unknown).toEqual([]);
  });

  it('keeps each example short enough for the inspector', () => {
    for (const type of EXAMPLE_NODE_TYPES) {
      const example = exampleFor(type)!;
      expect(example.length, type).toBeGreaterThan(10);
      expect(example.length, type).toBeLessThanOrEqual(200);
    }
  });

  it('shows the arrow form so input and output are distinguishable', () => {
    expect(exampleFor('logic.filter')).toContain('→');
  });
});
