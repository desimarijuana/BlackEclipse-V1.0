// ── Theme → chart palette bridge ─────────────────────────────────────────────
// Charts are DECOUPLED from the theme. A user's chart colours come from the
// shipped green/red default (or their explicit Settings › Charts edits, or a
// preset that carries its own `chartPalette`), and an ambient theme edit never
// recolours a chart. These helpers are the single seam the customization flow
// calls; they normalise the palette and deliberately ignore the theme's colors,
// so charts stay green/red unless the user asked for a change.
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
 * The chart palette a theme implies — which is the palette already in effect.
 * The theme is intentionally ignored: charts keep their shipped green/red (or
 * the user's own) colours when a theme is applied or previewed.
 */
export function chartPaletteFromTheme(
  _theme: EclipseTheme,
  base: ChartPalette = DEFAULT_CHART_PALETTE,
): ChartPalette {
  return normalizeChartPalette(base);
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
