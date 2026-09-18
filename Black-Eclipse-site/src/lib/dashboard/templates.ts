// ── Dashboard persona templates ──────────────────────────────────────────────
// Onboarding picks a persona → a starting template. A template is a set of
// CENTRE sections (band grammar: hero → primary → analysis → context → live).
// The left/right side zones are added later by `buildMarketViewLayout`, so
// templates stay purely about the centre.
//
// Specs are WIDGET-ID based (not registry indices): inserting or reordering a
// widget in the registry can no longer silently repoint a template. Unknown ids
// are dropped and a widget never appears twice. The template is ONLY a starting
// point — the user can fully modify it (spec §26, §28).
//
// Design intent (why it looks calmer than the old dump):
//   • A short 4-up HERO of small status/KPI tiles — quick glance, low height.
//   • ONE full-width PRIMARY visual (chart/heatmap) with a pinned height, so it
//     is a real centrepiece rather than a stretched gap.
//   • Analysis/context are TWO-UP (not four tiny columns), giving each panel
//     room to breathe. Pinned heights keep rows from stretching into dead space.
//   • A full-width LIVE strip last.

import { composeRows, type LayoutRow } from './layout';
import { cloneLayout, normalizeLayout } from '@/lib/workspace/ops';
import type { WorkspaceLayout } from '@/lib/workspace/types';

export interface DashboardTemplate {
  id: string;
  name: string;
  desc: string;
  /** Build the centre layout from a set of known widget ids. */
  build: (widgetIds: string[]) => WorkspaceLayout;
}

/** Band heights (px). Pinned so big visuals don't stretch into empty space. */
const H = {
  hero: 150,
  primary: 440,
  panel: 320,
  context: 300,
  live: 380,
} as const;

/** A band row: widgets one-per-column, with optional per-cell weights/heights. */
const row = (
  widgets: string[],
  opts?: { weights?: number[]; heights?: Array<number | null> },
): LayoutRow => ({
  zone: 'main',
  cells: widgets.map((widget, i) => ({
    widget,
    weight: opts?.weights?.[i],
    height: opts?.heights?.[i],
  })),
});

/** A band where every cell shares one height. */
const band = (widgets: string[], height: number, weights?: number[]): LayoutRow =>
  row(widgets, { weights, heights: widgets.map(() => height) });

function buildFromRows(rows: LayoutRow[], widgetIds: string[]): WorkspaceLayout {
  const sections = composeRows(rows, new Set(widgetIds));
  return normalizeLayout({ version: 1, sections })
    ?? cloneLayout({ version: 1, sections: [] });
}

export const DASHBOARD_TEMPLATES: DashboardTemplate[] = [
  {
    id: 'trader',
    name: 'Trader',
    desc: 'Chart-forward: live status and P&L, a large chart, movers, then news.',
    build: ids => buildFromRows([
      band(['market-status', 'market-regime', 'portfolio-summary', 'performance'], H.hero),
      band(['eclipse-chart'], H.primary),
      band(['top-movers', 'sector-heatmap'], H.panel),
      band(['what-changed', 'opportunity-scanner'], H.panel),
      band(['news-feed', 'economic-calendar'], H.context),
      band(['live-tv'], H.live),
    ], ids),
  },
  {
    id: 'investor',
    name: 'Investor',
    desc: 'Portfolio-first: performance vs benchmarks, holdings and risk.',
    build: ids => buildFromRows([
      band(['market-status', 'portfolio-summary', 'performance', 'risk-metrics'], H.hero),
      band(['fund-performance-chart'], H.primary),
      band(['holdings', 'funds-comparison-chart'], H.panel),
      band(['global-markets', 'market-regime'], H.panel),
      band(['news-feed', 'economic-calendar'], H.context),
    ], ids),
  },
  {
    id: 'macro',
    name: 'Macro',
    desc: 'Rates, central banks and global flows — series, commodities, geopolitics.',
    build: ids => buildFromRows([
      band(['market-status', 'market-regime', 'global-markets', 'macro-snapshot'], H.hero),
      band(['economic-chart'], H.primary),
      band(['market-drivers', 'what-changed'], H.panel),
      band(['commodities', 'economic-calendar'], H.panel),
      band(['geopolitics', 'maritime'], H.context),
      band(['news-feed'], H.context),
    ], ids),
  },
  {
    id: 'crypto',
    name: 'Crypto',
    desc: 'Live crypto markets, a large chart, trade tape and sentiment.',
    build: ids => buildFromRows([
      band(['market-status', 'market-regime', 'crypto-markets', 'global-markets'], H.hero),
      band(['eclipse-chart'], H.primary),
      band(['top-movers', 'trade-tape'], H.panel),
      band(['sparklines', 'polymarket'], H.panel),
      band(['crypto-ticker'], H.context),
      band(['opportunity-scanner', 'news-feed'], H.context),
    ], ids),
  },
  {
    id: 'forex',
    name: 'Forex',
    desc: 'FX pairs, a large chart, drivers and the economic calendar.',
    build: ids => buildFromRows([
      band(['market-status', 'market-regime', 'forex-pairs', 'global-markets'], H.hero),
      band(['eclipse-chart'], H.primary),
      band(['market-drivers', 'what-changed'], H.panel),
      band(['macro-snapshot', 'economic-calendar'], H.panel),
      band(['economic-chart'], H.primary),
      band(['news-feed'], H.context),
    ], ids),
  },
  {
    id: 'quant',
    name: 'Quant',
    desc: 'Screeners, heatmaps, risk and momentum setups for systematic work.',
    build: ids => buildFromRows([
      band(['market-status', 'market-regime', 'top-movers', 'performance'], H.hero),
      band(['market-heatmap'], H.primary),
      band(['stock-screener', 'sector-heatmap'], H.panel),
      band(['opportunity-scanner', 'risk-metrics'], H.panel),
      band(['asset-chart'], H.primary),
      band(['news-feed'], H.context),
    ], ids),
  },
];

export function getDashboardTemplate(id: string): DashboardTemplate | undefined {
  return DASHBOARD_TEMPLATES.find(t => t.id === id);
}
