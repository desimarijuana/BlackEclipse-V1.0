import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  DEFAULT_GENERAL_PREFS,
  GENERAL_PREFS_KEY,
  loadGeneralPrefs,
  normalizeGeneralPrefs,
  saveGeneralPrefs,
} from './general-prefs';

const memory = new Map<string, string>();

beforeEach(() => {
  memory.clear();
  vi.stubGlobal('window', {});
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => memory.get(key) ?? null,
    setItem: (key: string, value: string) => void memory.set(key, value),
    removeItem: (key: string) => void memory.delete(key),
  });
});

describe('normalizeGeneralPrefs', () => {
  it('returns defaults for junk input', () => {
    expect(normalizeGeneralPrefs(null)).toEqual(DEFAULT_GENERAL_PREFS);
    expect(normalizeGeneralPrefs('nope')).toEqual(DEFAULT_GENERAL_PREFS);
  });

  it('ignores a legacy startScreen key', () => {
    expect(normalizeGeneralPrefs({ startScreen: 'history' })).toEqual(DEFAULT_GENERAL_PREFS);
    expect(normalizeGeneralPrefs({ startScreen: 'portfolio' })).toEqual(DEFAULT_GENERAL_PREFS);
  });

  it('defaults confirmDestructive to true unless explicitly off', () => {
    expect(normalizeGeneralPrefs({}).confirmDestructive).toBe(true);
    expect(normalizeGeneralPrefs({ confirmDestructive: false }).confirmDestructive).toBe(false);
  });
});

describe('persistence', () => {
  it('round-trips through localStorage', () => {
    saveGeneralPrefs({ confirmDestructive: false });
    expect(JSON.parse(memory.get(GENERAL_PREFS_KEY)!)).toEqual({ confirmDestructive: false });
    expect(loadGeneralPrefs()).toEqual({ confirmDestructive: false });
  });

  it('falls back to defaults on corrupted JSON', () => {
    memory.set(GENERAL_PREFS_KEY, '{not json');
    expect(loadGeneralPrefs()).toEqual(DEFAULT_GENERAL_PREFS);
  });
});
