// ── Dashboard widget registry ────────────────────────────────────────────────
// The single source of truth for Command Center widgets. Each widget is a
// WidgetDefinition. Real data widgets consume DataHub topics; widgets needing
// external/broker integrations render a clear UNAVAILABLE state (never fabricate).

'use client';

import React from 'react';
import {
  Activity, BarChart3, Bell, Briefcase, CalendarDays, CandlestickChart,
  Globe, LayoutDashboard, Newspaper, PieChart, TrendingUp, Wallet,
  LineChart, Coins, Droplets, Flame, Radio, FileText, Bot, Scissors,
  StickyNote, Landmark, Ship, Gauge, Table2, Layers, HeartPulse, Brain, Zap, ScanEye, MapPin, Clock,
} from '@/lib/icons';
import type { WidgetDefinition } from '@/lib/workspace/widget-def';
import type { WidgetPlacement } from '@/lib/workspace/types';
import { registerTopic, jsonTopic } from '@/lib/workspace/data-hub';
import { MARKET_CONFIG_FIELD } from './market-views';
// Layout composition lives in ./layout (pure + unit-tested); re-exported below
// so existing `@/lib/dashboard/registry` imports keep working.
export {
  buildMarketViewLayout, buildRailSections, buildLeftSections,
  assetClassFor, LEFT_WIDGET_IDS, ASSET_RAIL, WIDGET_MIN_HEIGHT,
  WIDGET_FRAME_HEIGHT, CENTRE_TRACKS, composeBoard, placementSizing,
  type AssetClass, type BoardSpec, type BoardCell,
} from './layout';

import {
  MarketIndicesWidget, ForexPairsWidget, CryptoMarketsWidget, CommoditiesWidget,
  TopMoversWidget, SectorHeatmapWidget, NewsFeedWidget, EconomicCalendarWidget,
  EarningsCalendarWidget,
  StockQuoteWidget, WatchlistWidget,
  RecentFilesWidget, AgentErrorsWidget, WebScraperWidget,
  NotesWidget, GeopoliticsWidget, MaritimeWidget, PolymarketWidget,
  CryptoQuoteStripWidget, TradeTapeWidget, SparklinesWidget, CandleChartWidget,
  StockScreenerWidget, NewsCategoryWidget, PerformanceWidget, PortfolioSummaryWidget,
  RiskMetricsWidget, HoldingsWidget,
  ActiveAlertsWidget, AlertCountWidget, JournalPerformanceWidget,
  GlobalMarketsWidget, MarketStatusWidget,
} from './widgets';
import { CryptoTvlWidget, CryptoLiquidationsWidget } from './crypto-widgets';
import {
  AssetChartWidget, EconomicDataChartWidget, FundPerformanceChartWidget, FundsComparisonChartWidget, MacroSnapshotWidget,
  TradingViewChartWidget, EclipseChartWidget,
} from './chart-widgets';
import { MarketHeatmapWidget } from './heatmap-widget';
import { HEATMAP_MARKETS } from '@/lib/heatmap';
import {
  MarketRegimeWidget, WhatChangedWidget, OpportunityScannerWidget, MarketDriversWidget,
} from './intelligence-widgets';
import { AgentActivityWidget, RecentResearchWidget, AIInsightsWidget } from './ai-widgets';
import { DriftStatusWidget } from './drift-status-widget';
import { ProjectScopeWidget } from './project-widget';
import { HistoryWidget } from './history-widget';
import { GalleryWidget } from './gallery-widget';
import {
  InvestorEyeWidget, INVESTOR_EYE_RANGE_FIELD, INVESTOR_EYE_LENS_FIELD,
} from './investor-eye-widget';
import { InvestorEyeMapWidget, INVESTOR_EYE_MAP_RANGE_FIELD } from './investor-eye-map-widget';
import {
  LiveIntelligenceWidget, LIVE_INTELLIGENCE_MUTED_FIELD, LIVE_INTELLIGENCE_AUTOPLAY_FIELD,
} from './live-intelligence-widget';
import { MARKET_RAIL_WIDGETS, marketPanelIcon } from './market-rail-widgets';
import { SOURCE_WIDGETS } from '@/lib/workspace/generic-widgets';
import { getSdkWidgetDefinition } from '@/lib/sdk/widgets';
import { registerWidget, getWidget } from '@/lib/workspace/widget-registry';
import { ClockWidget, DEFAULT_CLOCK_CONFIG } from './clock-widget';

// Register the data topics the dashboard widgets depend on. The hub batches
// fetches per topic and only subscribes for visible widgets.
registerTopic(jsonTopic('market:indices:US', '/api/indices?market=US', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('market:indices:CRYPTO', '/api/indices?market=CRYPTO', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('market:overview', '/api/global-overview', { ttl: 300_000, interval: 120_000 }));
registerTopic(jsonTopic('market:commodities', '/api/commodities', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('market:forex', '/api/forex', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('news:feed', '/api/news?limit=30', { ttl: 60_000, interval: 30_000 }));
registerTopic(jsonTopic('econ:calendar', '/api/economics/calendar', { ttl: 300_000, interval: 120_000 }));
// Earnings calendar — server-cached 6h upstream, so a modest client cadence.
registerTopic(jsonTopic('earnings:calendar', '/api/earnings', { ttl: 1_800_000, interval: 1_800_000 }));
registerTopic(jsonTopic('market:quote:AAPL', '/api/quote?symbols=AAPL', { ttl: 60_000, interval: 30_000 }));
registerTopic(jsonTopic('market:quote:AAPL,MSFT,NVDA,TSLA,AMZN', '/api/quote?symbols=AAPL,MSFT,NVDA,TSLA,AMZN', { ttl: 60_000, interval: 30_000 }));
registerTopic(jsonTopic('alerts:list', '/api/alerts', { ttl: 60_000, interval: 30_000 }));
registerTopic(jsonTopic('journal:analytics', '/api/journal/analytics', { ttl: 60_000, interval: 30_000 }));
registerTopic(jsonTopic('chart:asset:AAPL', '/api/price-history?symbol=AAPL&market=US', { ttl: 300_000, interval: 120_000 }));
registerTopic(jsonTopic('econ:series:us-cpi', '/api/economics?source=us-cpi', { ttl: 600_000, interval: 300_000 }));
registerTopic(jsonTopic('econ:snapshot', '/api/economics/snapshot', { ttl: 600_000, interval: 300_000 }));
registerTopic(jsonTopic('agent:activity', '/api/agent/activity', { ttl: 30_000, interval: 15_000 }));

// Heatmap topic per market — picked via the widget's country/index selector.
// Registering all markets up front lets the hub cache + auto-refresh each view
// and unsubscribe hidden ones without a dynamic-registration race.
for (const m of HEATMAP_MARKETS) {
  registerTopic(jsonTopic(`market:heatmap:${m.id}`, `/api/heatmap?market=${m.id}`, { ttl: 180_000, interval: 180_000 }));
}

const ICONS: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  activity: Activity, 'bar-chart': BarChart3, bell: Bell, briefcase: Briefcase,
  calendar: CalendarDays, candlestick: CandlestickChart, globe: Globe,
  dashboard: LayoutDashboard, newspaper: Newspaper, pie: PieChart,
  trending: TrendingUp, wallet: Wallet, 'line-chart': LineChart, coins: Coins,
  droplets: Droplets, flame: Flame, radio: Radio, 'file-text': FileText,
  bot: Bot, scissors: Scissors, 'sticky-note': StickyNote, landmark: Landmark,
  ship: Ship, gauge: Gauge, table: Table2, layers: Layers, heart: HeartPulse,
  brain: Brain, zap: Zap, 'scan-eye': ScanEye, 'map-pin': MapPin, clock: Clock,
};
export function widgetIcon(name: string) {
  return ICONS[name] ?? marketPanelIcon(name) ?? LayoutDashboard;
}

function def(id: string, category: WidgetDefinition['category'], label: string, desc: string, icon: string, sizes: WidgetDefinition['sizes'], body: (placement: WidgetPlacement) => React.ReactNode, dataDeps?: string[], configFields?: WidgetDefinition['configFields'], defaultConfig?: Record<string, unknown>): WidgetDefinition {
  return { id, category, label, desc, icon, sizes, dataDeps, configFields, defaultConfig, render: (placement) => body(placement) };
}

/**
 * Market-aware widget definition. Adds the shared Market config field (so the
 * user can pin the widget to any market — US, PSX, Crypto, Forex, …) alongside
 * any widget-specific fields, and defaults it to "follow the active tab".
 */
function mdef(
  id: string,
  category: WidgetDefinition['category'],
  label: string,
  desc: string,
  icon: string,
  sizes: WidgetDefinition['sizes'],
  body: (placement: WidgetPlacement) => React.ReactNode,
  dataDeps?: string[],
  extraFields?: WidgetDefinition['configFields'],
  extraConfig?: Record<string, unknown>,
): WidgetDefinition {
  return def(
    id, category, label, desc, icon, sizes, body, dataDeps,
    [MARKET_CONFIG_FIELD, ...(extraFields ?? [])],
    { ...(extraConfig ?? {}) },
  );
}

const CORE_WIDGETS: WidgetDefinition[] = [
  // ── Markets ──
  mdef('market-indices', 'markets', 'Market Indices', 'Headline index quotes for the chosen market.', 'line-chart', ['medium', 'large'], (p) => <MarketIndicesWidget placement={p} />),
  def('forex-pairs', 'markets', 'Forex Pairs', 'EURUSD, GBPUSD, USDJPY and more.', 'droplets', ['medium', 'large'], () => <ForexPairsWidget />, ['market:forex']),
  def('crypto-markets', 'markets', 'Crypto Markets', 'BTC, ETH, BNB, SOL live prices.', 'coins', ['medium', 'large'], () => <CryptoMarketsWidget />, ['market:indices:CRYPTO']),
  def('crypto-tvl', 'markets', 'DeFi TVL', 'Protocol total value locked (AAVE, UNI, LDO…) from DefiLlama.', 'layers', ['medium', 'large'], () => <CryptoTvlWidget />),
  def('crypto-liquidations', 'markets', 'Crypto Liquidations', '24h long vs short forced liquidations for BTC/ETH/SOL (CoinGlass).', 'flame', ['medium', 'large'], () => <CryptoLiquidationsWidget />),
  def('commodities', 'markets', 'Commodities', 'Gold, Oil, Natural Gas, Copper.', 'flame', ['medium', 'large'], () => <CommoditiesWidget />, ['market:commodities']),
  mdef('sector-heatmap', 'markets', 'Sector Heatmap', 'Sector performance for the chosen market.', 'pie', ['medium', 'large'], (p) => <SectorHeatmapWidget placement={p} />),
  mdef('top-movers', 'markets', 'Top Movers', 'Biggest gainers and losers for the chosen market.', 'trending', ['medium', 'large'], (p) => <TopMoversWidget placement={p} />),
  def('market-sentiment', 'markets', 'Market Sentiment', 'Fear & greed, bull/bear indicators.', 'activity', ['small', 'medium'], () => UnavailableStub('')),
  def('quote-strip', 'markets', 'Quote Strip', 'Configurable live quote list.', 'bar-chart', ['large', 'full'], () => UnavailableStub('')),
  def('crypto-ticker', 'markets', 'Crypto Ticker', 'Live crypto quote strip.', 'radio', ['large', 'full'], () => <CryptoQuoteStripWidget />, ['market:indices:CRYPTO']),
  def('polymarket', 'markets', 'Polymarket', 'Live prediction-market prices.', 'gauge', ['medium', 'large'], () => <PolymarketWidget />),
  def('sparklines', 'markets', 'Sparklines', 'One-month price sparklines for the active market.', 'line-chart', ['large', 'full'], () => <SparklinesWidget />),
  def('trade-tape', 'markets', 'Trade Tape', 'Live crypto quote tape (exchange tick data not connected).', 'activity', ['medium', 'large'], () => <TradeTapeWidget />, ['market:indices:CRYPTO']),

  // ── Research ──
  def('news-feed', 'research', 'News Feed', 'Latest financial headlines.', 'newspaper', ['medium', 'large'], () => <NewsFeedWidget />, ['news:feed']),
  def('stock-quote', 'research', 'Stock Quote', 'Single stock detail (price, volume, chart).', 'bar-chart', ['small', 'medium'], () => <StockQuoteWidget />, ['market:quote:AAPL']),
  mdef('candle-chart', 'research', 'Candle Chart', 'Candlesticks for the active market’s lead instrument.', 'candlestick', ['large', 'full'], (p) => <CandleChartWidget placement={p} />),
  mdef('stock-screener', 'research', 'Stock Screener', 'Live JDDS rows ranked by market cap for the chosen market.', 'table', ['large', 'full'], (p) => <StockScreenerWidget placement={p} />),
  def('economic-calendar', 'research', 'Economic Calendar', 'Upcoming macro events.', 'calendar', ['medium', 'large'], () => <EconomicCalendarWidget />, ['econ:calendar']),
  def('earnings-calendar', 'research', 'Earnings Calendar', 'Upcoming company earnings — date, BMO/AMC and EPS estimate.', 'calendar', ['medium', 'large'], () => <EarningsCalendarWidget />, ['earnings:calendar']),
  def('news-category', 'research', 'News by Category', 'Category-filtered headlines.', 'newspaper', ['medium', 'large'], () => <NewsCategoryWidget />, ['news:feed']),
  def('project-scope', 'research', 'Project Scope', 'The project the chat is scoped to: its strategies, backtests and artifacts.', 'folder-plus', ['small', 'medium'], () => <ProjectScopeWidget />),
  def('local-history', 'research', 'Local History', 'The market history this machine already holds: the local copy Eclipse has already paid for.', 'database', ['medium', 'large'], () => <HistoryWidget />),
  def('strategy-gallery', 'research', 'Strategy Gallery', 'Published strategies with the grade their evidence earned. Clone one back into the quant store.', 'star', ['medium', 'large'], () => <GalleryWidget />),

  // ── Portfolio ──
  def('watchlist', 'portfolio', 'Watchlist', 'Your symbols with live prices and favourites.', 'bar-chart', ['medium', 'large'], () => <WatchlistWidget />, ['market:quote:AAPL,MSFT,NVDA,TSLA,AMZN']),
  def('performance', 'portfolio', 'Performance', 'P&L today/week/month/YTD.', 'line-chart', ['medium', 'large'], () => <PerformanceWidget />),
  def('portfolio-summary', 'portfolio', 'Portfolio Summary', 'Holdings with allocation breakdown.', 'briefcase', ['medium', 'large'], () => <PortfolioSummaryWidget />),
  def('risk-metrics', 'portfolio', 'Risk Metrics', 'Volatility, beta, drawdown, Sharpe.', 'activity', ['medium', 'large'], () => <RiskMetricsWidget />),
  def('holdings', 'portfolio', 'Holdings', 'Long-term broker holdings.', 'layers', ['large', 'full'], () => <HoldingsWidget />),

  // ── Trading ──
  def('quick-trade', 'trading', 'Quick Trade', 'Fast order entry (crypto + equities).', 'zap', ['medium', 'large'], () => UnavailableStub('Quick Trade')),
  def('open-positions', 'trading', 'Open Positions', 'Live broker positions.', 'briefcase', ['medium', 'large'], () => UnavailableStub('Open Positions')),
  def('working-orders', 'trading', 'Working Orders', 'Pending orders (click × to cancel).', 'bell', ['medium', 'large'], () => UnavailableStub('Working Orders')),
  def('margin-usage', 'trading', 'Margin Usage', 'Available/used margin, total, usage %.', 'gauge', ['small', 'medium'], () => UnavailableStub('Margin Usage')),
  def('today-pnl', 'trading', 'Today P&L', 'Aggregate broker P&L.', 'trending', ['small', 'medium'], () => UnavailableStub('Today P&L')),

  // ── Tools ──
  // `live-tv` is the ORIGINAL registry slot; it now renders the real Live
  // Intelligence widget (it used to be an UNAVAILABLE stub). Keeping the id means
  // any saved layout that already placed this slot keeps working.
  def('live-tv', 'tools', 'Live Intelligence', 'Live financial, market and world-news channels.', 'radio', ['large', 'full'], (p) => <LiveIntelligenceWidget placement={p} />, undefined,
    [LIVE_INTELLIGENCE_AUTOPLAY_FIELD, LIVE_INTELLIGENCE_MUTED_FIELD],
    { autoplay: true, muted: true }),
  def('clock', 'tools', 'Clock', 'Live local or timezone-pinned clock.', 'clock', ['small', 'medium'], (p) => <ClockWidget placement={p} />, undefined,
    [
      { key: 'timezone', label: 'Timezone', type: 'text', placeholder: 'UTC, Europe/London, America/New_York…' },
      { key: 'format', label: 'Format', type: 'select', options: [{ value: '24h', label: '24-hour' }, { value: '12h', label: '12-hour' }], default: '24h' },
      { key: 'showSeconds', label: 'Show seconds', type: 'boolean', default: true },
      { key: 'showDate', label: 'Show date', type: 'boolean', default: true },
      { key: 'label', label: 'Label', type: 'text', placeholder: 'Clock' },
    ],
    { ...DEFAULT_CLOCK_CONFIG }),
  def('recent-files', 'tools', 'Recent Files', 'Exports, reports, notebooks.', 'file-text', ['small', 'medium'], () => <RecentFilesWidget />),
  def('agent-errors', 'tools', 'Agent Errors', 'Recent agent execution failures.', 'bot', ['small', 'medium'], () => <AgentErrorsWidget />),
  def('web-scraper', 'tools', 'Web Scraper', 'Scrape tables from any URL.', 'scissors', ['medium', 'large'], () => <WebScraperWidget />),
  def('notes', 'tools', 'Notes', 'Recent/favorite financial notes.', 'sticky-note', ['small', 'medium'], () => <NotesWidget />),

  // ── Geopolitics ──
  def('geopolitics', 'geopolitics', 'Geopolitics Events', 'Live conflict/military/diplomatic events from Investor Eye.', 'landmark', ['medium', 'large'], () => <GeopoliticsWidget />, ['investor-eye:state:24']),
  def('maritime', 'geopolitics', 'Maritime & Trade', 'Live shipping/trade events from Investor Eye.', 'ship', ['medium', 'large'], () => <MaritimeWidget />, ['investor-eye:state:24']),

  // ── Alerts ──
  def('active-alerts', 'alerts', 'Active Alerts', 'Active price/condition alert watches.', 'bell', ['medium', 'large'], () => <ActiveAlertsWidget />, ['alerts:list']),
  def('alert-count', 'alerts', 'Alert Count', 'Active vs triggered alert totals.', 'bell', ['small', 'medium'], () => <AlertCountWidget />, ['alerts:list']),

  // ── Journal ──
  def('journal-performance', 'journal', 'Trading Performance', 'Win rate, P&L, profit factor, expectancy.', 'line-chart', ['medium', 'large'], () => <JournalPerformanceWidget />, ['journal:analytics']),

  // ── Macro / Global ──
  def('global-markets', 'macro', 'Global Markets', 'World market overview.', 'globe', ['medium', 'large'], () => <GlobalMarketsWidget />, ['market:overview']),
  mdef('market-status', 'macro', 'Market Status', 'Risk on/off, advancing/declining.', 'activity', ['small', 'medium'], (p) => <MarketStatusWidget placement={p} />),

  // ── AI ──
  def('agent-activity', 'ai', 'Agent Activity', 'Active agents and their tasks.', 'bot', ['medium', 'large'], () => <AgentActivityWidget />, ['agent:activity']),
  def('recent-research', 'ai', 'Recent Research', 'Recent agent research reports.', 'file-text', ['medium', 'large'], () => <RecentResearchWidget />, ['agent:activity']),
  def('ai-insights', 'ai', 'AI Insights', 'Engine brief and change feed.', 'brain', ['medium', 'large'], () => <AIInsightsWidget />, ['agent:activity']),
  def('drift-status', 'ai', 'Production Drift', 'Agent scopes currently drifting, with a short trend.', 'activity', ['small', 'medium'], () => <DriftStatusWidget />),

  // ── Charts ──
  def('asset-chart', 'markets', 'Asset Chart', 'Line chart with EMA 20/50 and RSI 14.', 'line-chart', ['large', 'full'], () => <AssetChartWidget />, ['chart:asset:AAPL']),
  // Charts default to the active market tab's lead instrument; the Symbol
  // field pins a specific one, and the Market field pins the data market.
  mdef('eclipse-chart', 'markets', 'Eclipse Chart', 'Native BlackEclipse chart — opens on the active market, symbol configurable.', 'candlestick', ['large', 'full'], (p) => <EclipseChartWidget placement={p} />, undefined,
    [{ key: 'symbol', label: 'Symbol', type: 'symbol', placeholder: 'Search any symbol (blank = market default)…' }]),
  mdef('tradingview-chart', 'markets', 'TradingView Chart', 'Full TradingView chart — opens on the active market, symbol configurable.', 'candlestick', ['large', 'full'], (p) => <TradingViewChartWidget placement={p} />, undefined,
    [{ key: 'symbol', label: 'Symbol', type: 'symbol', placeholder: 'Search any symbol (blank = market default)…' }]),
  def('economic-chart', 'macro', 'Economic Data Chart', 'Economic series line chart (US CPI).', 'line-chart', ['large', 'full'], () => <EconomicDataChartWidget />, ['econ:series:us-cpi']),
  def('fund-performance-chart', 'portfolio', 'Portfolio Performance', 'All funds indexed vs the benchmarks you pick.', 'line-chart', ['large', 'full'], (p) => <FundPerformanceChartWidget placement={p} />, undefined,
    [{ key: 'compare', label: 'Compare with', type: 'symbols', placeholder: 'Add SPY, QQQ, BTC-USD…' }],
    { compare: ['SPY'] }),
  def('macro-snapshot', 'macro', 'Macro Snapshot', 'Central-bank rates and key prints.', 'gauge', ['medium', 'large'], () => <MacroSnapshotWidget />, ['econ:snapshot']),

  // ── Intelligence ──
  mdef('market-regime', 'intelligence', 'Market Regime', 'Risk on/off, trending, range, volatility.', 'activity', ['medium', 'large'], (p) => <MarketRegimeWidget placement={p} />),
  mdef('what-changed', 'intelligence', 'What Changed?', 'Session-over-session market changes.', 'trending', ['medium', 'large'], (p) => <WhatChangedWidget placement={p} />),
  mdef('opportunity-scanner', 'intelligence', 'Opportunity Scanner', 'Momentum and mean-reversion setups with why.', 'zap', ['medium', 'large'], (p) => <OpportunityScannerWidget placement={p} />),
  mdef('market-drivers', 'intelligence', 'Market Drivers', 'What is moving markets, ranked.', 'gauge', ['medium', 'large'], (p) => <MarketDriversWidget placement={p} />),

  // ── Heatmap ── (market picker lives IN the widget header; no config field)
  def('market-heatmap', 'markets', 'Market Heatmap', 'Treemap of equities, crypto, forex or commodities — sized by cap, coloured by % change.', 'layers', ['large', 'full'], (p) => <MarketHeatmapWidget placement={p} />),

  // ── Portfolio comparisons ──
  def('funds-comparison-chart', 'portfolio', 'Overall Performance', 'Every fund indexed vs the benchmarks — 3MO.', 'line-chart', ['large', 'full'], () => <FundsComparisonChartWidget />),

  // ── Market rail (default right-hand column; draggable to the centre too) ──
  ...MARKET_RAIL_WIDGETS,

  // ── Intelligence: Investor Eye ──
  // Appended LAST so the index-based persona templates (templates.ts) keep
  // pointing at the same widgets. Reuses the full Investor Eye state topics.
  def('investor-eye', 'intelligence', 'Investor Eye', 'Live normalized world events — conflict, energy, trade and hazards.', 'scan-eye', ['medium', 'large'], (p) => <InvestorEyeWidget placement={p} />, ['investor-eye:state:24'],
    [INVESTOR_EYE_RANGE_FIELD, INVESTOR_EYE_LENS_FIELD], { range: '24h', lens: 'all' }),

  // ── Intelligence: Investor Eye MAP ──
  // The spatial companion to the feed widget — the same interactive world map /
  // 3D globe the full screen renders, embedded in the grid. Reuses the SAME
  // state topics + layer builders (no second fetch path), and its map chunk is
  // lazy so a dashboard without this widget never loads ECharts/echarts-gl.
  // Sits at the tail alongside `investor-eye` so the index-based persona
  // templates (templates.ts) keep pointing at the same widgets.
  def('investor-eye-map', 'intelligence', 'Investor Eye Map', 'Interactive world map / 3D globe of the live event layers.', 'map-pin', ['medium', 'large', 'full'], (p) => <InvestorEyeMapWidget placement={p} />, ['investor-eye:state:24'],
    [INVESTOR_EYE_MAP_RANGE_FIELD], { range: '24h' }),

  // ── Generic source-driven primitives (appended LAST to preserve index-based
  //    persona templates). These render whatever `data-source.ts` resolves for
  //    their `source` config, so an agent can surface a portfolio (or any other
  //    allow-listed source) on ANY page, not just the Command Center. See
  //    `src/lib/workspace/generic-widgets.tsx`. ──
  ...SOURCE_WIDGETS,
];

for (const widget of CORE_WIDGETS) registerWidget(widget);

export const DASHBOARD_WIDGETS: WidgetDefinition[] = CORE_WIDGETS;
export const DASHBOARD_WIDGET_IDS = CORE_WIDGETS.map(w => w.id);

export function getWidgetDefinition(id: string): WidgetDefinition | undefined {
  return getWidget(id) ?? getSdkWidgetDefinition(id);
}
export function renderDashboardWidget(widgetId: string, placement: WidgetPlacement): React.ReactNode {
  const def = getWidgetDefinition(widgetId);
  if (!def || !def.render) {
    // A widget that exists in a blueprint but has no host renderer yet (an
    // agent-added or engineered component). Keep it VISIBLE with an honest
    // state instead of silently dropping it.
    return (
      <div className="flex h-full flex-col p-4">
        <div className="flex items-center justify-between gap-2 border-b border-border/10 pb-2.5 mb-3">
          <h3 className="truncate font-serif text-sm font-semibold text-foreground">Needs a renderer</h3>
          <span className="shrink-0 rounded border border-amber-500/25 bg-amber-500/10 px-1 py-0.5 font-mono text-[8px] font-bold uppercase tracking-wide text-amber-400">
            unavailable
          </span>
        </div>
        <div className="flex flex-1 items-center justify-center text-center">
          <p className="max-w-[30ch] text-xs italic text-amber-400/80">
            The component “{widgetId}” is in this page but has no installed renderer yet. The Engineer path can add one.
          </p>
        </div>
      </div>
    );
  }
  return def.render(placement);
}

function UnavailableStub(label: string) {
  return (
    <div className="flex h-full flex-col p-4">
      <div className="flex items-center justify-between gap-2 border-b border-border/10 pb-2.5 mb-3">
        <h3 className="font-serif text-sm font-semibold text-foreground truncate">{label}</h3>
      </div>
      <div className="flex flex-1 items-center justify-center text-center">
        <p className="text-xs text-amber-400/80 italic max-w-[24ch]">UNAVAILABLE — data source not connected yet.</p>
      </div>
    </div>
  );
}
