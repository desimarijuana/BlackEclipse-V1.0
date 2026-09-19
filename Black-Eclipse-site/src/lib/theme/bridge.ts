// ── Theme → chart palette bridge ─────────────────────────────────────────────
// Keeps native Eclipse charts (candles, line primary, heatmap) aligned with the
// centralized theme's market semantics without duplicating color state. The
// categorical series palette is intentionally left alone so a user's multi-series
// choices (Settings › Charts) survive theme edits.
//
// Called only on explicit user customization, never on hydration, so a
// separately-saved chart palette is not clobbered on page load.

'use client';

import { useChartPaletteStore } from '@/lib/chart-palette-store';
import type { EclipseTheme } from './tokens';

export function syncChartPaletteFromTheme(theme: EclipseTheme): void {
  const { colors } = theme;
  const store = useChartPaletteStore.getState();
  store.setPalette({
    candles: { up: colors.bullish, down: colors.bearish, neutral: '#94a3b8' },
    lines: { ...store.palette.lines, primary: colors.primary },
    heatmap: { ...store.palette.heatmap, up: colors.bullish, down: colors.bearish },
  });
}
