import { describe, expect, it } from 'vitest';
import checkedIn from './registry.manifest.json';
import { buildNodeManifest } from './manifest';
import { getNodeDefinition, listNodeDefinitions } from './registry';
import { validateConfig } from './validation';

describe('node registry manifest', () => {
  it('matches the checked-in cross-language contract', () => {
    expect(buildNodeManifest()).toEqual(checkedIn);
  });

  it('covers every registry node exactly once', () => {
    const manifestKeys = checkedIn.nodes.map((node) => `${node.type}@${node.version}`);
    const registryKeys = listNodeDefinitions()
      .map((definition) => `${definition.type}@${definition.version}`)
      .sort();
    expect(manifestKeys).toEqual(registryKeys);
    expect(new Set(manifestKeys).size).toBe(manifestKeys.length);
  });

  it('declares Set variables with a valid default config', () => {
    const definition = getNodeDefinition('data.set_variables');
    expect(definition).toBeDefined();
    expect(definition?.category).toBe('data');
    expect(validateConfig(definition!, {})).toBeNull();
    expect(validateConfig(definition!, { variables: { symbol: 'AAPL' } })).toBeNull();
  });

  it('classifies local datasets as local scratch, not world writes', () => {
    expect(getNodeDefinition('data.dataset.save')?.sideEffects).toBe('local_write');
    expect(getNodeDefinition('data.dataset.load')?.sideEffects).toBe('read');
    expect(validateConfig(getNodeDefinition('data.dataset.save')!, { name: 'bars', ttlHours: 24 })).toBeNull();
  });
});
