// ── Dashboard persona templates ──────────────────────────────────────────────
// Onboarding picks a persona → a starting template. A template is a set of
// CENTRE sections (band grammar: hero → primary → analysis → intelligence →
// context → live). The left/right side zones are added later by
// `buildMarketViewLayout`, so templates stay purely about the centre.
//
// Specs are WIDGET-ID based (not registry indices): inserting or reordering a
// widget in the registry can no longer silently repoint a template. Unknown ids
// are dropped and a widget never appears twice. The template is ONLY a starting
// point — the user can fully modify it (spec §26, §28).

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

/** A centre band: one row of widgets, placed one-per-column (≤4). */
const row = (widgets: string[], weights?: number[]): LayoutRow => ({
  zone: 'main',
  cells: widgets.map((widget, i) => ({ widget, weight: weights?.[i] })),
});

function buildFromRows(rows: LayoutRow[], widgetIds: string[]): WorkspaceLayout {
  const sections = composeRows(rows, new Set(widgetIds));
  return normalizeLayout({ version: 1, sections })
    ?? cloneLayout({ version: 1, sections: [] });
}

export const DASHBOARD_TEMPLATES: DashboardTemplate[] = [
  {
    id: 'trader',
    name: 'Trader',
    desc: 'Chart-forward: live status, regime and P&L, a primary chart, movers and news.',
    build: ids => buildFromRows([
      row(['market-status', 'market-regime', 'portfolio-summary', 'performance']),
      row(['eclipse-chart']),
      row(['top-movers', 'sector-heatmap', 'market-drivers']),
      row(['what-changed', 'opportunity-scanner']),
      row(['news-feed', 'economic-calendar']),
      row(['live-tv']),
    ], ids),
  },
  {
    id: 'investor',
    name: 'Investor',
    desc: 'Portfolio-first: performance vs benchmarks, holdings, risk and global markets.',
    build: ids => buildFromRows([
      row(['market-status', 'portfolio-summary', 'performance', 'risk-metrics']),
      row(['fund-performance-chart']),
      row(['holdings', 'funds-comparison-chart', 'global-markets']),
      row(['news-feed', 'economic-calendar']),
      row(['market-regime']),
    ], ids),
  },
  {
    id: 'macro',
    name: 'Macro',
    desc: 'Rates, central banks and global flows — economic series, commodities, geopolitics.',
    build: ids => buildFromRows([
      row(['market-status', 'market-regime', 'global-markets', 'macro-snapshot']),
      row(['economic-chart']),
      row(['market-drivers', 'what-changed', 'commodities']),
      row(['economic-calendar', 'news-feed']),
      row(['geopolitics', 'maritime']),
    ], ids),
  },
  {
    id: 'crypto',
    name: 'Crypto',
    desc: 'Live crypto markets, a primary chart, trade tape, sparklines and sentiment.',
    build: ids => buildFromRows([
      row(['market-status', 'market-regime', 'crypto-markets', 'global-markets']),
      row(['eclipse-chart']),
      row(['top-movers', 'trade-tape', 'sparklines']),
      row(['crypto-ticker', 'polymarket']),
      row(['opportunity-scanner', 'news-feed']),
    ], ids),
  },
  {
    id: 'forex',
    name: 'Forex',
    desc: 'FX pairs, a primary chart, drivers, macro snapshot and the economic calendar.',
    build: ids => buildFromRows([
      row(['market-status', 'market-regime', 'forex-pairs', 'global-markets']),
      row(['eclipse-chart']),
      row(['market-drivers', 'what-changed', 'macro-snapshot']),
      row(['economic-calendar', 'news-feed']),
      row(['economic-chart']),
    ], ids),
  },
  {
    id: 'quant',
    name: 'Quant',
    desc: 'Screeners, heatmaps, risk and momentum setups for systematic work.',
    build: ids => buildFromRows([
      row(['market-status', 'market-regime', 'top-movers', 'performance']),
      row(['market-heatmap']),
      row(['stock-screener', 'sector-heatmap', 'opportunity-scanner']),
      row(['asset-chart', 'risk-metrics']),
      row(['news-feed']),
    ], ids),
  },
];

export function getDashboardTemplate(id: string): DashboardTemplate | undefined {
  return DASHBOARD_TEMPLATES.find(t => t.id === id);
}
