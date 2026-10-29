import { describe, expect, it } from 'vitest';
import {
  STUDIO_STORAGE_KEY,
  applyDeepLink,
  clearWorkspace,
  defaultWorkspace,
  loadWorkspace,
  parseWorkspace,
  saveWorkspace,
  workspaceQuery,
  type StorageLike,
} from './workspace';

function memoryStorage(seed: Record<string, string> = {}): StorageLike {
  const map = new Map(Object.entries(seed));
  return {
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => void map.set(key, value),
    removeItem: (key) => void map.delete(key),
  };
}

describe('studio workspace', () => {
  it('round-trips a workspace through storage', () => {
    const storage = memoryStorage();
    const workspace = { ...defaultWorkspace(), prompt: 'buy the dip', editor: '{"a":1}', strategyId: 'ema_cross', capital: 25000 };
    expect(saveWorkspace(workspace, storage)).toBe(true);
    const loaded = loadWorkspace(storage);
    expect(loaded?.prompt).toBe('buy the dip');
    expect(loaded?.editor).toBe('{"a":1}');
    expect(loaded?.strategyId).toBe('ema_cross');
    expect(loaded?.capital).toBe(25000);
  });

  it('discards a corrupt or stale blob instead of throwing', () => {
    const corrupt = memoryStorage({ [STUDIO_STORAGE_KEY]: '{not json' });
    expect(loadWorkspace(corrupt)).toBeNull();
    const stale = memoryStorage({ [STUDIO_STORAGE_KEY]: JSON.stringify({ schema: 99 }) });
    expect(loadWorkspace(stale)).toBeNull();
  });

  it('falls back to sane values for a partly broken blob', () => {
    const parsed = parseWorkspace({
      schema: 1,
      editor: 42,
      prompt: null,
      symbol: null,
      capital: -5,
      strategyId: '   ',
    });
    expect(parsed).not.toBeNull();
    expect(parsed?.prompt).toBe('');
    expect(parsed?.editor).toBe('');
    expect(parsed?.symbol).toBe(defaultWorkspace().symbol);
    expect(parsed?.capital).toBe(defaultWorkspace().capital);
    expect(parsed?.strategyId).toBeNull();
  });

  it('reads a deep link without touching the rest of the workspace', () => {
    const workspace = { ...defaultWorkspace(), editor: 'body' };
    const linked = applyDeepLink(workspace, '?tab=strategy-studio&strategy=ema_cross&experiment=exp_1');
    expect(linked.strategyId).toBe('ema_cross');
    expect(linked.experimentId).toBe('exp_1');
    expect(linked.editor).toBe('body');
    expect(linked.wantsStrategy).toBe(true);
    expect(linked.wantsExperiment).toBe(true);
  });

  it('ignores a deep link with no strategy identifiers', () => {
    const linked = applyDeepLink(defaultWorkspace(), '?tab=strategy-studio');
    expect(linked.wantsStrategy).toBe(false);
    expect(linked.wantsExperiment).toBe(false);
  });

  it('builds the query string for the address bar', () => {
    const query = workspaceQuery({ strategyId: 'ema_cross', experimentId: null });
    const params = new URLSearchParams(query);
    expect(params.get('tab')).toBe('strategy-studio');
    expect(params.get('strategy')).toBe('ema_cross');
    expect(params.has('experiment')).toBe(false);
  });

  it('does nothing when storage is unavailable', () => {
    expect(loadWorkspace(null)).toBeNull();
    expect(saveWorkspace(defaultWorkspace(), null)).toBe(false);
    expect(() => clearWorkspace(null)).not.toThrow();
  });

  it('clears a saved workspace', () => {
    const storage = memoryStorage();
    saveWorkspace(defaultWorkspace(), storage);
    clearWorkspace(storage);
    expect(loadWorkspace(storage)).toBeNull();
  });
});
