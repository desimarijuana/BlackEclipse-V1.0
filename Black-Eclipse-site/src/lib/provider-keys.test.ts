import { describe, it, expect } from 'vitest';
import { PROVIDER_KEYS, providerKeyDef, CATEGORY_LABELS } from './provider-keys';

// The vault's storage path touches Prisma + env, so these tests cover the pure
// registry contract — which is the part a new provider must satisfy. The
// encrypted round-trip is covered by the existing connectors/secrets tests.

describe('provider key registry', () => {
  it('has a unique env var per entry', () => {
    const vars = PROVIDER_KEYS.map((d) => d.envVar);
    expect(new Set(vars).size).toBe(vars.length);
  });

  it('fills every field the UI needs', () => {
    for (const def of PROVIDER_KEYS) {
      expect(def.envVar).toMatch(/^[A-Z0-9_]+$/);
      expect(def.label.length).toBeGreaterThan(0);
      expect(def.provider.length).toBeGreaterThan(0);
      expect(CATEGORY_LABELS[def.category]).toBeTruthy();
      expect(def.description.length).toBeGreaterThan(0);
    }
  });

  it('resolves by env var and rejects an unknown one', () => {
    expect(providerKeyDef('OPENAI_API_KEY')?.label).toBe('OpenAI');
    expect(providerKeyDef('NOT_A_REAL_KEY')).toBeUndefined();
  });

  it('only declares a test endpoint where a key is actually needed', () => {
    for (const def of PROVIDER_KEYS) {
      // A keyless provider (a plain base URL) must not advertise a test that
      // would send an empty credential.
      if (def.test) expect(def.publicValue).not.toBe(true);
    }
  });

  it('never exposes a plaintext value through the registry itself', () => {
    // The definitions carry metadata only — no `value` field anywhere.
    for (const def of PROVIDER_KEYS) {
      expect(Object.keys(def)).not.toContain('value');
      expect(Object.keys(def)).not.toContain('secret');
    }
  });

  it('covers every category the panel renders', () => {
    const used = new Set(PROVIDER_KEYS.map((d) => d.category));
    for (const c of ['ai', 'market', 'crypto', 'economics'] as const) {
      expect(used.has(c), `no providers declared for category ${c}`).toBe(true);
    }
  });

  it('gives every keyed provider a place to obtain the key', () => {
    for (const def of PROVIDER_KEYS) {
      if (def.publicValue) continue;
      // A secret with no docs link leaves the operator stranded.
      expect(def.docsUrl, `${def.envVar} has no docsUrl`).toBeTruthy();
    }
  });
});
