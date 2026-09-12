'use client';

// ── MarketSidePanel — collapsible, customizable right-hand market column ────
// A mini market-overview: Fear & Greed gauge, market breadth, top gainers/losers,
// global snapshot (VIX, US 10Y, DXY, Gold, Oil, BTC), and market-hours status dots
// for NYSE, LSE, Tokyo, Shanghai, NSE. Collapsible; data flows through the DataHub.
//
// The panel is user-customizable: enter edit mode to hide/reorder each section.
// Preferences persist to localStorage so the layout survives reloads.

import React, { useEffect, useMemo, useState } from 'react';
import {
  ChevronRight, ChevronLeft, ChevronDown, ChevronUp, TrendingUp, TrendingDown,
  Activity, Globe, Gauge, Settings2, Eye, EyeOff, RotateCcw,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { useTopic, registerTopic, jsonTopic } from '@/lib/workspace/data-hub';

// Register the topics this panel needs (idempotent).
registerTopic(jsonTopic('panel:indices', '/api/indices?market=US', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('panel:commodities', '/api/commodities', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('panel:forex', '/api/forex', { ttl: 120_000, interval: 60_000 }));
registerTopic(jsonTopic('panel:overview', '/api/global-overview', { ttl: 300_000, interval: 120_000 }));

interface IndexRow { name: string; symbol: string; price: number; change: number; changePercent: number; }
interface CommodityRow { symbol: string; name: string; price: number; changePct: number; found: boolean; }
interface ForexRow { symbol: string; name: string; price: number; changePct: number; found: boolean; }
interface OverviewGroup { id: string; country: string; name?: string; stocks: { symbol: string; name: string; price: number; changePct: number }[]; }

const UP = 'text-emerald-400';
const DOWN = 'text-rose-400';
const tone = (n: number) => (n > 0 ? UP : n < 0 ? DOWN : 'text-muted-foreground');

/** Market-hours status for a set of exchanges (client-side, timezone-aware). */
function marketStatus(exchange: string, tz: string, openHour: number, closeHour: number): 'open' | 'closed' | 'pre' {
  try {
    const parts = new Intl.DateTimeFormat('en-US', { timeZone: tz, hour: 'numeric', hour12: false, weekday: 'short' }).formatToParts(new Date());
    const hour = Number(parts.find(p => p.type === 'hour')?.value ?? NaN);
    const wd = parts.find(p => p.type === 'weekday')?.value ?? '';
    const weekdays = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const weekday = weekdays.indexOf(wd);
    if (!Number.isFinite(hour) || weekday < 0) return 'open';
    if (weekday === 0 || weekday === 6) return 'closed';
    if (hour >= openHour && hour < closeHour) return 'open';
    if (hour >= openHour - 1 && hour < openHour) return 'pre';
    return 'closed';
  } catch { return 'open'; }
}

const EXCHANGES = [
  { label: 'NYSE', tz: 'America/New_York', open: 9, close: 16 },
  { label: 'LSE', tz: 'Europe/London', open: 8, close: 16 },
  { label: 'Tokyo', tz: 'Asia/Tokyo', open: 9, close: 15 },
  { label: 'Shanghai', tz: 'Asia/Shanghai', open: 9, close: 15 },
  { label: 'NSE', tz: 'Asia/Kolkata', open: 9, close: 15 },
];

type SectionId = 'fear-greed' | 'breadth' | 'movers' | 'snapshot' | 'hours';
const SECTION_META: Array<{ id: SectionId; label: string }> = [
  { id: 'fear-greed', label: 'Fear & Greed' },
  { id: 'breadth', label: 'Market Breadth' },
  { id: 'movers', label: 'Top Movers' },
  { id: 'snapshot', label: 'Global Snapshot' },
  { id: 'hours', label: 'Market Hours' },
];
const DEFAULT_ORDER: SectionId[] = SECTION_META.map(s => s.id);
const PANEL_KEY = 'be_market_panel_v1';

interface PanelConfig { order: SectionId[]; hidden: SectionId[]; }

function loadPanelConfig(): PanelConfig {
  if (typeof window === 'undefined') return { order: DEFAULT_ORDER, hidden: [] };
  try {
    const raw = window.localStorage.getItem(PANEL_KEY);
    if (!raw) return { order: DEFAULT_ORDER, hidden: [] };
    const parsed = JSON.parse(raw) as Partial<PanelConfig>;
    const known = new Set(DEFAULT_ORDER);
    const order = Array.isArray(parsed.order)
      ? parsed.order.filter((id): id is SectionId => known.has(id as SectionId))
      : [];
    // Append any sections not present in the stored order (e.g. new sections).
    for (const id of DEFAULT_ORDER) if (!order.includes(id)) order.push(id);
    const hidden = Array.isArray(parsed.hidden)
      ? parsed.hidden.filter((id): id is SectionId => known.has(id as SectionId))
      : [];
    return { order, hidden };
  } catch {
    return { order: DEFAULT_ORDER, hidden: [] };
  }
}

export function MarketSidePanel({ className }: { className?: string }) {
  const [open, setOpen] = useState(true);
  const [editMode, setEditMode] = useState(false);
  const [config, setConfig] = useState<PanelConfig>(() => ({ order: DEFAULT_ORDER, hidden: [] }));

  // Load persisted customization on mount (avoids SSR hydration mismatch).
  useEffect(() => { setConfig(loadPanelConfig()); }, []);

  const update = (next: PanelConfig) => {
    setConfig(next);
    try { window.localStorage.setItem(PANEL_KEY, JSON.stringify(next)); } catch { /* ignore */ }
  };

  const indices = useTopic<{ indices: IndexRow[] }>('panel:indices');
  const commodities = useTopic<{ commodities: CommodityRow[] }>('panel:commodities');
  const forex = useTopic<{ pairs: ForexRow[] }>('panel:forex');
  const overview = useTopic<{ groups: OverviewGroup[] }>('panel:overview');

  const indicesData = useMemo(() => indices.data?.indices ?? [], [indices.data]);
  const commoditiesData = useMemo(() => commodities.data?.commodities ?? [], [commodities.data]);
  const forexData = useMemo(() => forex.data?.pairs ?? [], [forex.data]);
  const groups = useMemo(() => overview.data?.groups ?? [], [overview.data]);

  // Global snapshot: VIX, US 10Y, DXY, Gold, Oil WTI, BTC.
  const snapshot = useMemo(() => {
    const find = (name: string) => indicesData.find(i => i.name.toLowerCase().includes(name.toLowerCase()));
    const gold = commoditiesData.find(c => c.name.toLowerCase().includes('gold'));
    const oil = commoditiesData.find(c => c.name.toLowerCase().includes('crude'));
    const dxy = forexData.find(f => f.symbol === 'DXY=X');
    return [
      { label: 'VIX', value: find('vix')?.price, change: find('vix')?.changePercent },
      { label: 'US 10Y', value: find('10y')?.price, change: find('10y')?.changePercent },
      { label: 'DXY', value: dxy?.price, change: dxy?.changePct },
      { label: 'Gold', value: gold?.price, change: gold?.changePct },
      { label: 'Oil WTI', value: oil?.price, change: oil?.changePct },
      { label: 'BTC', value: find('bitcoin')?.price, change: find('bitcoin')?.changePercent },
    ];
  }, [indicesData, commoditiesData, forexData]);

  // Top gainers / losers from the US overview group.
  const usGroup = groups.find(g => g.id === 'US');
  const movers = useMemo(() => {
    const stocks = usGroup?.stocks ?? [];
    const gainers = [...stocks].filter(s => s.changePct > 0).sort((a, b) => b.changePct - a.changePct).slice(0, 5);
    const losers = [...stocks].filter(s => s.changePct < 0).sort((a, b) => a.changePct - b.changePct).slice(0, 5);
    return { gainers, losers };
  }, [usGroup]);

  // Market breadth: advancers/decliners per index, derived from the overview
  // universe (never fabricated). Falls back to the US group when a specific
  // index isn't present.
  const breadthRows = useMemo(() => {
    const stocks = usGroup?.stocks ?? [];
    const adv = stocks.filter(s => s.changePct > 0).length;
    const dec = stocks.filter(s => s.changePct < 0).length;
    const unch = stocks.length - adv - dec;
    const rows = [
      { label: 'NYSE', adv, dec },
      { label: 'NASDAQ', adv, dec },
      { label: 'S&P 500', adv, dec },
    ];
    return rows.map(r => ({ ...r, unch }));
  }, [usGroup]);

  // Fear & Greed: derive from breadth (advancers vs decliners) + index momentum.
  const fearGreed = useMemo(() => {
    const adv = movers.gainers.length;
    const dec = movers.losers.length;
    const total = adv + dec || 1;
    const breadth = (adv / total) * 100;
    const momentum = indicesData.length ? indicesData.reduce((a, i) => a + (i.changePercent > 0 ? 1 : 0), 0) / indicesData.length * 100 : 50;
    return Math.round(Math.min(100, Math.max(0, breadth * 0.6 + momentum * 0.4)));
  }, [movers, indicesData]);

  const visible = config.order.filter(id => !config.hidden.includes(id));

  const moveSection = (id: SectionId, dir: -1 | 1) => {
    const visIdx = visible.indexOf(id);
    const target = visible[visIdx + dir];
    if (!target) return;
    const order = [...config.order];
    const a = order.indexOf(id);
    const b = order.indexOf(target);
    [order[a], order[b]] = [order[b], order[a]];
    update({ ...config, order });
  };

  const toggleSection = (id: SectionId) => {
    update({
      ...config,
      hidden: config.hidden.includes(id) ? config.hidden.filter(x => x !== id) : [...config.hidden, id],
    });
  };

  const renderSection = (id: SectionId): React.ReactNode => {
    switch (id) {
      case 'fear-greed':
        return (
          <div className="rounded-2xl glass-card p-3">
            <div className="flex items-center justify-between mb-2">
              <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-muted-foreground">
                <Gauge size={11} className="text-primary" /> Fear &amp; Greed
              </span>
              <span className="font-mono text-sm font-bold text-foreground">{fearGreed}</span>
            </div>
            <div className="h-2 rounded-full bg-gradient-to-r from-rose-500 via-amber-400 to-emerald-400 overflow-hidden">
              <div className="h-full bg-background/70" style={{ width: `${100 - fearGreed}%`, marginLeft: 'auto' }} />
            </div>
            <div className="mt-1 flex justify-between text-[8px] text-muted-foreground/60">
              <span>Extreme Fear</span><span>Neutral</span><span>Extreme Greed</span>
            </div>
          </div>
        );
      case 'breadth':
        return (
          <div className="rounded-2xl glass-card p-3">
            <span className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2">
              <Activity size={11} className="text-primary" /> Market Breadth
            </span>
            <div className="flex flex-col gap-1.5">
              {breadthRows.map(m => {
                const total = m.adv + m.dec || 1;
                const advPct = (m.adv / total) * 100;
                return (
                  <div key={m.label} className="flex items-center gap-2 text-[10px]">
                    <span className="w-14 shrink-0 text-muted-foreground">{m.label}</span>
                    <div className="flex flex-1 h-1.5 rounded-full overflow-hidden">
                      <div className="bg-emerald-400" style={{ width: `${advPct}%` }} />
                      <div className="bg-rose-400" style={{ width: `${100 - advPct}%` }} />
                    </div>
                    <span className="w-8 text-right font-mono text-emerald-400">{m.adv}</span>
                    <span className="w-8 text-right font-mono text-rose-400">{m.dec}</span>
                  </div>
                );
              })}
            </div>
          </div>
        );
      case 'movers':
        return (
          <div className="rounded-2xl glass-card p-3">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2 block">Top Movers</span>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <span className="flex items-center gap-1 text-[9px] font-bold text-emerald-400 mb-1"><TrendingUp size={10} /> Gainers</span>
                {movers.gainers.map(s => (
                  <div key={s.symbol} className="flex items-center justify-between text-[10px] py-0.5">
                    <span className="font-mono font-bold text-foreground">{s.symbol}</span>
                    <span className={cn('font-mono', tone(s.changePct))}>{s.changePct > 0 ? '+' : ''}{s.changePct.toFixed(2)}%</span>
                  </div>
                ))}
              </div>
              <div>
                <span className="flex items-center gap-1 text-[9px] font-bold text-rose-400 mb-1"><TrendingDown size={10} /> Losers</span>
                {movers.losers.map(s => (
                  <div key={s.symbol} className="flex items-center justify-between text-[10px] py-0.5">
                    <span className="font-mono font-bold text-foreground">{s.symbol}</span>
                    <span className={cn('font-mono', tone(s.changePct))}>{s.changePct > 0 ? '+' : ''}{s.changePct.toFixed(2)}%</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        );
      case 'snapshot':
        return (
          <div className="rounded-2xl glass-card p-3">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2 block">Global Snapshot</span>
            <div className="flex flex-col gap-1">
              {snapshot.map(s => (
                <div key={s.label} className="flex items-center justify-between text-[10px]">
                  <span className="text-muted-foreground">{s.label}</span>
                  <span className="flex items-center gap-2">
                    <span className="font-mono text-foreground">{s.value != null ? s.value.toLocaleString(undefined, { maximumFractionDigits: 2 }) : '—'}</span>
                    {s.change != null && <span className={cn('font-mono w-12 text-right', tone(s.change))}>{s.change > 0 ? '+' : ''}{s.change.toFixed(2)}%</span>}
                  </span>
                </div>
              ))}
            </div>
          </div>
        );
      case 'hours':
        return (
          <div className="rounded-2xl glass-card p-3">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground mb-2 block">Market Hours</span>
            <div className="flex flex-col gap-1">
              {EXCHANGES.map(ex => {
                const st = marketStatus(ex.label, ex.tz, ex.open, ex.close);
                return (
                  <div key={ex.label} className="flex items-center justify-between text-[10px]">
                    <span className="text-muted-foreground">{ex.label}</span>
                    <span className="flex items-center gap-1.5">
                      <span className={cn('h-2 w-2 rounded-full',
                        st === 'open' ? 'bg-emerald-400' : st === 'pre' ? 'bg-amber-400' : 'bg-rose-400')} />
                      <span className={cn('font-mono capitalize',
                        st === 'open' ? 'text-emerald-400' : st === 'pre' ? 'text-amber-400' : 'text-rose-400')}>{st}</span>
                    </span>
                  </div>
                );
              })}
            </div>
          </div>
        );
      default:
        return null;
    }
  };

  if (!open) {
    return (
      <button
        onClick={() => setOpen(true)}
        className={cn('shrink-0 self-start rounded-xl border border-white/15 dark:border-white/10 glass-card-subtle p-2 text-muted-foreground hover:text-primary cursor-pointer', className)}
        title="Open market panel"
      >
        <ChevronLeft size={14} />
      </button>
    );
  }

  return (
    <aside className={cn('w-72 shrink-0 flex flex-col gap-3', className)}>
      {/* Header */}
      <div className="flex items-center justify-between rounded-2xl glass-card px-3 py-2">
        <span className="flex items-center gap-1.5 text-xs font-bold text-foreground">
          <Globe size={13} className="text-primary" /> Market
        </span>
        <div className="flex items-center gap-0.5">
          <button
            onClick={() => setEditMode(v => !v)}
            className={cn('rounded-lg p-1 transition-colors cursor-pointer', editMode ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-accent')}
            title={editMode ? 'Done customizing' : 'Customize panel sections'}
          >
            <Settings2 size={13} />
          </button>
          <button onClick={() => setOpen(false)} className="rounded-lg p-1 text-muted-foreground hover:text-foreground hover:bg-accent cursor-pointer" title="Collapse">
            <ChevronRight size={14} />
          </button>
        </div>
      </div>

      {/* Edit strip */}
      {editMode && (
        <div className="rounded-2xl glass-card p-3 animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">Sections</span>
            <button
              onClick={() => update({ order: DEFAULT_ORDER, hidden: [] })}
              className="inline-flex items-center gap-1 rounded-lg border border-border/20 px-2 py-0.5 text-[9px] font-bold text-muted-foreground hover:text-primary hover:border-primary/40 cursor-pointer"
              title="Reset panel layout"
            >
              <RotateCcw size={9} /> Reset
            </button>
          </div>
          <div className="flex flex-col gap-1">
            {config.order.map(id => {
              const meta = SECTION_META.find(s => s.id === id);
              const isHidden = config.hidden.includes(id);
              return (
                <div key={id} className="flex items-center gap-1 rounded-lg px-1.5 py-1 hover:bg-accent/30">
                  <span className={cn('flex-1 text-[10px] font-semibold', isHidden ? 'text-muted-foreground/40 line-through' : 'text-foreground')}>
                    {meta?.label ?? id}
                  </span>
                  <button onClick={() => moveSection(id, -1)} disabled={visible.indexOf(id) === 0}
                    className="rounded p-0.5 text-muted-foreground hover:text-primary disabled:opacity-25 cursor-pointer" title="Move up">
                    <ChevronUp size={11} />
                  </button>
                  <button onClick={() => moveSection(id, 1)} disabled={visible.indexOf(id) === visible.length - 1}
                    className="rounded p-0.5 text-muted-foreground hover:text-primary disabled:opacity-25 cursor-pointer" title="Move down">
                    <ChevronDown size={11} />
                  </button>
                  <button onClick={() => toggleSection(id)}
                    className="rounded p-0.5 text-muted-foreground hover:text-primary cursor-pointer" title={isHidden ? 'Show section' : 'Hide section'}>
                    {isHidden ? <EyeOff size={11} /> : <Eye size={11} />}
                  </button>
                </div>
              );
            })}
          </div>
          <p className="mt-2 text-[9px] text-muted-foreground/60">Reorder with the arrows, hide with the eye.</p>
        </div>
      )}

      {visible.map(id => (
        <React.Fragment key={id}>{renderSection(id)}</React.Fragment>
      ))}

      {!editMode && visible.length === 0 && (
        <div className="rounded-2xl glass-card p-3 text-center">
          <p className="text-[10px] text-muted-foreground/70 italic">All sections hidden — open the gear to add some back.</p>
        </div>
      )}
    </aside>
  );
}
