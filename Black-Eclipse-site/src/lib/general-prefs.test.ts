import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  DEFAULT_GENERAL_PREFS,
  GENERAL_PREFS_KEY,
  loadGeneralPrefs,
  normalizeGeneralPrefs,
  recordLastTab,
  resolveStartTab,
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

  it('keeps a valid start screen and rejects unknown tabs', () => {
    expect(normalizeGeneralPrefs({ startScreen: 'history' }).startScreen).toBe('history');
    expect(normalizeGeneralPrefs({ startScreen: 'portfolio' }).startScreen).toBe('portfolio');
    expect(normalizeGeneralPrefs({ startScreen: 'settings' }).startScreen).toBe('chat');
    expect(normalizeGeneralPrefs({ startScreen: 'skills' }).startScreen).toBe('chat');
  });

  it('defaults confirmDestructive to true unless explicitly off', () => {
    expect(normalizeGeneralPrefs({}).confirmDestructive).toBe(true);
    expect(normalizeGeneralPrefs({ confirmDestructive: false }).confirmDestructive).toBe(false);
  });
});

describe('persistence', () => {
  it('round-trips through localStorage', () => {
    saveGeneralPrefs({ startScreen: 'dashboard', confirmDestructive: false });
    expect(JSON.parse(memory.get(GENERAL_PREFS_KEY)!)).toEqual({
      startScreen: 'dashboard',
      confirmDestructive: false,
    });
    expect(loadGeneralPrefs()).toEqual({ startScreen: 'dashboard', confirmDestructive: false });
  });

  it('falls back to defaults on corrupted JSON', () => {
    memory.set(GENERAL_PREFS_KEY, '{not json');
    expect(loadGeneralPrefs()).toEqual(DEFAULT_GENERAL_PREFS);
  });
});

describe('resolveStartTab', () => {
  it('returns the fixed start screen', () => {
    expect(resolveStartTab({ startScreen: 'portfolio', confirmDestructive: true })).toBe('portfolio');
  });

  it('restores the last visited tab when startScreen is history', () => {
    recordLastTab('news');
    // news is not a valid start tab — falls back to null.
    expect(resolveStartTab({ startScreen: 'history', confirmDestructive: true })).toBeNull();

    recordLastTab('portfolio');
    expect(resolveStartTab({ startScreen: 'history', confirmDestructive: true })).toBe('portfolio');
  });

  it('returns null for history with nothing recorded', () => {
    expect(resolveStartTab({ startScreen: 'history', confirmDestructive: true })).toBeNull();
  });
});
