'use client';

// ── Chart Widget — the top-level chart surface ────────────────────────────────
// Owns the provider lifecycle, the toolbar (symbol / timeframe / chart type /
// provider), and data fetching. It talks ONLY to the ChartProvider contract —
// it never depends on Eclipse or TradingView internals. Switching providers
// preserves shared state (symbol, timeframe, chart type).

import React, { useEffect, useRef, useState } from 'react';
import { Search, RefreshCw, ChevronDown, LineChart, X, PenTool, MousePointer2 } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useCommandStore } from '@/lib/search/store';
import { createChartProvider } from '@/lib/chart/providers';
import { useChartData } from '@/lib/chart/use-chart-data';
import { getAllIndicators } from '@/lib/chart/indicators/registry';
import { getAllDrawingDefs, createDrawing } from '@/lib/chart/drawings/registry';
import {
  CHART_TYPES, TIMEFRAMES, defaultChartState,
  type ChartDrawing, type ChartIndicatorConfig, type ChartPoint, type ChartProvider, type ChartProviderId, type ChartState, type ChartType, type DrawingType, type Timeframe,
} from '@/lib/chart/types';

interface ChartWidgetProps {
  symbol?: string;
  market?: string;
  className?: string;
  /** Optional external state control (e.g. from a dashboard widget). */
  state?: ChartState;
  onStateChange?: (state: ChartState) => void;
}

export function ChartWidget({ symbol, market, className, state, onStateChange }: ChartWidgetProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const providerRef = useRef<ChartProvider | null>(null);

  // Internal state (overridable via props for controlled usage).
  const [internal, setInternal] = useState<ChartState>(() =>
    defaultChartState({ symbol: symbol ?? 'AAPL', market: market ?? 'US' })
  );
  const chartState = state ?? internal;
  const setState = (next: ChartState) => {
    if (onStateChange) onStateChange(next);
    else setInternal(next);
  };

  const { data, loading, error, refresh } = useChartData(
    chartState.symbol,
    chartState.market,
    chartState.timeframe
  );

  // Create/destroy the provider when the provider id changes.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const provider = createChartProvider(chartState.provider, chartState);
    providerRef.current = provider;
    provider.initialize(el);
    // Push any already-loaded data into the freshly created provider.
    if (data) provider.setData(data);
    return () => {
      provider.destroy();
      providerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartState.provider]);

  // Push data into the provider whenever it changes.
  useEffect(() => {
    if (data) providerRef.current?.setData(data);
  }, [data]);

  // Keep the provider's symbol/timeframe/chartType in sync with state.
  useEffect(() => {
    providerRef.current?.setSymbol(chartState.symbol, chartState.market);
  }, [chartState.symbol, chartState.market]);
  useEffect(() => {
    providerRef.current?.setTimeframe(chartState.timeframe);
  }, [chartState.timeframe]);
  useEffect(() => {
    providerRef.current?.setChartType(chartState.chartType);
  }, [chartState.chartType]);

  // Reconcile indicators with the provider (add/remove as state changes).
  useEffect(() => {
    const provider = providerRef.current;
    if (!provider) return;
    const active = new Set(chartState.indicators.map((i) => i.id));
    const current = provider.getState().indicators.map((i) => i.id);
    for (const id of current) if (!active.has(id)) provider.removeIndicator(id);
    for (const cfg of chartState.indicators) provider.addIndicator(cfg);
  }, [chartState.indicators]);

  const setProvider = (provider: ChartProviderId) => setState({ ...chartState, provider });
  const setTimeframe = (timeframe: Timeframe) => setState({ ...chartState, timeframe });
  const setChartType = (chartType: ChartType) => setState({ ...chartState, chartType });
  const setSymbol = (sym: string) => setState({ ...chartState, symbol: sym.toUpperCase() });

  const addIndicator = (config: ChartIndicatorConfig) => {
    if (chartState.indicators.some((i) => i.id === config.id)) return;
    setState({ ...chartState, indicators: [...chartState.indicators, config] });
  };
  const removeIndicator = (id: string) => {
    setState({ ...chartState, indicators: chartState.indicators.filter((i) => i.id !== id) });
  };

  const addDrawing = (drawing: ChartDrawing) => {
    setState({ ...chartState, drawings: [...chartState.drawings, drawing] });
  };
  const removeDrawing = (id: string) => {
    setState({ ...chartState, drawings: chartState.drawings.filter((d) => d.id !== id) });
  };

  const openSearch = () => useCommandStore.getState().setOpen(true);

  return (
    <div className={cn('flex h-full w-full flex-col gap-2', className)} style={{ minHeight: 400 }}>
      <ChartToolbar
        state={chartState}
        loading={loading}
        onProvider={setProvider}
        onTimeframe={setTimeframe}
        onChartType={setChartType}
        onSymbol={setSymbol}
        onSearch={openSearch}
        onRefresh={refresh}
        onAddIndicator={addIndicator}
        onRemoveIndicator={removeIndicator}
        onAddDrawing={addDrawing}
        onRemoveDrawing={removeDrawing}
      />

      <div className="relative min-h-0 flex-1 overflow-hidden rounded-2xl border border-border/10 glass-card-subtle">
        <div ref={containerRef} className="absolute inset-0" />
        {loading && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <span className="text-[11px] font-mono text-muted-foreground/70 animate-pulse">Loading {chartState.symbol}…</span>
          </div>
        )}
        {error && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <span className="text-[11px] font-mono text-rose-400/80">{error}</span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Toolbar ───────────────────────────────────────────────────────────────────

function ChartToolbar({
  state, loading, onProvider, onTimeframe, onChartType, onSymbol, onSearch, onRefresh,
  onAddIndicator, onRemoveIndicator, onAddDrawing, onRemoveDrawing,
}: {
  state: ChartState;
  loading: boolean;
  onProvider: (p: ChartProviderId) => void;
  onTimeframe: (t: Timeframe) => void;
  onChartType: (t: ChartType) => void;
  onSymbol: (s: string) => void;
  onSearch: () => void;
  onRefresh: () => void;
  onAddIndicator: (config: ChartIndicatorConfig) => void;
  onRemoveIndicator: (id: string) => void;
  onAddDrawing: (drawing: ChartDrawing) => void;
  onRemoveDrawing: (id: string) => void;
}) {
  const [symbolInput, setSymbolInput] = useState(state.symbol);
  useEffect(() => setSymbolInput(state.symbol), [state.symbol]);

  return (
    <div className="flex flex-wrap items-center gap-1.5 rounded-2xl border border-border/10 glass-card-subtle px-2 py-1.5">
      {/* Symbol */}
      <div className="flex items-center gap-1">
        <button
          onClick={onSearch}
          title="Search symbol (/)"
          className="inline-flex items-center gap-1 rounded-lg bg-accent/40 px-2 py-1 text-[11px] font-bold text-foreground hover:bg-accent/70 transition-colors cursor-pointer"
        >
          <Search size={12} />
          <input
            value={symbolInput}
            onChange={(e) => setSymbolInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') onSymbol(symbolInput);
            }}
            onBlur={() => onSymbol(symbolInput)}
            className="w-20 bg-transparent font-mono text-[11px] font-bold text-foreground outline-none placeholder:text-muted-foreground/50"
            placeholder="Symbol"
            spellCheck={false}
          />
        </button>
      </div>

      {/* Timeframe */}
      <div className="flex items-center gap-0.5 rounded-lg bg-accent/30 p-0.5">
        {TIMEFRAMES.map((tf) => (
          <button
            key={tf}
            onClick={() => onTimeframe(tf)}
            className={cn(
              'rounded-md px-1.5 py-0.5 text-[10px] font-bold transition-colors cursor-pointer',
              tf === state.timeframe ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {tf}
          </button>
        ))}
      </div>

      {/* Chart type */}
      <div className="flex items-center gap-0.5 rounded-lg bg-accent/30 p-0.5">
        {CHART_TYPES.map((ct) => (
          <button
            key={ct}
            onClick={() => onChartType(ct)}
            className={cn(
              'rounded-md px-1.5 py-0.5 text-[10px] font-bold capitalize transition-colors cursor-pointer',
              ct === state.chartType ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:text-foreground'
            )}
          >
            {ct === 'candlestick' ? 'Candle' : ct}
          </button>
        ))}
      </div>

      {/* Indicators */}
      <IndicatorMenu
        active={state.indicators}
        onAdd={onAddIndicator}
        onRemove={onRemoveIndicator}
      />

      {/* Drawings */}
      <DrawingMenu
        active={state.drawings}
        onAdd={onAddDrawing}
        onRemove={onRemoveDrawing}
      />

      <div className="flex-1" />

      {/* Provider selector */}
      <div className="relative">
        <ProviderDropdown value={state.provider} onChange={onProvider} />
      </div>

      {/* Refresh */}
      <button
        onClick={onRefresh}
        title="Refresh data"
        className="inline-flex items-center gap-1 rounded-lg bg-accent/40 px-2 py-1 text-[10px] font-bold text-muted-foreground hover:text-foreground hover:bg-accent/70 transition-colors cursor-pointer"
      >
        <RefreshCw size={12} className={cn(loading && 'animate-spin')} />
      </button>
    </div>
  );
}

// ── Indicator menu ───────────────────────────────────────────────────────────

function IndicatorMenu({
  active, onAdd, onRemove,
}: {
  active: ChartIndicatorConfig[];
  onAdd: (config: ChartIndicatorConfig) => void;
  onRemove: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const indicators = getAllIndicators();

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const add = (id: string) => {
    const def = indicators.find((i) => i.id === id);
    if (!def) return;
    const settings: Record<string, number | string | boolean> = {};
    for (const input of def.inputs) settings[input.key] = input.default;
    onAdd({ id, settings });
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-bold transition-colors cursor-pointer',
          active.length > 0 ? 'bg-primary/20 text-primary' : 'bg-accent/40 text-muted-foreground hover:text-foreground hover:bg-accent/70'
        )}
      >
        <LineChart size={12} /> Indicators {active.length > 0 && `(${active.length})`}
        <ChevronDown size={12} className={cn('transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="absolute left-0 top-full z-50 mt-1.5 w-64 rounded-xl border border-border/40 glass-card-strong p-1.5 shadow-2xl">
          <div className="px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Active</div>
          {active.length === 0 && (
            <div className="px-2 py-1 text-[10px] text-muted-foreground/60 italic">No indicators added</div>
          )}
          {active.map((cfg) => {
            const def = indicators.find((i) => i.id === cfg.id);
            return (
              <div key={cfg.id} className="flex items-center justify-between rounded-lg px-2 py-1 hover:bg-accent/40">
                <span className="text-[11px] font-semibold text-foreground">{def?.name ?? cfg.id}</span>
                <button
                  onClick={() => onRemove(cfg.id)}
                  className="rounded p-0.5 text-muted-foreground hover:text-rose-400 transition-colors cursor-pointer"
                  title="Remove"
                >
                  <X size={12} />
                </button>
              </div>
            );
          })}
          <div className="mt-1 border-t border-border/10 pt-1.5 px-2 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Add</div>
          <div className="max-h-56 overflow-y-auto">
            {indicators.map((def) => (
              <button
                key={def.id}
                onClick={() => add(def.id)}
                disabled={active.some((a) => a.id === def.id)}
                className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left hover:bg-accent/40 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed"
              >
                <span>
                  <span className="block text-[11px] font-semibold text-foreground">{def.name}</span>
                  <span className="block text-[9px] text-muted-foreground">{def.description}</span>
                </span>
                <span className="ml-2 rounded bg-accent/40 px-1.5 py-0.5 text-[8px] font-bold uppercase text-muted-foreground">{def.category}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Drawing menu ─────────────────────────────────────────────────────────────

function DrawingMenu({
  active, onAdd, onRemove,
}: {
  active: ChartDrawing[];
  onAdd: (drawing: ChartDrawing) => void;
  onRemove: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const defs = getAllDrawingDefs();

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const add = (type: DrawingType) => {
    const def = defs.find((d) => d.type === type);
    if (!def) return;
    // Place a default drawing at the last visible area (approximate).
    const points: ChartPoint[] = [];
    for (let i = 0; i < def.points; i++) {
      points.push({ x: 10 + i * 5, y: 100 - i * 10 });
    }
    onAdd(createDrawing(type, points));
  };

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-bold transition-colors cursor-pointer',
          active.length > 0 ? 'bg-primary/20 text-primary' : 'bg-accent/40 text-muted-foreground hover:text-foreground hover:bg-accent/70'
        )}
      >
        <PenTool size={12} /> Draw {active.length > 0 && `(${active.length})`}
        <ChevronDown size={12} className={cn('transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="absolute left-0 top-full z-50 mt-1.5 w-56 rounded-xl border border-border/40 glass-card-strong p-1.5 shadow-2xl">
          <div className="px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Active</div>
          {active.length === 0 && (
            <div className="px-2 py-1 text-[10px] text-muted-foreground/60 italic">No drawings</div>
          )}
          {active.map((d) => {
            const def = defs.find((x) => x.type === d.type);
            return (
              <div key={d.id} className="flex items-center justify-between rounded-lg px-2 py-1 hover:bg-accent/40">
                <span className="text-[11px] font-semibold text-foreground">{def?.name ?? d.type}</span>
                <button
                  onClick={() => onRemove(d.id)}
                  className="rounded p-0.5 text-muted-foreground hover:text-rose-400 transition-colors cursor-pointer"
                  title="Remove"
                >
                  <X size={12} />
                </button>
              </div>
            );
          })}
          <div className="mt-1 border-t border-border/10 pt-1.5 px-2 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Tools</div>
          <div className="grid grid-cols-2 gap-1">
            {defs.map((def) => (
              <button
                key={def.type}
                onClick={() => add(def.type)}
                className="flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-left hover:bg-accent/40 transition-colors cursor-pointer"
              >
                <MousePointer2 size={11} className="text-muted-foreground" />
                <span className="text-[10px] font-semibold text-foreground">{def.name}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

// ── Provider dropdown ─────────────────────────────────────────────────────────

function ProviderDropdown({ value, onChange }: { value: ChartProviderId; onChange: (p: ChartProviderId) => void }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const options: Array<{ id: ChartProviderId; label: string; desc: string }> = [
    { id: 'eclipse', label: 'Eclipse Chart', desc: 'Native BlackEclipse engine' },
    { id: 'tradingview', label: 'TradingView', desc: 'TradingView advanced chart' },
  ];

  const current = options.find((o) => o.id === value)!;

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-1.5 rounded-lg border border-border/40 bg-accent/40 px-2.5 py-1 text-[11px] font-bold text-foreground hover:bg-accent/70 transition-colors cursor-pointer"
      >
        <span className={cn('text-[10px]', value === 'eclipse' ? 'text-emerald-400' : 'text-rose-400')}>●</span> {current.label}
        <ChevronDown size={12} className={cn('transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="absolute right-0 top-full z-50 mt-1.5 w-56 rounded-xl border border-border/40 glass-card-strong p-1 shadow-2xl">
          {options.map((o) => (
            <button
              key={o.id}
              onClick={() => { onChange(o.id); setOpen(false); }}
              className={cn(
                'flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left transition-colors cursor-pointer',
                o.id === value ? 'bg-primary/15' : 'hover:bg-accent/50'
              )}
            >
              <span className={cn('mt-0.5 text-[10px]', o.id === 'eclipse' ? 'text-emerald-400' : 'text-rose-400')}>●</span>
              <span>
                <span className="block text-[11px] font-bold text-foreground">{o.label}</span>
                <span className="block text-[9px] text-muted-foreground">{o.desc}</span>
              </span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
