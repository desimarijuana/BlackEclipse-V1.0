import { beforeEach, describe, expect, it, vi } from 'vitest';

const store = vi.hoisted(() => new Map<string, string>());

vi.mock('@/lib/settings', () => ({
  getConfig: async (key: string) => store.get(key) ?? null,
  setConfig: async (key: string, value: string) => {
    store.set(key, value);
  },
}));

import {
  THEME_PRESETS_CONFIG_KEY,
  deleteSavedThemePreset,
  findSavedThemePreset,
  listSavedThemePresets,
  saveSavedThemePreset,
} from './theme-presets';

beforeEach(() => store.clear());

describe('app-wide named theme presets', () => {
  it('saves, lists and finds a named ThemeSpec', async () => {
    const saved = await saveSavedThemePreset('Neon', { brand: '#ff2bd6', scheme: 'dark' });
    expect(saved.name).toBe('Neon');
    expect(saved.theme.colors.primary).toBe('#ff2bd6');
    expect(store.has(THEME_PRESETS_CONFIG_KEY)).toBe(true);

    const listed = await listSavedThemePresets();
    expect(listed.map((preset) => preset.name)).toEqual(['Neon']);
    expect((await findSavedThemePreset('neon'))?.name).toBe('Neon');
  });

  it('overwrites a preset case-insensitively', async () => {
    await saveSavedThemePreset('Neon', { brand: '#ff2bd6' });
    await saveSavedThemePreset('neon', { brand: '#00e5ff' });
    const listed = await listSavedThemePresets();
    expect(listed).toHaveLength(1);
    expect(listed[0].theme.colors.primary).toBe('#00e5ff');
  });

  it('deletes only saved presets', async () => {
    await saveSavedThemePreset('Neon', { brand: '#ff2bd6' });
    expect(await deleteSavedThemePreset('NEON')).toBe(true);
    expect(await listSavedThemePresets()).toEqual([]);
    expect(await deleteSavedThemePreset('Neon')).toBe(false);
  });

  it('rejects an invalid name or spec', async () => {
    await expect(saveSavedThemePreset('', { brand: '#fff' })).rejects.toThrow();
    await expect(saveSavedThemePreset('bad/name', { brand: '#fff' })).rejects.toThrow();
    await expect(saveSavedThemePreset('Neon', { brand: 'nope' })).rejects.toThrow();
  });
});
