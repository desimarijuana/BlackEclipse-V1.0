'use client';

// ── Chart Widget — the top-level chart surface ────────────────────────────────
// Owns the provider lifecycle, the toolbar (symbol / timeframe / chart type /
// provider), and data fetching. It talks ONLY to the ChartProvider contract —
// it never depends on Eclipse or TradingView internals. Switching providers
// preserves shared state (symbol, timeframe, chart type).

import React, { useEffect, useRef, useState } from 'react';
import { Search, RefreshCw, ChevronDown, LineChart, X, PenTool, MousePointer2, Undo2, Redo2, Trash2, Lock, Eye, EyeOff } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useCommandStore } from '@/lib/search/store';
import { createChartProvider } from '@/lib/chart/providers';
import { useChartData } from '@/lib/chart/use-chart-data';
import { getAllIndicators } from '@/lib/chart/indicators/registry';
import { getAllDrawingDefs } from '@/lib/chart/drawings/tools';
import { DrawingManager } from '@/lib/chart/drawings/manager';
import { DrawingController } from '@/lib/chart/drawings/controller';
import { DrawingOverlay } from '@/components/chart/drawing-overlay';
import type { EclipseChartProvider } from '@/lib/chart/providers/eclipse-provider';
import {
  CHART_TYPES, TIMEFRAMES, defaultChartState,
  type ChartDrawing, type ChartIndicatorConfig, type ChartProvider, type ChartProviderId, type ChartState, type ChartType, type DrawingToolMode, type Timeframe,
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

  // ── Drawing system ────────────────────────────────────────────────────────
  const [drawingManager] = useState(() => {
    const saved = loadSavedDrawings(symbol ?? 'AAPL');
    return new DrawingManager(saved);
  });
  const [drawingController] = useState(() => new DrawingController(drawingManager));
  const [tool, setTool] = useState<DrawingToolMode>('cursor');
  const [, forceRender] = useState(0);

  // Keep the manager in sync with external state changes (symbol/timeframe
  // switch). On mount, the manager already holds the persisted drawings, so we
  // only restore when the symbol actually changes.
  const prevSymbolRef = useRef(chartState.symbol);
  useEffect(() => {
    if (prevSymbolRef.current !== chartState.symbol) {
      drawingManager.restore(loadSavedDrawings(chartState.symbol));
      prevSymbolRef.current = chartState.symbol;
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartState.symbol]);

  // Persist drawing changes back to chart state + localStorage.
  useEffect(() => {
    const unsub = drawingManager.subscribe(() => {
      const drawings = drawingManager.serialize();
      setState({ ...chartState, drawings });
      saveDrawings(chartState.symbol, drawings);
      forceRender((n) => n + 1);
    });
    return unsub;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartState]);

  // Keyboard shortcuts: Escape cancels, Delete removes, Ctrl+Z undo, Ctrl+Shift+Z redo.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        drawingController.cancel();
        setTool('cursor');
      } else if (e.key === 'Delete' || e.key === 'Backspace') {
        const sel = drawingManager.getSelected();
        if (sel) drawingManager.delete(sel.id);
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') {
        e.preventDefault();
        if (e.shiftKey) drawingManager.redo();
        else drawingManager.undo();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [drawingManager, drawingController]);

  const selectTool = (t: DrawingToolMode) => {
    drawingController.setTool(t);
    setTool(t);
  };

  const getChart = () => {
    const p = providerRef.current as EclipseChartProvider | null;
    return p?.getEChartsInstance?.() ?? null;
  };

  const openSearch = () => useCommandStore.getState().setOpen(true);

  return (
    <div className={cn('flex h-full w-full flex-col gap-2', className)} style={{ minHeight: 400 }}>
      <ChartToolbar
        state={chartState}
        loading={loading}
        tool={tool}
        onTool={selectTool}
        onProvider={setProvider}
        onTimeframe={setTimeframe}
        onChartType={setChartType}
        onSymbol={setSymbol}
        onSearch={openSearch}
        onRefresh={refresh}
        onAddIndicator={addIndicator}
        onRemoveIndicator={removeIndicator}
        manager={drawingManager}
      />

      <div className="relative min-h-0 flex-1 overflow-hidden rounded-2xl border border-border/10 glass-card-subtle">
        <div ref={containerRef} className="absolute inset-0" />
        <DrawingOverlay getChart={getChart} manager={drawingManager} controller={drawingController} tool={tool} />
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
  state, loading, tool, onTool, onProvider, onTimeframe, onChartType, onSymbol, onSearch, onRefresh,
  onAddIndicator, onRemoveIndicator, manager,
}: {
  state: ChartState;
  loading: boolean;
  tool: DrawingToolMode;
  onTool: (t: DrawingToolMode) => void;
  onProvider: (p: ChartProviderId) => void;
  onTimeframe: (t: Timeframe) => void;
  onChartType: (t: ChartType) => void;
  onSymbol: (s: string) => void;
  onSearch: () => void;
  onRefresh: () => void;
  onAddIndicator: (config: ChartIndicatorConfig) => void;
  onRemoveIndicator: (id: string) => void;
  manager: DrawingManager;
}) {
  const [symbolInput, setSymbolInput] = useState(state.symbol);
  useEffect(() => setSymbolInput(state.symbol), [state.symbol]);

  return (
    <div className="relative z-20 flex flex-wrap items-center gap-1.5 rounded-2xl border border-border/10 glass-card-subtle px-2 py-1.5">
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

      {/* Drawing tools */}
      <DrawingToolbar tool={tool} onTool={onTool} manager={manager} />

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

// ── Drawing toolbar ─────────────────────────────────────────────────────────

const TOOL_GROUPS: Array<{ label: string; tools: DrawingToolMode[] }> = [
  { label: 'Cursor', tools: ['cursor'] },
  { label: 'Lines', tools: ['trendline', 'ray', 'horizontal', 'vertical'] },
  { label: 'Shapes', tools: ['rectangle', 'text', 'arrow'] },
  { label: 'Analysis', tools: ['fibonacci', 'measure', 'long-position', 'short-position'] },
];

function DrawingToolbar({
  tool, onTool, manager,
}: {
  tool: DrawingToolMode;
  onTool: (t: DrawingToolMode) => void;
  manager: DrawingManager;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const defs = getAllDrawingDefs();
  const [, force] = useState(0);

  useEffect(() => {
    const unsub = manager.subscribe(() => force((n) => n + 1));
    return unsub;
  }, [manager]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const selected = manager.getSelected();
  const defName = (t: DrawingToolMode) => (t === 'cursor' ? 'Cursor' : defs.find((d) => d.type === t)?.name ?? t);

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className={cn(
          'inline-flex items-center gap-1 rounded-lg px-2 py-1 text-[10px] font-bold transition-colors cursor-pointer',
          tool !== 'cursor' ? 'bg-primary/20 text-primary' : 'bg-accent/40 text-muted-foreground hover:text-foreground hover:bg-accent/70'
        )}
      >
        <PenTool size={12} /> {defName(tool)}
        <ChevronDown size={12} className={cn('transition-transform', open && 'rotate-180')} />
      </button>
      {open && (
        <div className="absolute left-0 top-full z-50 mt-1.5 w-64 rounded-xl border border-border/40 glass-card-strong p-1.5 shadow-2xl">
          {TOOL_GROUPS.map((group) => (
            <div key={group.label} className="mb-1">
              <div className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">{group.label}</div>
              <div className="grid grid-cols-2 gap-1">
                {group.tools.map((t) => (
                  <button
                    key={t}
                    onClick={() => { onTool(t); setOpen(false); }}
                    className={cn(
                      'flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-left transition-colors cursor-pointer',
                      tool === t ? 'bg-primary/15 text-primary' : 'hover:bg-accent/40'
                    )}
                  >
                    <MousePointer2 size={11} className="text-muted-foreground" />
                    <span className="text-[10px] font-semibold text-foreground">{defName(t)}</span>
                  </button>
                ))}
              </div>
            </div>
          ))}
          <div className="mt-1 border-t border-border/10 pt-1.5">
            <div className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Manage</div>
            <div className="flex items-center gap-1 px-1">
              <button
                onClick={() => manager.undo()}
                disabled={!manager.canUndo()}
                title="Undo (Ctrl+Z)"
                className="rounded-lg p-1.5 text-muted-foreground hover:text-primary disabled:opacity-30 cursor-pointer"
              ><Undo2 size={13} /></button>
              <button
                onClick={() => manager.redo()}
                disabled={!manager.canRedo()}
                title="Redo (Ctrl+Shift+Z)"
                className="rounded-lg p-1.5 text-muted-foreground hover:text-primary disabled:opacity-30 cursor-pointer"
              ><Redo2 size={13} /></button>
              <button
                onClick={() => selected && manager.delete(selected.id)}
                disabled={!selected}
                title="Delete selected (Del)"
                className="rounded-lg p-1.5 text-muted-foreground hover:text-rose-400 disabled:opacity-30 cursor-pointer"
              ><Trash2 size={13} /></button>
              <button
                onClick={() => selected && manager.setLocked(selected.id, !selected.locked)}
                disabled={!selected}
                title="Lock/unlock"
                className="rounded-lg p-1.5 text-muted-foreground hover:text-primary disabled:opacity-30 cursor-pointer"
              ><Lock size={13} /></button>
              <button
                onClick={() => selected && manager.setVisible(selected.id, !selected.visible)}
                disabled={!selected}
                title="Show/hide"
                className="rounded-lg p-1.5 text-muted-foreground hover:text-primary disabled:opacity-30 cursor-pointer"
              >{selected?.visible ? <Eye size={13} /> : <EyeOff size={13} />}</button>
            </div>
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

// ── Drawing persistence helpers ────────────────────────────────────────────────

const DRAWINGS_KEY = 'be_chart_drawings';

function loadSavedDrawings(symbol: string): ChartDrawing[] {
  try {
    const raw = localStorage.getItem(DRAWINGS_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as Record<string, ChartDrawing[]>;
    return parsed[symbol] ?? [];
  } catch {
    return [];
  }
}

function saveDrawings(symbol: string, drawings: ChartDrawing[]): void {
  try {
    const raw = localStorage.getItem(DRAWINGS_KEY);
    const all = raw ? (JSON.parse(raw) as Record<string, ChartDrawing[]>) : {};
    all[symbol] = drawings;
    localStorage.setItem(DRAWINGS_KEY, JSON.stringify(all));
  } catch {
    /* ignore quota */
  }
}
