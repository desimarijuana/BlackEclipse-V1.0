import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_ECLIPSE_THEME, normalizeTheme } from './tokens';

const THEME_KEY = 'be_theme_v1';
const PRESETS_KEY = 'be_theme_presets_v1';
const values = new Map<string, string>();

const storage = {
  getItem: vi.fn((name: string) => values.get(name) ?? null),
  setItem: vi.fn((name: string, value: string) => { values.set(name, value); }),
  removeItem: vi.fn((name: string) => { values.delete(name); }),
};

/** Minimal <html> + <head> stub so applyThemeToDocument can run in node. */
function makeElement() {
  const classes = new Set<string>();
  return {
    classList: {
      add: (c: string) => classes.add(c),
      remove: (...c: string[]) => c.forEach((x) => classes.delete(x)),
      toggle: (c: string, on?: boolean) => { if (on) classes.add(c); else classes.delete(c); },
      contains: (c: string) => classes.has(c),
    },
    style: { setProperty: vi.fn(), removeProperty: vi.fn() },
    _classes: classes,
  };
}

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  values.clear();
  const root = makeElement();
  const head = { appendChild: vi.fn(), children: [] as unknown[] };
  vi.stubGlobal('window', { localStorage: storage });
  vi.stubGlobal('document', {
    documentElement: root,
    head,
    createElement: vi.fn(() => ({ id: '', textContent: '', rel: '', href: '' })),
    getElementById: vi.fn(() => null),
    querySelector: vi.fn(() => null),
    title: '',
  });
});

afterEach(() => vi.unstubAllGlobals());

describe('user theme presets', () => {
  it('saves the current theme, persists it, and lists it newest-first', async () => {
    const { useThemeStore } = await import('./store');
    const s = useThemeStore.getState();
    s.hydrate();

    useThemeStore.getState().setColor('primary', '#ff6600');
    const id1 = useThemeStore.getState().saveUserPreset('Sunset');
    useThemeStore.getState().setColor('primary', '#0066ff');
    const id2 = useThemeStore.getState().saveUserPreset('Ocean');

    const presets = useThemeStore.getState().userPresets;
    expect(presets).toHaveLength(2);
    expect(presets[0].id).toBe(id2);
    expect(presets[0].label).toBe('Ocean');
    expect(presets[1].id).toBe(id1);
    expect(presets[1].theme.colors.primary).toBe('#ff6600');
    expect(values.has(PRESETS_KEY)).toBe(true);
  });

  it('renames, updates and deletes a preset', async () => {
    const { useThemeStore } = await import('./store');
    useThemeStore.getState().hydrate();
    const id = useThemeStore.getState().saveUserPreset('Draft');

    useThemeStore.getState().renameUserPreset(id, 'Refined');
    expect(useThemeStore.getState().userPresets[0].label).toBe('Refined');

    useThemeStore.getState().setColor('primary', '#123456');
    useThemeStore.getState().updateUserPreset(id);
    expect(useThemeStore.getState().userPresets[0].theme.colors.primary).toBe('#123456');

    useThemeStore.getState().deleteUserPreset(id);
    expect(useThemeStore.getState().userPresets).toHaveLength(0);
  });

  it('falls back to a default label when the name is blank', async () => {
    const { useThemeStore } = await import('./store');
    useThemeStore.getState().hydrate();
    useThemeStore.getState().saveUserPreset('   ');
    expect(useThemeStore.getState().userPresets[0].label).toBe('My Theme');
  });

  it('rehydrates persisted presets after a reload', async () => {
    const { useThemeStore } = await import('./store');
    useThemeStore.getState().hydrate();
    useThemeStore.getState().saveUserPreset('Persisted');

    // Simulate a fresh module load reading the same localStorage.
    vi.resetModules();
    const again = await import('./store');
    again.useThemeStore.getState().hydrate();
    expect(again.useThemeStore.getState().userPresets).toHaveLength(1);
    expect(again.useThemeStore.getState().userPresets[0].label).toBe('Persisted');
    expect(again.useThemeStore.getState().userPresets[0].theme.colors.primary)
      .toBe(DEFAULT_ECLIPSE_THEME.colors.primary);
  });

  it('reset clears the active theme but keeps saved presets', async () => {
    const { useThemeStore } = await import('./store');
    useThemeStore.getState().hydrate();
    const id = useThemeStore.getState().saveUserPreset('Keep me');
    useThemeStore.getState().setColor('primary', '#abcdef');
    useThemeStore.getState().reset();

    expect(useThemeStore.getState().theme.colors.primary).toBe(DEFAULT_ECLIPSE_THEME.colors.primary);
    expect(useThemeStore.getState().customized).toBe(false);
    expect(useThemeStore.getState().userPresets.map((p) => p.id)).toEqual([id]);
    expect(values.has(THEME_KEY)).toBe(false);
  });
});

describe('theme normalization from import', () => {
  it('coerces a partial imported theme to a full theme', () => {
    const imported = normalizeTheme({ colors: { primary: '#101010' }, radius: 0.2 });
    expect(imported.colors.primary).toBe('#101010');
    expect(imported.radius).toBe(0.2);
    expect(imported.glass.enabled).toBe(true);
    expect(imported.fontScale).toBe(1);
  });
});
