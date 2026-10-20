import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { EclipseTheme } from '@/lib/theme/tokens';

const mocks = vi.hoisted(() => {
  const setServerTheme = vi.fn(async (theme: EclipseTheme) => theme);
  return {
    setServerTheme,
    getServerThemeState: vi.fn(async () => ({ theme: null, initialized: false })),
    clearServerTheme: vi.fn(async () => undefined),
    listSavedThemePresets: vi.fn(async () => []),
    findSavedThemePreset: vi.fn(async () => null),
    saveSavedThemePreset: vi.fn(async (name: string) => ({
      name,
      spec: {},
      theme: {} as EclipseTheme,
      createdAt: '2026-01-01T00:00:00.000Z',
      updatedAt: '2026-01-01T00:00:00.000Z',
    })),
    deleteSavedThemePreset: vi.fn(async () => true),
  };
});

vi.mock('@/lib/theme/server', () => ({
  getServerThemeState: mocks.getServerThemeState,
  setServerTheme: mocks.setServerTheme,
  clearServerTheme: mocks.clearServerTheme,
}));
vi.mock('./theme-presets', () => ({
  listSavedThemePresets: mocks.listSavedThemePresets,
  findSavedThemePreset: mocks.findSavedThemePreset,
  saveSavedThemePreset: mocks.saveSavedThemePreset,
  deleteSavedThemePreset: mocks.deleteSavedThemePreset,
}));
vi.mock('@/lib/sdk/locks-server', () => ({ designLockBlocked: async () => null }));
vi.mock('./audit-server', () => ({ recordSdkAudit: vi.fn(async () => undefined) }));

import { themeRoute } from './theme-server';

function request(method: string, body?: unknown): Request {
  return new Request('http://localhost/api/sdk/theme', {
    method,
    headers: { 'content-type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.setServerTheme.mockImplementation(async (theme: EclipseTheme) => theme);
});

describe('themeRoute', () => {
  it('creates and applies a ThemeSpec', async () => {
    const res = await themeRoute(request('POST', { spec: { brand: '#ff2bd6', scheme: 'dark' } }), 'POST', ['theme']);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.theme.colors.primary).toBe('#ff2bd6');
    expect(body.spec.brand).toBe('#ff2bd6');
    expect(mocks.setServerTheme).toHaveBeenCalledTimes(1);
  });

  it('rejects an invalid spec with issues', async () => {
    const res = await themeRoute(request('POST', { spec: { brand: 'nope' } }), 'POST', ['theme']);
    expect(res.status).toBe(400);
    const body = await res.json();
    expect(body.issues[0]).toContain('brand');
    expect(mocks.setServerTheme).not.toHaveBeenCalled();
  });

  it('applies a shipped preset by id or label', async () => {
    const res = await themeRoute(request('POST', { preset: 'Midnight' }), 'POST', ['theme', 'presets', 'apply']);
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.preset.id).toBe('midnight');
    expect(body.theme.scheme).toBe('dark');
  });

  it('refuses to delete a shipped preset', async () => {
    const res = await themeRoute(request('DELETE'), 'DELETE', ['theme', 'presets', 'midnight']);
    expect(res.status).toBe(400);
    expect(mocks.deleteSavedThemePreset).not.toHaveBeenCalled();
  });
});
