import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  LEGACY_UPDATED_AT,
  newBotStateEnvelope,
  readLocalEnvelope,
  shouldAdoptRemote,
  shouldPushLocal,
  writeLocalEnvelope,
} from './state-sync';

function fakeLocalStorage() {
  const map = new Map<string, string>();
  return {
    getItem: (key: string) => map.get(key) ?? null,
    setItem: (key: string, value: string) => void map.set(key, value),
    removeItem: (key: string) => void map.delete(key),
    clear: () => map.clear(),
    key: (index: number) => [...map.keys()][index] ?? null,
    get length() {
      return map.size;
    },
  };
}

describe('bot state mirror — envelope handling', () => {
  beforeEach(() => {
    vi.stubGlobal('window', { localStorage: fakeLocalStorage() });
  });
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('round-trips a version-2 envelope', () => {
    const envelope = newBotStateEnvelope({ b1: [] }, new Date('2026-05-01T10:00:00Z'));
    writeLocalEnvelope('be_test', envelope);
    expect(readLocalEnvelope('be_test')).toEqual(envelope);
  });

  it('upgrades a legacy document instead of discarding it', () => {
    window.localStorage.setItem('be_test', JSON.stringify({ b1: [{ id: 'm1' }] }));
    const envelope = readLocalEnvelope<{ b1: Array<{ id: string }> }>('be_test');
    expect(envelope?.updatedAt).toBe(LEGACY_UPDATED_AT);
    expect(envelope?.data.b1[0].id).toBe('m1');
  });

  it('returns null for absent or corrupt storage', () => {
    expect(readLocalEnvelope('missing')).toBeNull();
    window.localStorage.setItem('be_test', '{not json');
    expect(readLocalEnvelope('be_test')).toBeNull();
  });
});

describe('bot state mirror — newest timestamp wins', () => {
  it('adopts a server copy only when it is newer', () => {
    expect(shouldAdoptRemote(undefined, '2026-01-01T00:00:00Z')).toBe(true);
    expect(shouldAdoptRemote('2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z')).toBe(true);
    expect(shouldAdoptRemote('2026-01-02T00:00:00Z', '2026-01-01T00:00:00Z')).toBe(false);
    expect(shouldAdoptRemote('2026-01-02T00:00:00Z', '2026-01-02T00:00:00Z')).toBe(false);
    expect(shouldAdoptRemote('2026-01-01T00:00:00Z', 'not-a-date')).toBe(false);
  });

  it('pushes a local copy only when it is strictly newer', () => {
    expect(shouldPushLocal('2026-01-02T00:00:00Z', '2026-01-01T00:00:00Z')).toBe(true);
    expect(shouldPushLocal('2026-01-01T00:00:00Z', '2026-01-02T00:00:00Z')).toBe(false);
    expect(shouldPushLocal('2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')).toBe(false);
    expect(shouldPushLocal(undefined, '2026-01-01T00:00:00Z')).toBe(false);
  });
});
