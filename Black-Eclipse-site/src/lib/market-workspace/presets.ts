// ── Market Workspace — presets ───────────────────────────────────────────────
// Curated starting layouts. A preset is ONLY a starting point — every panel,
// symbol, timeframe and size remains fully editable afterwards.

import { defaultChartState, type Timeframe, type ChartType } from '@/lib/chart/types';
import { newPanelId, type MarketPanel, type MarketPanelType, type MarketWorkspaceLayout, type PanelRect } from './types';
import { cloneLayout, normalizePanels } from './ops';
import { DEFAULT_LINK } from './types';
import type { Draft } from 'immer';

export interface WorkspacePreset {
  id: string;
  name: string;
  desc: string;
  build: () => MarketWorkspaceLayout;
}

interface PanelSpec {
  type: MarketPanelType;
  rect: PanelRect;
  symbol?: string;
  market?: string;
  timeframe?: Timeframe;
  chartType?: ChartType;
  aiOpen?: boolean;
  config?: Record<string, unknown>;
}

function chart(symbol: string, market: string, timeframe: Timeframe = '1D', chartType: ChartType = 'candlestick'): Partial<PanelSpec> {
  return { symbol, market, timeframe, chartType };
}

function build(specs: PanelSpec[], layoutId = 'custom', rows = 4): MarketWorkspaceLayout {
  const panels: MarketPanel[] = specs.map((spec) => {
    const panel: MarketPanel = {
      id: newPanelId(spec.type),
      type: spec.type,
      rect: { ...spec.rect },
    };
    if (spec.type === 'chart') {
      panel.chart = defaultChartState({
        symbol: spec.symbol ?? 'AAPL',
        market: spec.market ?? 'US',
        timeframe: spec.timeframe ?? '1D',
        chartType: spec.chartType ?? 'candlestick',
      });
      panel.link = { ...DEFAULT_LINK };
    }
    if (spec.symbol) panel.symbol = spec.symbol;
    if (spec.market) panel.market = spec.market;
    if (spec.aiOpen) panel.aiOpen = true;
    if (spec.config) panel.config = spec.config;
    return panel;
  });
  const layout: MarketWorkspaceLayout = { version: 1, layoutId, rows, panels };
  normalizePanels(layout as Draft<MarketWorkspaceLayout>);
  return layout;
}

export const WORKSPACE_PRESETS: WorkspacePreset[] = [
  {
    id: 'trading',
    name: 'Trading',
    desc: 'Six charts, watchlist and live AI analysis — the dense intraday terminal.',
    build: () => build([
      { type: 'chart', rect: { col: 0, row: 0, colSpan: 4, rowSpan: 2 }, ...chart('AAPL', 'US', '15m') },
      { type: 'chart', rect: { col: 4, row: 0, colSpan: 4, rowSpan: 2 }, ...chart('MSFT', 'US', '15m') },
      { type: 'chart', rect: { col: 8, row: 0, colSpan: 4, rowSpan: 2 }, ...chart('NVDA', 'US', '15m') },
      { type: 'chart', rect: { col: 0, row: 2, colSpan: 4, rowSpan: 2 }, ...chart('TSLA', 'US', '1H') },
      { type: 'chart', rect: { col: 4, row: 2, colSpan: 4, rowSpan: 2 }, ...chart('AMZN', 'US', '1H') },
      { type: 'watchlist', rect: { col: 8, row: 2, colSpan: 4, rowSpan: 2 } },
    ], 'custom', 4),
  },
  {
    id: 'research',
    name: 'Investment Research',
    desc: 'One large chart beside fundamentals, AI analysis and news.',
    build: () => build([
      { type: 'chart', rect: { col: 0, row: 0, colSpan: 7, rowSpan: 4 }, ...chart('AAPL', 'US', '1D'), aiOpen: true },
      { type: 'fundamentals', rect: { col: 7, row: 0, colSpan: 5, rowSpan: 2 } },
      { type: 'ai-analysis', rect: { col: 7, row: 2, colSpan: 5, rowSpan: 1 } },
      { type: 'news', rect: { col: 7, row: 3, colSpan: 5, rowSpan: 1 } },
    ], 'custom', 4),
  },
  {
    id: 'portfolio',
    name: 'Portfolio Monitoring',
    desc: 'Portfolio, watchlist and charts for the positions you hold.',
    build: () => build([
      { type: 'portfolio', rect: { col: 0, row: 0, colSpan: 5, rowSpan: 2 } },
      { type: 'watchlist', rect: { col: 5, row: 0, colSpan: 3, rowSpan: 2 } },
      { type: 'market-overview', rect: { col: 8, row: 0, colSpan: 4, rowSpan: 2 } },
      { type: 'chart', rect: { col: 0, row: 2, colSpan: 6, rowSpan: 2 }, ...chart('SPY', 'US', '1D') },
      { type: 'chart', rect: { col: 6, row: 2, colSpan: 6, rowSpan: 2 }, ...chart('QQQ', 'US', '1D') },
    ], 'custom', 4),
  },
  {
    id: 'overview',
    name: 'Market Overview',
    desc: 'Global breadth: overview, heatmap, indices charts and news.',
    build: () => build([
      { type: 'market-overview', rect: { col: 0, row: 0, colSpan: 4, rowSpan: 2 } },
      { type: 'heatmap', rect: { col: 4, row: 0, colSpan: 8, rowSpan: 2 } },
      { type: 'chart', rect: { col: 0, row: 2, colSpan: 6, rowSpan: 2 }, ...chart('SPX', 'US', '1D') },
      { type: 'news', rect: { col: 6, row: 2, colSpan: 6, rowSpan: 2 } },
    ], 'custom', 4),
  },
  {
    id: 'technical',
    name: 'Technical Analysis',
    desc: 'Four charts with indicators alongside AI structure analysis.',
    build: () => build([
      { type: 'chart', rect: { col: 0, row: 0, colSpan: 6, rowSpan: 2 }, ...chart('AAPL', 'US', '1H'), aiOpen: true },
      { type: 'chart', rect: { col: 6, row: 0, colSpan: 6, rowSpan: 2 }, ...chart('NVDA', 'US', '1H') },
      { type: 'chart', rect: { col: 0, row: 2, colSpan: 4, rowSpan: 2 }, ...chart('BTC', 'CRYPTO', '1H') },
      { type: 'chart', rect: { col: 4, row: 2, colSpan: 4, rowSpan: 2 }, ...chart('ETH', 'CRYPTO', '1H') },
      { type: 'ai-analysis', rect: { col: 8, row: 2, colSpan: 4, rowSpan: 2 } },
    ], 'custom', 4),
  },
  {
    id: 'crypto',
    name: 'Crypto',
    desc: 'Major pairs 24/7 with watchlist and live AI.',
    build: () => build([
      { type: 'chart', rect: { col: 0, row: 0, colSpan: 4, rowSpan: 2 }, ...chart('BTC', 'CRYPTO', '1H'), aiOpen: true },
      { type: 'chart', rect: { col: 4, row: 0, colSpan: 4, rowSpan: 2 }, ...chart('ETH', 'CRYPTO', '1H') },
      { type: 'chart', rect: { col: 8, row: 0, colSpan: 4, rowSpan: 2 }, ...chart('SOL', 'CRYPTO', '1H') },
      { type: 'watchlist', rect: { col: 0, row: 2, colSpan: 4, rowSpan: 2 } },
      { type: 'chart', rect: { col: 4, row: 2, colSpan: 8, rowSpan: 2 }, ...chart('BNB', 'CRYPTO', '4H') },
    ], 'custom', 4),
  },
  {
    id: 'pakistan',
    name: 'Pakistan Market',
    desc: 'PSX blue chips on the Karachi session with watchlist.',
    build: () => build([
      { type: 'chart', rect: { col: 0, row: 0, colSpan: 6, rowSpan: 2 }, ...chart('OGDC', 'PK', '1D') },
      { type: 'chart', rect: { col: 6, row: 0, colSpan: 6, rowSpan: 2 }, ...chart('LUCK', 'PK', '1D') },
      { type: 'chart', rect: { col: 0, row: 2, colSpan: 6, rowSpan: 2 }, ...chart('ENGRO', 'PK', '1D') },
      { type: 'watchlist', rect: { col: 6, row: 2, colSpan: 6, rowSpan: 2 } },
    ], 'custom', 4),
  },
  {
    id: 'us',
    name: 'US Market',
    desc: 'Mega-cap US equities with indices and breadth.',
    build: () => build([
      { type: 'chart', rect: { col: 0, row: 0, colSpan: 4, rowSpan: 2 }, ...chart('AAPL', 'US', '1D') },
      { type: 'chart', rect: { col: 4, row: 0, colSpan: 4, rowSpan: 2 }, ...chart('MSFT', 'US', '1D') },
      { type: 'chart', rect: { col: 8, row: 0, colSpan: 4, rowSpan: 2 }, ...chart('NVDA', 'US', '1D') },
      { type: 'market-overview', rect: { col: 0, row: 2, colSpan: 4, rowSpan: 2 } },
      { type: 'chart', rect: { col: 4, row: 2, colSpan: 8, rowSpan: 2 }, ...chart('SPY', 'US', '1D') },
    ], 'custom', 4),
  },
  {
    id: 'india',
    name: 'India Market',
    desc: 'NSE large caps on the Mumbai session with watchlist.',
    build: () => build([
      { type: 'chart', rect: { col: 0, row: 0, colSpan: 6, rowSpan: 2 }, ...chart('RELIANCE', 'IN', '1D') },
      { type: 'chart', rect: { col: 6, row: 0, colSpan: 6, rowSpan: 2 }, ...chart('TCS', 'IN', '1D') },
      { type: 'chart', rect: { col: 0, row: 2, colSpan: 6, rowSpan: 2 }, ...chart('HDFCBANK', 'IN', '1D') },
      { type: 'watchlist', rect: { col: 6, row: 2, colSpan: 6, rowSpan: 2 } },
    ], 'custom', 4),
  },
];

export function getWorkspacePreset(id: string): WorkspacePreset | undefined {
  return WORKSPACE_PRESETS.find(p => p.id === id);
}

/** The layout a brand-new workspace opens with. */
export function defaultWorkspaceLayout(): MarketWorkspaceLayout {
  return cloneLayout(getWorkspacePreset('trading')!.build());
}
