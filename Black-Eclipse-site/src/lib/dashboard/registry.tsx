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
  StickyNote, Landmark, Ship, Gauge, Table2, Layers, HeartPulse, Brain, Zap,
} from 'lucide-react';
import type { WidgetDefinition } from '@/lib/workspace/widget-def';
import type { WidgetPlacement } from '@/lib/workspace/types';
import { registerTopic, jsonTopic } from '@/lib/workspace/data-hub';
import {
  MarketIndicesWidget, ForexPairsWidget, CryptoMarketsWidget, CommoditiesWidget,
  TopMoversWidget, SectorHeatmapWidget, NewsFeedWidget, EconomicCalendarWidget,
  StockQuoteWidget, WatchlistWidget,
  LiveTVWidget, RecentFilesWidget, AgentErrorsWidget, WebScraperWidget,
  NotesWidget, GeopoliticsWidget, MaritimeWidget, PolymarketWidget,
  CryptoQuoteStripWidget, TradeTapeWidget, SparklinesWidget, CandleChartWidget,
  StockScreenerWidget, NewsCategoryWidget, PerformanceWidget, PortfolioSummaryWidget,
  RiskMetricsWidget, HoldingsWidget,
  ActiveAlertsWidget, AlertCountWidget, JournalPerformanceWidget,
  GlobalMarketsWidget, MarketStatusWidget,
} from './widgets';
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

// Register the data topics the dashboard widgets depend on. The hub batches
// fetches per topic and only subscribes for visible widgets.
registerTopic(jsonTopic('market:indices:US', '/api/indices?market=US', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('market:indices:CRYPTO', '/api/indices?market=CRYPTO', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('market:overview', '/api/global-overview', { ttl: 300_000, interval: 120_000 }));
registerTopic(jsonTopic('market:commodities', '/api/commodities', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('market:forex', '/api/forex', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('news:feed', '/api/news?limit=30', { ttl: 60_000, interval: 30_000 }));
registerTopic(jsonTopic('econ:calendar', '/api/economics/calendar', { ttl: 300_000, interval: 120_000 }));
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
  brain: Brain, zap: Zap,
};

export function widgetIcon(name: string) {
  return ICONS[name] ?? LayoutDashboard;
}

function def(id: string, category: WidgetDefinition['category'], label: string, desc: string, icon: string, sizes: WidgetDefinition['sizes'], body: (placement: WidgetPlacement) => React.ReactNode, dataDeps?: string[], configFields?: WidgetDefinition['configFields'], defaultConfig?: Record<string, unknown>): WidgetDefinition {
  return { id, category, label, desc, icon, sizes, dataDeps, configFields, defaultConfig, render: (placement) => body(placement) };
}

export const DASHBOARD_WIDGETS: WidgetDefinition[] = [
  // ── Markets ──
  def('market-indices', 'markets', 'Market Indices', 'SPY, QQQ, DIA, IWM — major US indices.', 'line-chart', ['medium', 'large'], () => <MarketIndicesWidget />, ['market:indices:US']),
  def('forex-pairs', 'markets', 'Forex Pairs', 'EURUSD, GBPUSD, USDJPY and more.', 'droplets', ['medium', 'large'], () => <ForexPairsWidget />, ['market:forex']),
  def('crypto-markets', 'markets', 'Crypto Markets', 'BTC, ETH, BNB, SOL live prices.', 'coins', ['medium', 'large'], () => <CryptoMarketsWidget />, ['market:indices:CRYPTO']),
  def('commodities', 'markets', 'Commodities', 'Gold, Oil, Natural Gas, Copper.', 'flame', ['medium', 'large'], () => <CommoditiesWidget />, ['market:commodities']),
  def('sector-heatmap', 'markets', 'Sector Heatmap', 'S&P 500 sector performance.', 'pie', ['medium', 'large'], () => <SectorHeatmapWidget />, ['market:indices:US']),
  def('top-movers', 'markets', 'Top Movers', 'Biggest gainers and losers.', 'trending', ['medium', 'large'], () => <TopMoversWidget />, ['market:overview']),
  def('market-sentiment', 'markets', 'Market Sentiment', 'Fear & greed, bull/bear indicators.', 'activity', ['small', 'medium'], () => UnavailableStub('')),
  def('quote-strip', 'markets', 'Quote Strip', 'Configurable live quote list.', 'bar-chart', ['large', 'full'], () => UnavailableStub('')),
  def('crypto-ticker', 'markets', 'Crypto Ticker', 'Live Kraken/HyperLiquid ticker strip.', 'radio', ['large', 'full'], () => <CryptoQuoteStripWidget />),
  def('polymarket', 'markets', 'Polymarket', 'Live prediction-market prices.', 'gauge', ['medium', 'large'], () => <PolymarketWidget />),
  def('sparklines', 'markets', 'Sparklines', 'Configurable sparkline strip.', 'line-chart', ['large', 'full'], () => <SparklinesWidget />),
  def('trade-tape', 'markets', 'Trade Tape', 'Live trade prints for a crypto pair.', 'activity', ['medium', 'large'], () => <TradeTapeWidget />),

  // ── Research ──
  def('news-feed', 'research', 'News Feed', 'Latest financial headlines.', 'newspaper', ['medium', 'large'], () => <NewsFeedWidget />, ['news:feed']),
  def('stock-quote', 'research', 'Stock Quote', 'Single stock detail (price, volume, chart).', 'bar-chart', ['small', 'medium'], () => <StockQuoteWidget />, ['market:quote:AAPL']),
  def('candle-chart', 'research', 'Candle Chart', 'Candlestick chart for a ticker.', 'candlestick', ['large', 'full'], () => <CandleChartWidget />),
  def('stock-screener', 'research', 'Stock Screener', 'Filter by fundamentals/technicals.', 'table', ['large', 'full'], () => <StockScreenerWidget />),
  def('economic-calendar', 'research', 'Economic Calendar', 'Upcoming macro events.', 'calendar', ['medium', 'large'], () => <EconomicCalendarWidget />, ['econ:calendar']),
  def('news-category', 'research', 'News by Category', 'Category-filtered headlines.', 'newspaper', ['medium', 'large'], () => <NewsCategoryWidget />),

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
  def('live-tv', 'tools', 'Live TV / Streams', 'Financial TV networks + custom streams.', 'radio', ['large', 'full'], () => <LiveTVWidget />),
  def('recent-files', 'tools', 'Recent Files', 'Exports, reports, notebooks.', 'file-text', ['small', 'medium'], () => <RecentFilesWidget />),
  def('agent-errors', 'tools', 'Agent Errors', 'Recent agent execution failures.', 'bot', ['small', 'medium'], () => <AgentErrorsWidget />),
  def('web-scraper', 'tools', 'Web Scraper', 'Scrape tables from any URL.', 'scissors', ['medium', 'large'], () => <WebScraperWidget />),
  def('notes', 'tools', 'Notes', 'Recent/favorite financial notes.', 'sticky-note', ['small', 'medium'], () => <NotesWidget />),

  // ── Geopolitics ──
  def('geopolitics', 'geopolitics', 'Geopolitics Events', 'Live conflict/political events.', 'landmark', ['medium', 'large'], () => <GeopoliticsWidget />),
  def('maritime', 'geopolitics', 'Maritime Vessels', 'Live vessel positions.', 'ship', ['medium', 'large'], () => <MaritimeWidget />),

  // ── Alerts ──
  def('active-alerts', 'alerts', 'Active Alerts', 'Active price/condition alert watches.', 'bell', ['medium', 'large'], () => <ActiveAlertsWidget />, ['alerts:list']),
  def('alert-count', 'alerts', 'Alert Count', 'Active vs triggered alert totals.', 'bell', ['small', 'medium'], () => <AlertCountWidget />, ['alerts:list']),

  // ── Journal ──
  def('journal-performance', 'journal', 'Trading Performance', 'Win rate, P&L, profit factor, expectancy.', 'line-chart', ['medium', 'large'], () => <JournalPerformanceWidget />, ['journal:analytics']),

  // ── Macro / Global ──
  def('global-markets', 'macro', 'Global Markets', 'World market overview.', 'globe', ['medium', 'large'], () => <GlobalMarketsWidget />, ['market:overview']),
  def('market-status', 'macro', 'Market Status', 'Risk on/off, advancing/declining.', 'activity', ['small', 'medium'], () => <MarketStatusWidget />, ['market:indices:US']),

  // ── AI ──
  def('agent-activity', 'ai', 'Agent Activity', 'Active agents and their tasks.', 'bot', ['medium', 'large'], () => <AgentActivityWidget />, ['agent:activity']),
  def('recent-research', 'ai', 'Recent Research', 'Recent agent research reports.', 'file-text', ['medium', 'large'], () => <RecentResearchWidget />, ['agent:activity']),
  def('ai-insights', 'ai', 'AI Insights', 'Engine brief and change feed.', 'brain', ['medium', 'large'], () => <AIInsightsWidget />, ['agent:activity']),

  // ── Charts ──
  def('asset-chart', 'markets', 'Asset Chart', 'Line chart with EMA 20/50 and RSI 14.', 'line-chart', ['large', 'full'], () => <AssetChartWidget />, ['chart:asset:AAPL']),
  def('eclipse-chart', 'markets', 'Eclipse Chart', 'Native BlackEclipse chart — candlesticks, indicators, provider-switchable.', 'candlestick', ['large', 'full'], (p) => <EclipseChartWidget placement={p} />, undefined,
    [{ key: 'symbol', label: 'Symbol', type: 'symbol', placeholder: 'Search any symbol…', default: 'AAPL' }],
    { symbol: 'AAPL' }),
  def('tradingview-chart', 'markets', 'TradingView Chart', 'Full TradingView advanced chart with RSI.', 'candlestick', ['large', 'full'], (p) => <TradingViewChartWidget placement={p} />, undefined,
    [{ key: 'symbol', label: 'Symbol', type: 'symbol', placeholder: 'Search any symbol…', default: 'AAPL' }],
    { symbol: 'AAPL' }),
  def('economic-chart', 'macro', 'Economic Data Chart', 'Economic series line chart (US CPI).', 'line-chart', ['large', 'full'], () => <EconomicDataChartWidget />, ['econ:series:us-cpi']),
  def('fund-performance-chart', 'portfolio', 'Portfolio Performance', 'All funds indexed vs the benchmarks you pick.', 'line-chart', ['large', 'full'], (p) => <FundPerformanceChartWidget placement={p} />, undefined,
    [{ key: 'compare', label: 'Compare with', type: 'symbols', placeholder: 'Add SPY, QQQ, BTC-USD…' }],
    { compare: ['SPY'] }),
  def('macro-snapshot', 'macro', 'Macro Snapshot', 'Central-bank rates and key prints.', 'gauge', ['medium', 'large'], () => <MacroSnapshotWidget />, ['econ:snapshot']),

  // ── Intelligence ──
  def('market-regime', 'intelligence', 'Market Regime', 'Risk on/off, trending, range, volatility.', 'activity', ['medium', 'large'], () => <MarketRegimeWidget />, ['market:indices:US']),
  def('what-changed', 'intelligence', 'What Changed?', 'Session-over-session market changes.', 'trending', ['medium', 'large'], () => <WhatChangedWidget />, ['market:indices:US']),
  def('opportunity-scanner', 'intelligence', 'Opportunity Scanner', 'Momentum and mean-reversion setups with why.', 'zap', ['medium', 'large'], () => <OpportunityScannerWidget />, ['market:overview']),
  def('market-drivers', 'intelligence', 'Market Drivers', 'What is moving markets, ranked.', 'gauge', ['medium', 'large'], () => <MarketDriversWidget />, ['market:indices:US']),

  // ── Heatmap ──
  def('market-heatmap', 'markets', 'Market Heatmap', 'Country/index treemap — sized by market cap, coloured by % change.', 'layers', ['large', 'full'], (p) => <MarketHeatmapWidget placement={p} />),

  // ── Portfolio comparisons ──
  def('funds-comparison-chart', 'portfolio', 'Overall Performance', 'Every fund indexed vs the benchmarks — 3MO.', 'line-chart', ['large', 'full'], () => <FundsComparisonChartWidget />),
];

export const DASHBOARD_WIDGET_IDS = DASHBOARD_WIDGETS.map(w => w.id);

export function getWidgetDefinition(id: string): WidgetDefinition | undefined {
  return DASHBOARD_WIDGETS.find(w => w.id === id);
}

export function renderDashboardWidget(widgetId: string, placement: WidgetPlacement): React.ReactNode {
  const def = getWidgetDefinition(widgetId);
  if (!def) return <div className="p-4 text-xs text-muted-foreground">Unknown widget: {widgetId}</div>;
  return def.render ? def.render(placement) : <div className="p-4 text-xs text-muted-foreground">No renderer for {widgetId}</div>;
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
