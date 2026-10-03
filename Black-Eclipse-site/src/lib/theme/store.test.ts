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
  vi.stubGlobal('window', { localStorage: storage, addEventListener: vi.fn() });
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

  it('captures the chart palette with a preset and restores it on apply', async () => {
    const { useThemeStore } = await import('./store');
    const { useChartPaletteStore } = await import('@/lib/chart-palette-store');
    useThemeStore.getState().hydrate();
    useChartPaletteStore.getState().setSection('candles', { up: '#abcdef' });
    const id = useThemeStore.getState().saveUserPreset('With charts');
    expect(useThemeStore.getState().userPresets[0].chartPalette?.candles.up).toBe('#abcdef');

    // Change both theme and charts away, then re-apply the preset.
    useThemeStore.getState().setColor('primary', '#000000');
    useChartPaletteStore.getState().setSection('candles', { up: '#111111' });
    useThemeStore.getState().applyUserPreset(id);
    expect(useChartPaletteStore.getState().palette.candles.up).toBe('#abcdef');
  });

  it('captures the ChatBot backdrop with a preset and restores it on apply', async () => {
    const { useThemeStore } = await import('./store');
    const { useBackgroundStore } = await import('@/lib/backgrounds');
    useThemeStore.getState().hydrate();
    useBackgroundStore.getState().setPrefs({
      mode: 'solid', solidFill: 'gradient', solidColor: '#05060f', text: 'MIDNIGHT', textEnabled: true,
    });
    const id = useThemeStore.getState().saveUserPreset('Midnight-ish');
    expect(useThemeStore.getState().userPresets[0].background?.mode).toBe('solid');
    expect(useThemeStore.getState().userPresets[0].background?.text).toBe('MIDNIGHT');

    // Change the backdrop away, then re-apply the preset.
    useBackgroundStore.getState().setPrefs({ mode: 'image', preset: 'eclipse-5' });
    useThemeStore.getState().applyUserPreset(id);
    expect(useBackgroundStore.getState().prefs.mode).toBe('solid');
    expect(useBackgroundStore.getState().prefs.text).toBe('MIDNIGHT');
  });

  it('persists and rehydrates a preset chart palette', async () => {
    const { useThemeStore } = await import('./store');
    const { useChartPaletteStore } = await import('@/lib/chart-palette-store');
    useThemeStore.getState().hydrate();
    useChartPaletteStore.getState().setSection('heatmap', { down: '#abc123' });
    useThemeStore.getState().saveUserPreset('Heat');

    vi.resetModules();
    const again = await import('./store');
    again.useThemeStore.getState().hydrate();
    expect(again.useThemeStore.getState().userPresets[0].chartPalette?.heatmap.down).toBe('#abc123');
  });

  it('captures the Aurora palette with a preset and restores it on apply', async () => {
    const { useThemeStore } = await import('./store');
    const { useAuroraPaletteStore } = await import('@/lib/aurora/store');
    useThemeStore.getState().hydrate();
    useAuroraPaletteStore.getState().setPalette({
      bullish: { core: '#00ff00', edge: '#003300' },
      neutral: { core: '#888888', edge: '#222222' },
      bearish: { core: '#ff0000', edge: '#330000' },
    });
    const id = useThemeStore.getState().saveUserPreset('Green glow');
    expect(useThemeStore.getState().userPresets[0].aurora?.bullish.core).toBe('#00ff00');

    // Change the glow away, then re-apply the preset.
    useAuroraPaletteStore.getState().setPalette({
      bullish: { core: '#0000ff', edge: '#000033' },
      neutral: { core: '#111111', edge: '#000000' },
      bearish: { core: '#ff00ff', edge: '#330033' },
    });
    useThemeStore.getState().applyUserPreset(id);
    expect(useAuroraPaletteStore.getState().palette.bullish.core).toBe('#00ff00');
  });
});

describe('live preview', () => {
  it('previews without persisting and restores on cancel', async () => {
    const { useThemeStore } = await import('./store');
    useThemeStore.getState().hydrate();
    expect(values.has(THEME_KEY)).toBe(false);

    const previewDraft = normalizeTheme({ ...DEFAULT_ECLIPSE_THEME, colors: { ...DEFAULT_ECLIPSE_THEME.colors, primary: '#abc123' } });
    useThemeStore.getState().preview(previewDraft);

    // Preview is held, but the saved theme + storage are untouched.
    expect(useThemeStore.getState().previewTheme?.colors.primary).toBe('#abc123');
    expect(useThemeStore.getState().theme.colors.primary).toBe(DEFAULT_ECLIPSE_THEME.colors.primary);
    expect(values.has(THEME_KEY)).toBe(false);

    useThemeStore.getState().cancelPreview();
    expect(useThemeStore.getState().previewTheme).toBeNull();
    expect(values.has(THEME_KEY)).toBe(false);
  });

  it('commits a preview to the saved theme + storage', async () => {
    const { useThemeStore } = await import('./store');
    useThemeStore.getState().hydrate();
    useThemeStore.getState().preview(normalizeTheme({ ...DEFAULT_ECLIPSE_THEME, colors: { ...DEFAULT_ECLIPSE_THEME.colors, primary: '#abc123' } }));
    useThemeStore.getState().commitPreview();
    expect(useThemeStore.getState().previewTheme).toBeNull();
    expect(useThemeStore.getState().theme.colors.primary).toBe('#abc123');
    expect(useThemeStore.getState().customized).toBe(true);
    expect(values.has(THEME_KEY)).toBe(true);
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
