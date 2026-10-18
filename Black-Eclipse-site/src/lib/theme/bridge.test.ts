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
  it('decouples charts from the theme — a theme edit never recolours charts', async () => {
    const { chartPaletteFromTheme } = await import('./bridge');
    const theme = normalizeTheme({
      ...DEFAULT_ECLIPSE_THEME,
      colors: { primary: '#00d0ff', bullish: '#00ff41', bearish: '#ff3b3b' },
    });
    const palette = chartPaletteFromTheme(theme);
    // Neither the accent nor the market colors reach the chart palette.
    expect(palette.candles.up).toBe(DEFAULT_CHART_PALETTE.candles.up);
    expect(palette.candles.down).toBe(DEFAULT_CHART_PALETTE.candles.down);
    expect(palette.lines.primary).toBe(DEFAULT_CHART_PALETTE.lines.primary);
    expect(palette.heatmap.up).toBe(DEFAULT_CHART_PALETTE.heatmap.up);
  });

  it('preserves the categorical series palette from the base', async () => {
    const { chartPaletteFromTheme } = await import('./bridge');
    const base = { ...DEFAULT_CHART_PALETTE, lines: { ...DEFAULT_CHART_PALETTE.lines, series: ['#111111', '#222222', '#333333', '#444444', '#555555', '#666666'] } };
    const palette = chartPaletteFromTheme(DEFAULT_ECLIPSE_THEME, base);
    expect(palette.lines.series).toEqual(base.lines.series);
  });
});

describe('preview + commit bridge', () => {
  it('leaves chart colours untouched on preview and never persists', async () => {
    const { previewChartPaletteFromTheme, clearChartPalettePreview } = await import('./bridge');
    const { getChartPalette } = await import('@/lib/chart-palette-store');
    const theme = normalizeTheme({ ...DEFAULT_ECLIPSE_THEME, colors: { ...DEFAULT_ECLIPSE_THEME.colors, bullish: '#123456' } });
    previewChartPaletteFromTheme(theme);
    expect(getChartPalette().candles.up).toBe(DEFAULT_CHART_PALETTE.candles.up);
    expect(storage.setItem).not.toHaveBeenCalled();
    clearChartPalettePreview();
    expect(getChartPalette().candles.up).toBe(DEFAULT_CHART_PALETTE.candles.up);
  });

  it('persists the unchanged palette when explicitly synced', async () => {
    const { syncChartPaletteFromTheme } = await import('./bridge');
    const { useChartPaletteStore } = await import('@/lib/chart-palette-store');
    const theme = normalizeTheme({ ...DEFAULT_ECLIPSE_THEME, colors: { ...DEFAULT_ECLIPSE_THEME.colors, bearish: '#abcdef' } });
    syncChartPaletteFromTheme(theme);
    expect(useChartPaletteStore.getState().palette.candles.down).toBe(DEFAULT_CHART_PALETTE.candles.down);
    expect(storage.setItem).toHaveBeenCalled();
  });
});
