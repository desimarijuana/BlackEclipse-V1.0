// ── Dashboard widget registry ────────────────────────────────────────────────
// The single source of truth for dashboard widgets. Phase 1 ships the engine
// with a small set of placeholder widgets so the customization system is fully
// testable; real data widgets land in Phase 2. Each widget is a WidgetDefinition.

'use client';

import React from 'react';
import {
  Activity, BarChart3, Bell, Briefcase, CalendarDays, CandlestickChart,
  Globe, LayoutDashboard, Newspaper, PieChart, TrendingUp, Wallet,
} from 'lucide-react';
import type { WidgetDefinition } from '@/lib/workspace/widget-def';
import type { WidgetPlacement } from '@/lib/workspace/types';

const ICONS: Record<string, React.ComponentType<{ size?: number; className?: string }>> = {
  activity: Activity,
  'bar-chart': BarChart3,
  bell: Bell,
  briefcase: Briefcase,
  calendar: CalendarDays,
  candlestick: CandlestickChart,
  globe: Globe,
  dashboard: LayoutDashboard,
  newspaper: Newspaper,
  pie: PieChart,
  trending: TrendingUp,
  wallet: Wallet,
};

export function widgetIcon(name: string) {
  return ICONS[name] ?? LayoutDashboard;
}

/** Placeholder body — Phase 2 replaces these with real data widgets. */
function Placeholder({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="flex h-full flex-col p-4">
      <div className="flex items-center justify-between gap-2 border-b border-border/10 pb-2.5 mb-3">
        <h3 className="font-serif text-sm font-semibold text-foreground truncate">{title}</h3>
        <span className="font-mono text-[9px] text-muted-foreground/70 shrink-0">PHASE 2</span>
      </div>
      <div className="flex flex-1 items-center justify-center text-center">
        <p className="text-xs text-muted-foreground/70 italic max-w-[24ch]">{desc}</p>
      </div>
    </div>
  );
}

function makePlaceholder(id: string, category: WidgetDefinition['category'], label: string, desc: string, icon: string, sizes: WidgetDefinition['sizes']): WidgetDefinition {
  return {
    id,
    category,
    label,
    desc,
    icon,
    sizes,
    render: () => <Placeholder title={label} desc={desc} />,
  };
}

export const DASHBOARD_WIDGETS: WidgetDefinition[] = [
  makePlaceholder('market-status', 'markets', 'Market Status', 'US, Europe, Asia, crypto session status.', 'globe', ['small', 'medium']),
  makePlaceholder('market-pulse', 'markets', 'Market Pulse', 'Advancers, decliners, breadth, momentum.', 'activity', ['medium', 'large']),
  makePlaceholder('market-movers', 'markets', 'Market Movers', 'Gainers, losers, volume, breakouts.', 'trending', ['medium', 'large']),
  makePlaceholder('watchlist', 'markets', 'Watchlist', 'Configurable watchlist with live quotes.', 'bar-chart', ['medium', 'large']),
  makePlaceholder('chart', 'markets', 'Chart', 'TradingView / ECharts symbol chart.', 'candlestick', ['large', 'full']),
  makePlaceholder('portfolio', 'portfolio', 'Portfolio', 'Aggregate portfolio value and P&L.', 'briefcase', ['medium', 'large']),
  makePlaceholder('allocation', 'portfolio', 'Allocation', 'Portfolio allocation breakdown.', 'pie', ['medium', 'large']),
  makePlaceholder('risk', 'portfolio', 'Risk', 'VaR, drawdown, volatility, Sharpe.', 'activity', ['medium', 'large']),
  makePlaceholder('economic-calendar', 'macro', 'Economic Calendar', 'Upcoming high-impact economic events.', 'calendar', ['medium', 'large']),
  makePlaceholder('news', 'news', 'Latest News', 'Live market news feed with sentiment.', 'newspaper', ['medium', 'large']),
  makePlaceholder('alerts', 'trading', 'Alerts', 'Active and triggered price alerts.', 'bell', ['small', 'medium']),
  makePlaceholder('journal', 'trading', 'Trading Journal', 'Trading performance and recent trades.', 'wallet', ['medium', 'large']),
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
