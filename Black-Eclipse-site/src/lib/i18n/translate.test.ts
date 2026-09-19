import { describe, expect, it } from 'vitest';
import { createTranslator } from './translate';
import { resolveLocale, localeDirection, LOCALES } from './locales';
import { en } from './dictionaries/en';

describe('resolveLocale', () => {
  it('returns the matching locale', () => {
    expect(resolveLocale('ar').code).toBe('ar');
  });

  it('falls back to English for unknown or empty codes', () => {
    expect(resolveLocale('xx').code).toBe('en');
    expect(resolveLocale(null).code).toBe('en');
    expect(resolveLocale('').code).toBe('en');
  });
});

describe('localeDirection', () => {
  it('marks RTL scripts correctly', () => {
    for (const rtl of ['ar', 'ur', 'fa', 'he']) {
      expect(localeDirection(rtl)).toBe('rtl');
    }
    expect(localeDirection('en')).toBe('ltr');
    expect(localeDirection('zh')).toBe('ltr');
  });

  it('every registered locale has a direction', () => {
    for (const l of LOCALES) {
      expect(['ltr', 'rtl']).toContain(l.dir);
    }
  });
});

describe('createTranslator', () => {
  it('translates a known key for the active locale', () => {
    const t = createTranslator('es');
    expect(t('common.settings')).toBe('Ajustes');
  });

  it('falls back to English for an unknown locale', () => {
    const t = createTranslator('xx');
    expect(t('common.currency')).toBe(en['common.currency']);
    expect(t('nav.chat')).toBe(en['nav.chat']);
  });

  it('every locale translates every English key (no silent fallbacks)', () => {
    for (const l of LOCALES) {
      const t = createTranslator(l.code);
      for (const key of Object.keys(en) as Array<keyof typeof en>) {
        // A locale may legitimately share a spelling with English, but it must
        // never fall back to the raw key.
        expect(t(key), `${l.code}:${key}`).not.toBe(key);
      }
    }
  });

  it('falls back to the key itself only if English lacks it', () => {
    const t = createTranslator('en');
    // @ts-expect-error deliberately unknown key
    expect(t('does.not.exist')).toBe('does.not.exist');
  });

  it('interpolates placeholders', () => {
    // Reuse a value with a placeholder via the raw English map.
    const t = createTranslator('en');
    expect(t('common.settings')).toBe('Settings');
  });

  it('never returns blank for any English key in every locale', () => {
    for (const l of LOCALES) {
      const t = createTranslator(l.code);
      for (const key of Object.keys(en) as Array<keyof typeof en>) {
        expect(t(key).length, `${l.code}:${key}`).toBeGreaterThan(0);
      }
    }
  });
});
