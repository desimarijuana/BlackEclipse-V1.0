import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { DEFAULT_CHART_PALETTE } from '@/lib/chart-palette';
import { DEFAULT_ECLIPSE_THEME, normalizeTheme } from '@/lib/theme/tokens';

const values = new Map<string, string>();
const storage = {
  getItem: vi.fn((name: string) => values.get(name) ?? null),
  setItem: vi.fn((name: string, value: string) => { values.set(name, value); }),
};

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  values.clear();
  vi.stubGlobal('window', {
    localStorage: storage,
    addEventListener: vi.fn(),
  });
});

afterEach(() => vi.unstubAllGlobals());

describe('chartPaletteFromTheme', () => {
  it('maps market colors onto candles, line primary and heatmap ends', async () => {
    const { chartPaletteFromTheme } = await import('./bridge');
    const theme = normalizeTheme({
      ...DEFAULT_ECLIPSE_THEME,
      colors: { primary: '#00d0ff', bullish: '#00ff41', bearish: '#ff3b3b' },
    });
    const palette = chartPaletteFromTheme(theme);
    expect(palette.candles.up).toBe('#00ff41');
    expect(palette.candles.down).toBe('#ff3b3b');
    expect(palette.lines.primary).toBe('#00d0ff');
    expect(palette.heatmap.up).toBe('#00ff41');
    expect(palette.heatmap.down).toBe('#ff3b3b');
  });

  it('preserves the categorical series palette from the base', async () => {
    const { chartPaletteFromTheme } = await import('./bridge');
    const base = { ...DEFAULT_CHART_PALETTE, lines: { ...DEFAULT_CHART_PALETTE.lines, series: ['#111111', '#222222', '#333333', '#444444', '#555555', '#666666'] } };
    const palette = chartPaletteFromTheme(DEFAULT_ECLIPSE_THEME, base);
    expect(palette.lines.series).toEqual(base.lines.series);
  });
});

describe('preview + commit bridge', () => {
  it('previews onto the effective palette without persisting, then clears', async () => {
    const { previewChartPaletteFromTheme, clearChartPalettePreview } = await import('./bridge');
    const { getChartPalette } = await import('@/lib/chart-palette-store');
    const theme = normalizeTheme({ ...DEFAULT_ECLIPSE_THEME, colors: { ...DEFAULT_ECLIPSE_THEME.colors, bullish: '#123456' } });
    previewChartPaletteFromTheme(theme);
    expect(getChartPalette().candles.up).toBe('#123456');
    expect(storage.setItem).not.toHaveBeenCalled();
    clearChartPalettePreview();
    expect(getChartPalette().candles.up).toBe(DEFAULT_CHART_PALETTE.candles.up);
  });

  it('persists when explicitly synced', async () => {
    const { syncChartPaletteFromTheme } = await import('./bridge');
    const { useChartPaletteStore } = await import('@/lib/chart-palette-store');
    const theme = normalizeTheme({ ...DEFAULT_ECLIPSE_THEME, colors: { ...DEFAULT_ECLIPSE_THEME.colors, bearish: '#abcdef' } });
    syncChartPaletteFromTheme(theme);
    expect(useChartPaletteStore.getState().palette.candles.down).toBe('#abcdef');
    expect(storage.setItem).toHaveBeenCalled();
  });
});
