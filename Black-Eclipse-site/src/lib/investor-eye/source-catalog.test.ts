import { describe, it, expect } from 'vitest';
import {
  SOURCE_CATALOG, catalogFor, hasCatalogEntry, requiredAttributions,
  COMMERCIAL_USE_LABEL,
} from './source-catalog';
import { listSources, registerBuiltinSources } from './sources/registry';

describe('source catalog', () => {
  it('has a unique id per entry', () => {
    const ids = SOURCE_CATALOG.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it('fills every governance field the spec requires (§6)', () => {
    for (const e of SOURCE_CATALOG) {
      expect(e.id.length).toBeGreaterThan(0);
      expect(e.name.length).toBeGreaterThan(0);
      expect(e.provider.length).toBeGreaterThan(0);
      expect(e.website).toMatch(/^https:\/\//);
      expect(e.license.length).toBeGreaterThan(0);
      expect(['yes', 'no', 'unknown']).toContain(e.commercialUse);
      expect(typeof e.requiresApiKey).toBe('boolean');
      expect(typeof e.attributionRequired).toBe('boolean');
      expect(['seconds', 'minutes', 'hourly', 'daily', 'static']).toContain(e.dataFreshness);
      expect(e.note.length).toBeGreaterThan(0);
    }
  });

  it('states the attribution text whenever attribution is required', () => {
    for (const e of SOURCE_CATALOG) {
      if (e.attributionRequired) {
        expect(e.attribution, `${e.id} requires attribution but has none`).toBeTruthy();
      }
    }
  });

  it('links a license or terms reference for every non-local entry', () => {
    for (const e of SOURCE_CATALOG) {
      // Local data (the app's own RSS corpus) has no third-party license; the
      // upstream feeds declare their own terms individually.
      if (e.local) continue;
      expect(e.licenseUrl ?? e.termsUrl, `${e.id} has no license/terms link`).toBeTruthy();
    }
  });

  // The regression guard that matters: a new adapter cannot ship without its
  // license declared. Registration and governance must land together.
  it('has a catalog entry for EVERY registered source', () => {
    registerBuiltinSources();
    for (const s of listSources()) {
      expect(hasCatalogEntry(s.id), `source '${s.id}' has no catalog entry`).toBe(true);
    }
    expect(listSources().length).toBeGreaterThan(0);
  });

  it('does not declare entries for sources that are not registered', () => {
    registerBuiltinSources();
    const registered = new Set(listSources().map((s) => s.id));
    for (const e of SOURCE_CATALOG) {
      // 'news' and all fetchers are registered built-ins; an entry with no
      // adapter would document a fiction.
      expect(registered.has(e.id), `catalog entry '${e.id}' has no registered source`).toBe(true);
    }
  });

  it('uses https and a commercial-use label for every value', () => {
    for (const e of SOURCE_CATALOG) {
      expect(COMMERCIAL_USE_LABEL[e.commercialUse]).toBeTruthy();
    }
  });

  it('agrees with the adapter on whether a credential is required', () => {
    registerBuiltinSources();
    for (const s of listSources()) {
      const entry = catalogFor(s.id);
      expect(entry, `missing entry for ${s.id}`).toBeDefined();
      // A key-gated adapter must be recorded as key-required, and vice versa —
      // otherwise the settings UI would tell the operator the wrong thing.
      expect(entry!.requiresApiKey).toBe(s.requiresCredentials);
    }
  });
});

describe('requiredAttributions', () => {
  it('returns the catalog attribution lines that must be shown', () => {
    const lines = requiredAttributions();
    expect(lines.some((l) => /GDELT/i.test(l))).toBe(true);
    expect(lines.some((l) => /FIRMS/i.test(l))).toBe(true);
  });

  it('deduplicates and scopes to the requested ids', () => {
    expect(requiredAttributions(['gdelt', 'gdelt'])).toEqual(requiredAttributions(['gdelt']));
    expect(requiredAttributions(['usgs'])).toEqual([]); // USGS requires none
  });

  it('returns nothing for an unknown id rather than inventing credit', () => {
    expect(requiredAttributions(['nope'])).toEqual([]);
  });
});
