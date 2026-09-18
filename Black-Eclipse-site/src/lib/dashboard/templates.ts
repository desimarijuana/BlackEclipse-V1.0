// ── Dashboard persona templates ──────────────────────────────────────────────
// Onboarding picks a persona → a starting template. A template is a set of
// CENTRE sections. The left/right side zones are added later by
// `buildMarketViewLayout`, so templates stay purely about the centre.
//
// Specs are WIDGET-ID based (not registry indices): inserting or reordering a
// widget in the registry can no longer silently repoint a template. Unknown ids
// are dropped and a widget never appears twice. The template is ONLY a starting
// point — the user can fully modify it (spec §26, §28).
//
// The gap-free rule: EVERY default placement is pinned to one of `HEIGHTS`, and
// each row is authored so its columns share a height (a short widget is never
// left beside a tall one, and nothing stretches into dead space). Rows are
// therefore mostly 2-up or 4-up with matched heights.
//
// Eight personas with GENUINELY different widgets and a different primary
// visual — not index shuffles of one another:
//   trader    chart + trade tape + movers + live TV
//   trader-pro chart + tradingview + tape + alerts + LARGE live TV + heatmap
//   investor  fund performance + holdings + risk
//   macro     economic chart + rates + commodities + geopolitics
//   crypto    chart + crypto markets + ticker + polymarket
//   forex     chart + FX pairs + drivers + macro
//   quant     heatmap + screener + opportunities + asset chart
//   world     investor-eye map + events + conflict layers

import { composeRows, HEIGHTS, type LayoutRow } from './layout';
import { cloneLayout, normalizeLayout } from '@/lib/workspace/ops';
import type { WorkspaceLayout } from '@/lib/workspace/types';

export interface DashboardTemplate {
  id: string;
  name: string;
  desc: string;
  /** Build the centre layout from a set of known widget ids. */
  build: (widgetIds: string[]) => WorkspaceLayout;
}

/** A band row: widgets one-per-column, each pinned to the same height. */
const band = (widgets: string[], height: number, weights?: number[]): LayoutRow => ({
  zone: 'main',
  cells: widgets.map((widget, i) => ({ widget, weight: weights?.[i], height })),
});

/** A full-width single-widget band (the primary visual). */
const full = (widget: string, height: number): LayoutRow => ({
  zone: 'main',
  cells: [{ widget, weight: 1, height }],
});

function buildFromRows(rows: LayoutRow[], widgetIds: string[]): WorkspaceLayout {
  const sections = composeRows(rows, new Set(widgetIds));
  return normalizeLayout({ version: 1, sections })
    ?? cloneLayout({ version: 1, sections: [] });
}

// Centre rows are capped at TWO widgets. Four skinny columns are what squeezed
// KPI tiles until their titles and numbers truncated — the "looks horrible"
// regression. Two-up (or one full-width) gives every widget room to render its
// full content without crowding.
export const DASHBOARD_TEMPLATES: DashboardTemplate[] = [
  {
    id: 'trader',
    name: 'Trader',
    desc: 'Chart-first day trading: status, a big chart, heatmap, trade tape, live TV and news.',
    build: ids => buildFromRows([
      band(['market-status', 'market-regime'], HEIGHTS.tile),
      full('eclipse-chart', HEIGHTS.chart),
      full('market-heatmap', HEIGHTS.tall),
      band(['trade-tape', 'top-movers'], HEIGHTS.panel),
      band(['what-changed', 'opportunity-scanner'], HEIGHTS.panel),
      full('live-tv', HEIGHTS.live),
      band(['news-feed', 'economic-calendar'], HEIGHTS.panel),
    ], ids),
  },
  {
    id: 'trader-pro',
    name: 'Trader Pro',
    desc: 'The full professional board: chart, trade tape, alerts, heatmap and large live TV.',
    build: ids => buildFromRows([
      band(['market-status', 'top-movers'], HEIGHTS.tile),
      full('eclipse-chart', HEIGHTS.chart),
      full('market-heatmap', HEIGHTS.tall),
      band(['trade-tape', 'active-alerts'], HEIGHTS.panel),
      band(['candle-chart', 'risk-metrics'], HEIGHTS.tall),
      band(['sector-heatmap', 'what-changed'], HEIGHTS.panel),
      full('live-tv', HEIGHTS.live),
    ], ids),
  },
  {
    id: 'investor',
    name: 'Investor',
    desc: 'Portfolio-first: performance vs benchmarks, holdings, allocation and risk.',
    build: ids => buildFromRows([
      band(['market-status', 'portfolio-summary'], HEIGHTS.tile),
      full('fund-performance-chart', HEIGHTS.chart),
      full('holdings', HEIGHTS.tall),
      band(['funds-comparison-chart', 'risk-metrics'], HEIGHTS.panel),
      band(['global-markets', 'market-regime'], HEIGHTS.panel),
      band(['news-feed', 'economic-calendar'], HEIGHTS.panel),
    ], ids),
  },
  {
    id: 'macro',
    name: 'Macro',
    desc: 'Rates, central banks and global flows — economic series, commodities, geopolitics, news.',
    build: ids => buildFromRows([
      band(['market-status', 'market-regime'], HEIGHTS.tile),
      full('economic-chart', HEIGHTS.chart),
      band(['global-markets', 'macro-snapshot'], HEIGHTS.panel),
      band(['market-drivers', 'what-changed'], HEIGHTS.panel),
      band(['commodities', 'economic-calendar'], HEIGHTS.panel),
      band(['geopolitics', 'maritime'], HEIGHTS.tall),
      full('news-feed', HEIGHTS.tall),
    ], ids),
  },
  {
    id: 'crypto',
    name: 'Crypto',
    desc: 'Live crypto markets, a big chart, trade tape, sparklines and prediction markets.',
    build: ids => buildFromRows([
      band(['market-status', 'crypto-markets'], HEIGHTS.tile),
      full('eclipse-chart', HEIGHTS.chart),
      band(['market-regime', 'global-markets'], HEIGHTS.panel),
      band(['trade-tape', 'top-movers'], HEIGHTS.panel),
      band(['sparklines', 'polymarket'], HEIGHTS.panel),
      full('crypto-ticker', HEIGHTS.strip),
      band(['opportunity-scanner', 'news-feed'], HEIGHTS.tall),
    ], ids),
  },
  {
    id: 'forex',
    name: 'Forex',
    desc: 'FX pairs, a big chart, drivers, macro snapshot and the economic calendar.',
    build: ids => buildFromRows([
      band(['market-status', 'forex-pairs'], HEIGHTS.tile),
      full('eclipse-chart', HEIGHTS.chart),
      band(['market-regime', 'global-markets'], HEIGHTS.panel),
      band(['market-drivers', 'what-changed'], HEIGHTS.panel),
      band(['macro-snapshot', 'economic-calendar'], HEIGHTS.panel),
      full('economic-chart', HEIGHTS.tall),
      full('news-feed', HEIGHTS.tall),
    ], ids),
  },
  {
    id: 'quant',
    name: 'Quant',
    desc: 'Screeners, heatmaps, risk and momentum setups for systematic work.',
    build: ids => buildFromRows([
      band(['market-status', 'market-regime'], HEIGHTS.tile),
      full('market-heatmap', HEIGHTS.chart),
      full('stock-screener', HEIGHTS.tall),
      band(['sector-heatmap', 'top-movers'], HEIGHTS.panel),
      band(['opportunity-scanner', 'risk-metrics'], HEIGHTS.panel),
      full('asset-chart', HEIGHTS.chart),
      full('news-feed', HEIGHTS.tall),
    ], ids),
  },
  {
    id: 'world',
    name: 'World',
    desc: 'Geopolitics and world events: the live map, event feed, conflict layers and markets.',
    build: ids => buildFromRows([
      band(['market-status', 'market-regime'], HEIGHTS.tile),
      full('investor-eye-map', HEIGHTS.chart),
      full('investor-eye', HEIGHTS.tall),
      band(['geopolitics', 'maritime'], HEIGHTS.tall),
      band(['global-markets', 'macro-snapshot'], HEIGHTS.panel),
      band(['economic-calendar', 'news-feed'], HEIGHTS.panel),
    ], ids),
  },
];

export function getDashboardTemplate(id: string): DashboardTemplate | undefined {
  return DASHBOARD_TEMPLATES.find(t => t.id === id);
}
