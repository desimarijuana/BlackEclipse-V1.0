// ── Theme → chart palette bridge ─────────────────────────────────────────────
// Keeps native Eclipse charts (candles, line primary, heatmap) aligned with the
// centralized theme's market semantics without duplicating color state. The
// categorical series palette is intentionally left alone so a user's multi-series
// choices (Settings › Charts) survive theme edits.
//
// Called only on explicit user customization, never on hydration, so a
// separately-saved chart palette is not clobbered on page load.

'use client';

import {
  DEFAULT_CHART_PALETTE,
  normalizeChartPalette,
  type ChartPalette,
} from '@/lib/chart-palette';
import { useChartPaletteStore } from '@/lib/chart-palette-store';
import type { EclipseTheme } from './tokens';

/**
 * The chart palette a theme implies: market colors follow the theme, while the
 * categorical series palette is preserved from `base` (default: shipped) so
 * multi-series customizations are not silently reset by a theme edit.
 */
export function chartPaletteFromTheme(
  theme: EclipseTheme,
  base: ChartPalette = DEFAULT_CHART_PALETTE,
): ChartPalette {
  const { colors } = theme;
  return normalizeChartPalette({
    candles: { up: colors.bullish, down: colors.bearish, neutral: base.candles.neutral },
    lines: { ...base.lines, primary: colors.primary },
    heatmap: { ...base.heatmap, up: colors.bullish, down: colors.bearish },
  });
}

/** Persist the chart palette a theme implies (explicit user action). */
export function syncChartPaletteFromTheme(theme: EclipseTheme): void {
  const store = useChartPaletteStore.getState();
  store.setPalette(chartPaletteFromTheme(theme, store.palette));
}

/**
 * Show the chart palette a draft theme implies WITHOUT persisting it — used by
 * the live / full-screen theme preview so charts and market heatmaps recolor as
 * the user edits, then revert on discard.
 */
export function previewChartPaletteFromTheme(theme: EclipseTheme): void {
  const store = useChartPaletteStore.getState();
  store.setPreview(chartPaletteFromTheme(theme, store.palette));
}

/** Drop the preview overlay, restoring the saved chart palette. */
export function clearChartPalettePreview(): void {
  useChartPaletteStore.getState().setPreview(null);
}
