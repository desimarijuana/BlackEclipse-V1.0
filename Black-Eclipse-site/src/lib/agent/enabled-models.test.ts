import { describe, it, expect } from 'vitest';
import { compactModels, MODEL_LIST_SOFT_LIMIT } from './enabled-models';

describe('compactModels', () => {
  const all = Array.from({ length: 100 }, (_, i) => `model-${String(i).padStart(3, '0')}`);

  it('caps an uncurated provider at the soft limit and flags truncation', () => {
    const { models, truncated, curated } = compactModels('openrouter', all);
    expect(curated).toBe(false);
    expect(truncated).toBe(true);
    expect(models).toHaveLength(MODEL_LIST_SOFT_LIMIT);
  });

  it('shows every model for a small uncurated provider', () => {
    const { models, truncated } = compactModels('ollama', ['a', 'b', 'c']);
    expect(truncated).toBe(false);
    expect(models).toEqual(['a', 'b', 'c']);
  });

  it('returns exactly the enabled ids, in catalog order, for a curated provider', () => {
    const enabled = ['model-050', 'model-003', 'model-099'];
    const { models, curated, truncated } = compactModels('openrouter', all, {
      explicitEnabled: enabled,
    });
    expect(curated).toBe(true);
    expect(truncated).toBe(false);
    // Catalog order, not enable order.
    expect(models).toEqual(['model-003', 'model-050', 'model-099']);
  });

  it('keeps a selected model visible even when the catalog no longer lists it', () => {
    const { models } = compactModels('openrouter', ['model-001'], {
      explicitEnabled: ['model-001'],
      selected: 'custom/typed-id',
    });
    expect(models).toContain('model-001');
    expect(models).toContain('custom/typed-id');
  });

  it('keeps an enabled id that fell out of the catalog (custom/discovered)', () => {
    const { models } = compactModels('openrouter', ['model-001'], {
      explicitEnabled: ['model-001', 'gone/but-enabled'],
    });
    expect(models).toContain('gone/but-enabled');
  });

  it('an empty curated set yields no models (the user disabled all)', () => {
    const { models, curated } = compactModels('openrouter', all, { explicitEnabled: [] });
    expect(curated).toBe(true);
    expect(models).toEqual([]);
  });

  it('keeps the newest models when an uncurated list is truncated', () => {
    // `all` ascends model-000 … model-099, so newest-first must keep the tail.
    const { models, truncated } = compactModels('openrouter', all);
    expect(truncated).toBe(true);
    expect(models[0]).toBe('model-099');
    expect(models).not.toContain('model-000');
  });
});
