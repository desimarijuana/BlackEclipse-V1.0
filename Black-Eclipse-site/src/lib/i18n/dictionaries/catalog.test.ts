import { describe, expect, it } from 'vitest';
import { catalog } from './index';
import { en } from './en';

// Dictionary integrity beyond the existing "every key translates" check:
//   * a non-English locale must not define a key English lacks (an orphan key
//     that can never be reached and silently rots);
//   * the catalog must expose every registered locale (a locale added to
//     `locales.ts` but not wired here would silently fall back to English).
// These are real drift classes a type-level `Partial` cannot catch.

const englishKeys = new Set(Object.keys(en));

describe('dictionary integrity', () => {
  it('no locale defines a key English does not have', () => {
    for (const [code, dict] of Object.entries(catalog)) {
      if (code === 'en') continue;
      const orphans = Object.keys(dict as Record<string, string>).filter((k) => !englishKeys.has(k));
      expect(orphans, `${code} defines keys missing from English`).toEqual([]);
    }
  });

  it('English is the complete canonical set (non-empty, unique)', () => {
    const keys = Object.keys(en);
    expect(keys.length).toBeGreaterThan(0);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it('every English value is a non-empty string', () => {
    for (const [key, value] of Object.entries(en)) {
      expect(typeof value, key).toBe('string');
      expect((value as string).trim().length, key).toBeGreaterThan(0);
    }
  });
});
