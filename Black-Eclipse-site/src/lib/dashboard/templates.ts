// ── Dashboard persona templates ──────────────────────────────────────────────
// Onboarding picks a persona → a starting template. A template is a set of
// CENTRE bands. The left/right side tracks are added later by
// `buildMarketViewLayout`, so templates stay purely about the centre.
//
// Specs are WIDGET-ID based (not registry indices): inserting or reordering a
// widget in the registry can no longer silently repoint a template. Unknown ids
// are dropped and a widget never appears twice. The template is ONLY a starting
// point — the user can fully modify it.
//
// Track-board grammar: each persona authors several bands. A band is `full`
// (one track), `split` (two tracks) or `grid` (N tracks). Cell objects can
// override a widget's intrinsic frame height so a persona expresses deliberate
// asymmetry instead of a uniform grid. The packer then balances each band.
//
// Twelve personas, each a DIFFERENT SHAPE (not index shuffles):
//   tape-reader  full chart → wide tape → two-up context → TV
//   desk         dense 4-track dashboard, TV + heatmap flank the chart
//   allocator    portfolio: performance hero → holdings → risk grid
//   rates-desk   macro: economic chart + rates + calendar, geopolitics
//   chain-desk   crypto: crypto hero row → chart → venue grid → prediction
//   fx-desk      forex: FX pairs hero → chart → drivers/macro two-up
//   screener     quant: heatmap + screener full, momentum grid
//   map-room     world: map hero → event feed → conflict/markets grid
//   newsroom     text-forward: news + calendar lead, charts secondary

import { composeBoard, type BoardCell, type BoardSpec } from './layout';
import { cloneLayout, normalizeLayout } from '@/lib/workspace/ops';
import type { WorkspaceLayout } from '@/lib/workspace/types';

export interface DashboardTemplate {
  id: string;
  name: string;
  desc: string;
  /** Build the centre layout from a set of known widget ids. */
  build: (widgetIds: string[]) => WorkspaceLayout;
}

/** One full-width band. */
const full = (...cells: BoardCell[]): BoardSpec => ({ zone: 'main', tracks: 1, cells });

/** A two-up band (deliberately asymmetric — one tall left, one short right). */
const split = (left: BoardCell, right: BoardCell): BoardSpec => ({ zone: 'main', tracks: 2, cells: [left, right] });

/** A multi-track band balanced by the packer. */
const grid = (tracks: number, ...cells: BoardCell[]): BoardSpec => ({ zone: 'main', tracks, cells });

function buildFromSpecs(specs: BoardSpec[], widgetIds: string[]): WorkspaceLayout {
  const sections = composeBoard(specs, new Set(widgetIds));
  return normalizeLayout({ version: 2, sections })
    ?? cloneLayout({ version: 2, sections: [] });
}

export const DASHBOARD_TEMPLATES: DashboardTemplate[] = [
  {
    id: 'tape-reader',
    name: 'Tape Reader',
    desc: 'Chart-first day trading with a wide trade tape and live TV below.',
    build: ids => buildFromSpecs([
      full('eclipse-chart'),
      full('trade-tape'),
      split({ id: 'market-status', min: 170 }, { id: 'top-movers', min: 300 }),
      split({ id: 'what-changed', min: 300 }, { id: 'opportunity-scanner', min: 300 }),
      full('live-tv'),
      split({ id: 'news-feed', h: 380, frame: false }, { id: 'economic-calendar', h: 340, frame: false }),
    ], ids),
  },
  {
    id: 'desk',
    name: 'The Desk',
    desc: 'Dense professional board — chart, heatmap and TV share the top row.',
    build: ids => buildFromSpecs([
      grid(3,
        { id: 'eclipse-chart', h: 440 },
        { id: 'market-heatmap', h: 440 },
        { id: 'market-status', min: 170 },
      ),
      grid(4,
        { id: 'top-movers', min: 280 },
        { id: 'trade-tape', h: 320, frame: false },
        { id: 'active-alerts', h: 300, frame: false },
        { id: 'risk-metrics', min: 220 },
      ),
      full('live-tv'),
      grid(3,
        { id: 'sector-heatmap', min: 280 },
        { id: 'what-changed', min: 280 },
        { id: 'market-drivers', min: 280 },
      ),
    ], ids),
  },
  {
    id: 'allocator',
    name: 'The Allocator',
    desc: 'Portfolio-first: performance curve, holdings, allocation and risk.',
    build: ids => buildFromSpecs([
      full({ id: 'fund-performance-chart', h: 440 }),
      split({ id: 'portfolio-summary', min: 300 }, { id: 'risk-metrics', min: 300 }),
      full({ id: 'holdings', h: 380, frame: false }),
      grid(3,
        { id: 'funds-comparison-chart', h: 360 },
        { id: 'market-regime', min: 280 },
        { id: 'global-markets', min: 300 },
      ),
      split({ id: 'news-feed', h: 380, frame: false }, { id: 'economic-calendar', h: 340, frame: false }),
    ], ids),
  },
  {
    id: 'rates-desk',
    name: 'Rates Desk',
    desc: 'Macro plumbing: economic series, rates, commodities and geopolitics.',
    build: ids => buildFromSpecs([
      full('economic-chart'),
      grid(3,
        { id: 'macro-snapshot', min: 280 },
        { id: 'market-regime', min: 280 },
        { id: 'market-status', min: 170 },
      ),
      grid(4,
        { id: 'global-markets', min: 300 },
        { id: 'commodities', min: 280 },
        { id: 'market-drivers', min: 280 },
        { id: 'economic-calendar', h: 340, frame: false },
      ),
      split({ id: 'geopolitics', h: 380, frame: false }, { id: 'maritime', h: 380, frame: false }),
      full({ id: 'news-feed', h: 380, frame: false }),
    ], ids),
  },
  {
    id: 'chain-desk',
    name: 'Chain Desk',
    desc: 'Crypto venue board: markets, big chart, venue tiles and prediction markets.',
    build: ids => buildFromSpecs([
      grid(3,
        { id: 'crypto-markets', min: 300 },
        { id: 'market-status', min: 170 },
        { id: 'market-regime', min: 300 },
      ),
      full('eclipse-chart'),
      grid(4,
        { id: 'trade-tape', h: 320, frame: false },
        { id: 'top-movers', min: 280 },
        { id: 'sparklines', min: 200 },
        { id: 'polymarket', min: 300 },
      ),
      full('crypto-ticker'),
      split({ id: 'opportunity-scanner', min: 320 }, { id: 'news-feed', h: 380, frame: false }),
    ], ids),
  },
  {
    id: 'fx-desk',
    name: 'FX Desk',
    desc: 'Currency board: FX pairs hero, a big chart, drivers and rates.',
    build: ids => buildFromSpecs([
      split({ id: 'forex-pairs', min: 340 }, { id: 'market-status', min: 170 }),
      full('eclipse-chart'),
      grid(3,
        { id: 'market-drivers', min: 300 },
        { id: 'what-changed', min: 300 },
        { id: 'macro-snapshot', min: 300 },
      ),
      split({ id: 'global-markets', min: 300 }, { id: 'economic-calendar', h: 340, frame: false }),
      full({ id: 'economic-chart', h: 380 }),
      full({ id: 'news-feed', h: 360, frame: false }),
    ], ids),
  },
  {
    id: 'screener',
    name: 'The Screener',
    desc: 'Systematic workbench: heatmap + screener, momentum and setup grids.',
    build: ids => buildFromSpecs([
      grid(2,
        { id: 'market-heatmap', h: 460 },
        { id: 'market-status', min: 170 },
      ),
      full({ id: 'stock-screener', h: 440, frame: false }),
      grid(3,
        { id: 'market-regime', min: 300 },
        { id: 'sector-heatmap', min: 300 },
        { id: 'top-movers', min: 300 },
      ),
      split({ id: 'opportunity-scanner', min: 340 }, { id: 'risk-metrics', min: 260 }),
      full('asset-chart'),
      full({ id: 'news-feed', h: 360, frame: false }),
    ], ids),
  },
  {
    id: 'map-room',
    name: 'Map Room',
    desc: 'Geopolitics first: the world map, live event feed and conflict layers.',
    build: ids => buildFromSpecs([
      full('investor-eye-map'),
      grid(2,
        { id: 'investor-eye', h: 420, frame: false },
        { id: 'market-status', min: 170 },
      ),
      split({ id: 'geopolitics', h: 400, frame: false }, { id: 'maritime', h: 400, frame: false }),
      grid(3,
        { id: 'global-markets', min: 300 },
        { id: 'macro-snapshot', min: 300 },
        { id: 'market-regime', min: 280 },
      ),
      full({ id: 'news-feed', h: 380, frame: false }),
    ], ids),
  },
  {
    id: 'newsroom',
    name: 'Newsroom',
    desc: 'Text-forward: headlines and the economic calendar lead, charts second.',
    build: ids => buildFromSpecs([
      grid(2,
        { id: 'news-feed', h: 440, frame: false },
        { id: 'economic-calendar', h: 440, frame: false },
      ),
      full('eclipse-chart'),
      grid(3,
        { id: 'global-markets', min: 300 },
        { id: 'market-drivers', min: 300 },
        { id: 'what-changed', min: 300 },
      ),
      split({ id: 'market-status', min: 170 }, { id: 'market-regime', min: 280 }),
      full({ id: 'live-tv', h: 460 }),
    ], ids),
  },
  {
    id: 'risk-desk',
    name: 'Risk Desk',
    desc: 'Downside-first: regime, breadth and risk metrics above the chart.',
    build: ids => buildFromSpecs([
      grid(3,
        { id: 'market-regime', min: 300 },
        { id: 'risk-metrics', min: 240 },
        { id: 'market-status', min: 170 },
      ),
      split({ id: 'eclipse-chart', h: 460 }, { id: 'market-heatmap', h: 460 }),
      grid(3,
        { id: 'active-alerts', h: 300, frame: false },
        { id: 'market-drivers', min: 300 },
        { id: 'sector-heatmap', min: 300 },
      ),
      full({ id: 'news-feed', h: 380, frame: false }),
    ], ids),
  },
  {
    id: 'trader-pro',
    name: 'Trader Pro',
    desc: 'Dual charts, candle detail, tape and alerts — the full trading cockpit.',
    build: ids => buildFromSpecs([
      grid(2,
        { id: 'eclipse-chart', h: 460 },
        { id: 'tradingview-chart', h: 460 },
      ),
      grid(3,
        { id: 'candle-chart', h: 440 },
        { id: 'trade-tape', h: 320, frame: false },
        { id: 'top-movers', min: 300 },
      ),
      grid(4,
        { id: 'active-alerts', h: 300, frame: false },
        { id: 'risk-metrics', min: 240 },
        { id: 'market-status', min: 170 },
        { id: 'what-changed', min: 300 },
      ),
      full('live-tv'),
    ], ids),
  },
  {
    id: 'research',
    name: 'The Research Desk',
    desc: 'Charts plus the full news and research surface: categories, calendar, agent work.',
    build: ids => buildFromSpecs([
      grid(2,
        { id: 'eclipse-chart', h: 420 },
        { id: 'news-category', h: 420, frame: false },
      ),
      grid(3,
        { id: 'recent-research', h: 300, frame: false },
        { id: 'agent-activity', h: 300, frame: false },
        { id: 'ai-insights', h: 300, frame: false },
      ),
      split({ id: 'news-feed', h: 400, frame: false }, { id: 'economic-calendar', h: 400, frame: false }),
      grid(3,
        { id: 'global-markets', min: 300 },
        { id: 'market-drivers', min: 300 },
        { id: 'market-heatmap', h: 440 },
      ),
    ], ids),
  },
];

/**
 * Legacy persona ids → current ids. The nine personas were renamed when the
 * track-board grammar landed, but stored dashboards and market layouts still
 * carry the OLD ids. Without this map `getDashboardTemplate('trader')` returns
 * undefined, so the centre of every existing dashboard renders EMPTY (only the
 * side rails appear). Resolving aliases keeps those arrangements working.
 */
export const LEGACY_TEMPLATE_IDS: Record<string, string> = {
  trader: 'tape-reader',
  investor: 'allocator',
  macro: 'rates-desk',
  crypto: 'chain-desk',
  forex: 'fx-desk',
  quant: 'screener',
  world: 'map-room',
};

/** Resolve a possibly-legacy template id to a current persona id. */
export function resolveTemplateId(id: string | undefined | null): string {
  if (!id) return DASHBOARD_TEMPLATES[0].id;
  if (DASHBOARD_TEMPLATES.some(t => t.id === id)) return id;
  return LEGACY_TEMPLATE_IDS[id] ?? DASHBOARD_TEMPLATES[0].id;
}

export function getDashboardTemplate(id: string): DashboardTemplate | undefined {
  const resolved = resolveTemplateId(id);
  return DASHBOARD_TEMPLATES.find(t => t.id === resolved);
}

