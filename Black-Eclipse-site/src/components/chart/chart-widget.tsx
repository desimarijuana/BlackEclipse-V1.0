'use client';

// ── Chart Widget — the top-level chart surface ────────────────────────────────
// Owns the provider lifecycle, the toolbar (symbol / timeframe / chart type /
// provider), and data fetching. It talks ONLY to the ChartProvider contract —
// it never depends on Eclipse or TradingView internals. Switching providers
// preserves shared state (symbol, timeframe, chart type).

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Search, SearchX, RefreshCw, LineChart, X, PenTool, MousePointer2, Undo2, Redo2, Trash2, Lock, Eye, EyeOff, ZoomIn, ZoomOut, Maximize2, ChevronLeft, ChevronRight, Plus,
  TrendingUp, TrendingDown, Minus, MoveVertical, Square, GitBranch, Type, ArrowUpRight, Ruler, MoveDiagonal, ArrowLeftRight, Spline, Waypoints, Pipette,
  type LucideIcon,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { canHandleKeyboardEvent, matchesShortcut } from '@/lib/keyboard';
import { getChartPalette, useChartPalette } from '@/lib/chart-palette-store';
import { useCommandStore } from '@/lib/search/store';
import { createChartProvider } from '@/lib/chart/providers';
import { useChartData } from '@/lib/chart/use-chart-data';
import { useCompareData } from '@/lib/chart/use-compare-data';
import { useLiveQuote } from '@/lib/chart/subscription-manager';
import { getAllIndicators } from '@/lib/chart/indicators/registry';
import { getAllDrawingDefs } from '@/lib/chart/drawings/tools';
import { DrawingManager } from '@/lib/chart/drawings/manager';
import { DrawingController } from '@/lib/chart/drawings/controller';
import { DrawingOverlay } from '@/components/chart/drawing-overlay';
import { ToolbarMenu } from '@/components/chart/toolbar-menu';
import type { EclipseChartProvider } from '@/lib/chart/providers/eclipse-provider';
import {
  CHART_TYPES, TIMEFRAMES, defaultChartState,
  type ChartDrawing, type ChartIndicatorConfig, type ChartProvider, type ChartProviderId, type ChartState, type ChartType, type DrawingToolMode, type Timeframe, type ChartCompareItem, type ChartCompareSeries,
} from '@/lib/chart/types';

interface ChartWidgetProps {
  symbol?: string;
  market?: string;
  className?: string;
  /** Optional external state control (e.g. from a dashboard widget). */
  state?: ChartState;
  onStateChange?: (state: ChartState) => void;
  /** Dense mode: tighter chrome for small multi-chart panels. */
  compact?: boolean;
  /** Hide the header toolbar entirely (the panel renders its own). */
  hideToolbar?: boolean;
  /** Hide the bottom price footer. */
  hideFooter?: boolean;
  /** Controlled drawing tool (when hosted in a chart panel toolbar). */
  tool?: DrawingToolMode;
  onToolChange?: (tool: DrawingToolMode) => void;
  /** Crosshair move callback (timestamp ms) — linked charts. */
  onCrosshair?: (time: number | null) => void;
  /** Visible-range callback (0–100 %) — linked range. */
  onRange?: (range: { start: number; end: number }) => void;
  /** External crosshair target (timestamp ms) from a linked peer. */
  crosshairTime?: number | null;
  /** External range from a linked peer. */
  range?: { start: number; end: number } | null;
  /**
   * Called with the live provider whenever it is (re)created / destroyed. Lets
   * hosts (e.g. linked chart panels) apply crosshair/range updates imperatively
   * without routing high-frequency events through React state.
   */
  onProviderReady?: (provider: ChartProvider | null) => void;
}

/** Live quote snapshot shown in the chart footer + fed to the last-price line. */
interface LiveQuote {
  price: number;
  changePercent: number;
  currency: string;
  updatedAt: string | null;
  at: number;
}

/** Refresh cadence options for the live price. */
const REFRESH_OPTIONS: Array<{ label: string; ms: number }> = [
  { label: '30s', ms: 30_000 },
  { label: '1m', ms: 60_000 },
  { label: '5m', ms: 300_000 },
  { label: '15m', ms: 900_000 },
  { label: 'Off', ms: 0 },
];

/** Duration of one candle per timeframe (intraday only; daily+ handled separately). */
const CANDLE_MS: Partial<Record<Timeframe, number>> = {
  '1m': 60_000,
  '3m': 180_000,
  '5m': 300_000,
  '15m': 900_000,
  '30m': 1_800_000,
  '1H': 3_600_000,
  '2H': 7_200_000,
  '4H': 14_400_000,
};

/** Crypto trades 24/7; everything else follows (approximate) market sessions. */
function isCryptoMarket(market: string, symbol: string): boolean {
  return /CRYPTO/i.test(market) || /-USD$/i.test(symbol) || /USDT$/i.test(symbol);
}

/**
 * Epoch ms when the currently-forming candle closes, plus a human label.
 * Intraday timeframes snap to their interval boundary; 1D/1W/1M roll to the
 * next session/day/week/month boundary.
 */
function nextCandleAt(timeframe: Timeframe, symbol: string, market: string, now: Date): { at: number; label: string } {
  const ms = CANDLE_MS[timeframe];
  if (ms) {
    return { at: Math.ceil(now.getTime() / ms) * ms, label: `${timeframe} candle` };
  }
  const d = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  if (timeframe === '1D') {
    d.setUTCDate(d.getUTCDate() + 1);
    return { at: d.getTime(), label: 'daily close' };
  }
  if (timeframe === '1W') {
    const day = d.getUTCDay();
    d.setUTCDate(d.getUTCDate() + (day === 0 ? 1 : 8 - day));
    return { at: d.getTime(), label: 'weekly close' };
  }
  d.setUTCMonth(d.getUTCMonth() + 1, 1);
  return { at: d.getTime(), label: 'monthly close' };
}

/** Compact countdown: "MM:SS", "H:MM:SS", or "2d 4h". */
function formatCountdown(msLeft: number): string {
  const s = Math.max(0, Math.floor(msLeft / 1000));
  if (s < 3600) {
    const m = Math.floor(s / 60);
    return `${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  }
  if (s < 86400) {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    return `${h}:${String(m).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
  }
  const d = Math.floor(s / 86400);
  const h = Math.floor((s % 86400) / 3600);
  return `${d}d ${h}h`;
}

/** Live next-candle countdown state, ticking every second. */
function useCandleCountdown(timeframe: Timeframe, symbol: string, market: string) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);
  const candle = useMemo(
    () => nextCandleAt(timeframe, symbol, market, new Date(now)),
    [timeframe, symbol, market, now],
  );
  const crypto = isCryptoMarket(market, symbol);
  const closedMarket = !crypto && (timeframe === '1D' || timeframe === '1W' || timeframe === '1M')
    && (new Date(now).getUTCDay() === 6 || new Date(now).getUTCDay() === 0);
  return { candle, candleLeft: candle.at - now, closedMarket };
}

export function ChartWidget({
  symbol, market, className, state, onStateChange,
  compact = false, hideToolbar = false, hideFooter = false,
  tool: controlledTool, onToolChange,
  onCrosshair, onRange, crosshairTime, range, onProviderReady,
}: ChartWidgetProps) {
  const rootRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const providerRef = useRef<ChartProvider | null>(null);
  const livePriceRef = useRef<number | null>(null);

  // Internal state (overridable via props for controlled usage).
  const [internal, setInternal] = useState<ChartState>(() =>
    defaultChartState({ symbol: symbol ?? 'AAPL', market: market ?? 'US' })
  );
  const chartState = state ?? internal;
  // Persisted/templated state may predate the compare field.
  const compareList = chartState.compare ?? [];
  const setState = (next: ChartState) => {
    if (onStateChange) onStateChange(next);
    else setInternal(next);
  };

  // Reconcile the `symbol` / `market` props into internal state. The widget
  // initialises `internal` once, so without this a host that passes only
  // `symbol` (the chart tab, the search palette) would update its own state and
  // see nothing change — the chart kept rendering whatever it mounted with.
  // Only the uncontrolled path writes back, so a controlled `state=` host keeps
  // sole ownership. A caller-supplied market wins over the home market.
  useEffect(() => {
    if (state) return; // controlled — the host owns the state
    if (symbol == null && market == null) return;
    setInternal((prev) => {
      const nextSymbol = symbol != null ? symbol.toUpperCase() : prev.symbol;
      const nextMarket = market != null ? market : prev.market;
      if (nextSymbol === prev.symbol && nextMarket === prev.market) return prev;
      return { ...prev, symbol: nextSymbol, market: nextMarket };
    });
  }, [symbol, market, state]);

  const { data, loading, error, refresh } = useChartData(
    chartState.symbol,
    chartState.market,
    chartState.timeframe
  );

  // Compare overlays — fetched/rebasal against the primary bars.
  const compareSeries = useCompareData(data, compareList, chartState.timeframe);

  // Create/destroy the provider when the provider id changes.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const provider = createChartProvider(chartState.provider, chartState);
    providerRef.current = provider;
    provider.initialize(el);
    provider.setCompact?.(compact);
    // Push any already-loaded data into the freshly created provider.
    if (data) provider.setData(data);
    if (livePriceRef.current != null) provider.setLivePrice?.(livePriceRef.current);
    if (compareSeries.length) provider.setCompare?.(compareSeries);
    onProviderReady?.(provider);
    return () => {
      onProviderReady?.(null);
      provider.destroy();
      providerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartState.provider]);

  // Push data into the provider whenever it changes.
  useEffect(() => {
    if (data) providerRef.current?.setData(data);
  }, [data]);

  // Push compare overlays into the provider.
  useEffect(() => {
    providerRef.current?.setCompare?.(compareSeries);
  }, [compareSeries]);

  // ── Live quote + refresh timer ────────────────────────────────────────────
  // Quotes come from the shared DataSubscriptionManager, so duplicate charts of
  // the same instrument share ONE /api/quote subscription (spec §9).
  const [refreshMs, setRefreshMs] = useState(60_000);
  const refreshMsRef = useRef(refreshMs);
  refreshMsRef.current = refreshMs;
  const [quote, setQuote] = useState<LiveQuote | null>(null);
  const [secondsLeft, setSecondsLeft] = useState(60);

  const sharedQuote = useLiveQuote(chartState.symbol, chartState.market, refreshMs);

  useEffect(() => {
    const price = sharedQuote.found && sharedQuote.price != null ? sharedQuote.price : null;
    livePriceRef.current = price;
    providerRef.current?.setLivePrice?.(price);
    setQuote(
      price != null
        ? {
            price,
            changePercent: sharedQuote.changePercent,
            currency: sharedQuote.currency,
            updatedAt: sharedQuote.updatedAt,
            at: sharedQuote.at ?? Date.now(),
          }
        : null,
    );
  }, [sharedQuote]);

  // Per-chart countdown to the next refresh (uses the shared poll cadence).
  useEffect(() => {
    let nextAt = Date.now() + refreshMsRef.current;
    let cancelled = false;
    setSecondsLeft(Math.round(refreshMsRef.current / 1000));
    const timer = setInterval(() => {
      if (cancelled) return;
      if (refreshMsRef.current <= 0) return;
      if (Date.now() >= nextAt) nextAt = Date.now() + refreshMsRef.current;
      setSecondsLeft(Math.max(0, Math.ceil((nextAt - Date.now()) / 1000)));
    }, 1000);
    return () => { cancelled = true; clearInterval(timer); };
  }, [chartState.symbol, chartState.market, refreshMs]);

  // Reload OHLCV when the currently-forming candle closes so the newest bar
  // appears without the user hitting refresh (Yahoo is delayed, so this just
  // re-pulls the same range and picks up the new candle when available).
  const refreshRef = useRef(refresh);
  refreshRef.current = refresh;
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    const schedule = () => {
      const { at } = nextCandleAt(chartState.timeframe, chartState.symbol, chartState.market, new Date());
      // Fire a few seconds after the boundary to let upstream roll the candle.
      const delay = Math.max(5_000, at - Date.now() + 4_000);
      timer = setTimeout(() => { refreshRef.current(); schedule(); }, delay);
    };
    schedule();
    return () => clearTimeout(timer);
  }, [chartState.symbol, chartState.market, chartState.timeframe]);

  // Dense mode for small multi-chart panels.
  useEffect(() => {
    providerRef.current?.setCompact?.(compact);
  }, [compact, chartState.provider]);

  // Linked-chart observers: publish crosshair moves + range changes to the host.
  useEffect(() => {
    providerRef.current?.onCrosshair?.((t) => onCrosshair?.(t));
  }, [onCrosshair, chartState.provider]);
  useEffect(() => {
    providerRef.current?.onRange?.((r) => onRange?.(r));
  }, [onRange, chartState.provider]);

  // Apply crosshair / range driven by a linked peer (echo-suppressed upstream).
  useEffect(() => {
    providerRef.current?.setCrosshair?.(crosshairTime ?? null);
  }, [crosshairTime]);
  useEffect(() => {
    if (range) providerRef.current?.setRange?.(range);
  }, [range]);

  // Keep the provider's symbol/timeframe/chartType in sync with state.
  useEffect(() => {
    providerRef.current?.setSymbol(chartState.symbol, chartState.market);
  }, [chartState.symbol, chartState.market]);  useEffect(() => {
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
  const pickSymbol = (sym: string, market: string) =>
    setState({ ...chartState, symbol: sym.toUpperCase(), market: market || chartState.market });
  const addIndicator = (config: ChartIndicatorConfig) => {
    if (chartState.indicators.some((i) => i.id === config.id)) return;
    setState({ ...chartState, indicators: [...chartState.indicators, config] });
  };
  const removeIndicator = (id: string) => {
    setState({ ...chartState, indicators: chartState.indicators.filter((i) => i.id !== id) });
  };

  // ── Compare overlays ──────────────────────────────────────────────────────
  const addCompare = (sym: string, market: string) => {
    const symbol = sym.toUpperCase();
    const id = `${symbol}:${market || chartState.market}`;
    if (compareList.some((c) => c.id === id)) return;
    const colors = getChartPalette().lines.series;
    const color = colors[compareList.length % colors.length];
    setState({ ...chartState, compare: [...compareList, { id, symbol, market: market || chartState.market, color }] });
  };
  const removeCompare = (id: string) => {
    setState({ ...chartState, compare: compareList.filter((c) => c.id !== id) });
  };

  // ── Drawing system ────────────────────────────────────────────────────────
  const [drawingManager] = useState(() => {
    const saved = loadSavedDrawings(symbol ?? 'AAPL');
    return new DrawingManager(saved);
  });
  const [drawingController] = useState(() => new DrawingController(drawingManager));
  const [internalTool, setInternalTool] = useState<DrawingToolMode>('cursor');
  const tool = controlledTool ?? internalTool;
  const setTool = useCallback((t: DrawingToolMode) => {
    if (controlledTool === undefined) setInternalTool(t);
    onToolChange?.(t);
  }, [controlledTool, onToolChange]);
  const [, forceRender] = useState(0);

  // Mirror an externally controlled tool into the drawing controller.
  useEffect(() => {
    if (controlledTool !== undefined) drawingController.setTool(controlledTool);
  }, [controlledTool, drawingController]);

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
  const onDrawingKey = (e: KeyboardEvent) => {
    const root = rootRef.current;
    if (!root || !canHandleKeyboardEvent(e, root) || document.activeElement?.closest('[data-chart-keyboard-root]') !== root) return;
    if (matchesShortcut(e, 'escape') && (drawingController.isInteracting() || drawingController.getTool() !== 'cursor')) {
      e.preventDefault();
      drawingController.cancel();
      drawingController.pointerUp();
      drawingController.setTool('cursor');
      setTool('cursor');
    } else if (matchesShortcut(e, 'delete') || matchesShortcut(e, 'backspace')) {
      const sel = drawingManager.getSelected();
      if (!sel || sel.locked) return;
      e.preventDefault();
      drawingManager.delete(sel.id);
    } else if (matchesShortcut(e, 'mod+shift+z') && drawingManager.canRedo()) {
      e.preventDefault();
      drawingManager.redo();
    } else if (matchesShortcut(e, 'mod+z') && drawingManager.canUndo()) {
      e.preventDefault();
      drawingManager.undo();
    } else if (matchesShortcut(e, 'v')) {
      e.preventDefault();
      toggleVolume();
    } else if (matchesShortcut(e, '0')) {
      e.preventDefault();
      resetZoom();
    } else if (matchesShortcut(e, '=') || (e.key === '+' && !e.ctrlKey && !e.metaKey && !e.altKey)) {
      e.preventDefault();
      zoomIn();
    } else if (matchesShortcut(e, '-') || (e.key === '_' && !e.ctrlKey && !e.metaKey && !e.altKey)) {
      e.preventDefault();
      zoomOut();
    } else if (matchesShortcut(e, 'alt+arrowleft')) {
      e.preventDefault();
      panLeft();
    } else if (matchesShortcut(e, 'alt+arrowright')) {
      e.preventDefault();
      panRight();
    }
  };

  const selectTool = (t: DrawingToolMode) => {
    drawingController.setTool(t);
    setTool(t);
  };

  const getChart = () => {
    const p = providerRef.current as EclipseChartProvider | null;
    return p?.getEChartsInstance?.() ?? null;
  };

  // Navigation controls — only meaningful for the native Eclipse provider.
  const isEclipse = chartState.provider === 'eclipse';
  const showVolume = chartState.settings?.showVolume !== false;
  const toggleVolume = () => {
    const next = { ...chartState, settings: { ...chartState.settings, showVolume: !showVolume } };
    (providerRef.current as EclipseChartProvider | null)?.setShowVolume?.(!showVolume);
    setState(next);
  };

  const zoomIn = () => (providerRef.current as EclipseChartProvider | null)?.zoomBy?.(0.7);
  const zoomOut = () => (providerRef.current as EclipseChartProvider | null)?.zoomBy?.(1.4);
  const panLeft = () => (providerRef.current as EclipseChartProvider | null)?.panBy?.(-0.25);
  const panRight = () => (providerRef.current as EclipseChartProvider | null)?.panBy?.(0.25);
  const resetZoom = () => (providerRef.current as EclipseChartProvider | null)?.resetZoom?.();

  const openSearch = () => useCommandStore.getState().setOpen(true);

  // No bars came back after loading → the symbol could not be resolved.
  const notFound = !loading && !error && !!data && data.bars.length === 0;
  const emptyResult = notFound || (!!error && !loading);

  return (
    <div
      ref={rootRef}
      tabIndex={0}
      data-chart-keyboard-root
      data-keyboard-scope={`${chartState.symbol} chart`}
      aria-label={`${chartState.symbol} chart`}
      onKeyDown={(e) => onDrawingKey(e.nativeEvent)}
      onPointerDownCapture={(e) => {
        const target = e.target as HTMLElement;
        const interactive = target.closest('input, textarea, select, [contenteditable], [role="textbox"], [role="combobox"], button, a, [tabindex]');
        if (e.button !== 0 || (interactive && interactive !== e.currentTarget)) return;
        e.currentTarget.focus({ preventScroll: true });
      }}
      className={cn('flex h-full min-h-0 w-full flex-col focus-visible:outline focus-visible:outline-1 focus-visible:outline-primary', compact ? 'gap-1' : 'gap-2', className)}
    >
      {!hideToolbar && (
        <ChartToolbar
          state={chartState}
          loading={loading}
          compact={compact}
          tool={tool}
          onTool={selectTool}
          onProvider={setProvider}
          onTimeframe={setTimeframe}
          onChartType={setChartType}
          onSymbol={setSymbol}
          onPickSymbol={pickSymbol}
          onSearch={openSearch}
          onRefresh={refresh}
          onAddIndicator={addIndicator}
          onRemoveIndicator={removeIndicator}
          showVolume={showVolume}
          onToggleVolume={toggleVolume}
          compare={compareList}
          compareSeries={compareSeries}
          onAddCompare={addCompare}
          onRemoveCompare={removeCompare}
          manager={drawingManager}
          isEclipse={isEclipse}
          onZoomIn={zoomIn}
          onZoomOut={zoomOut}
          onPanLeft={panLeft}
          onPanRight={panRight}
          onResetZoom={resetZoom}
        />
      )}

      <div className={cn('relative min-h-0 flex-1 overflow-hidden', compact ? 'rounded-lg' : 'rounded-2xl', 'border border-border/10 glass-card-subtle')}>
        <div ref={containerRef} className="absolute inset-0" />
        <DrawingOverlay getChart={getChart} manager={drawingManager} controller={drawingController} tool={tool} />
        {!emptyResult && !compact && (
          <LivePriceOverlay
            symbol={chartState.symbol}
            market={chartState.market}
            timeframe={chartState.timeframe}
          />
        )}
        {loading && (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center">
            <span className="text-[11px] font-mono text-muted-foreground/70 animate-pulse">Loading {chartState.symbol}…</span>
          </div>
        )}
        {emptyResult && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 bg-background/40 px-6 text-center backdrop-blur-[1px]">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-rose-500/25 bg-rose-500/10">
              <SearchX className="text-rose-400" size={20} />
            </div>
            <div>
              <p className="text-sm font-bold text-foreground">Symbol not found</p>
              <p className="mt-0.5 text-[11px] text-muted-foreground">
                {error ? error : `No price data available for “${chartState.symbol}”.`}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={openSearch}
                className="inline-flex items-center gap-1.5 rounded-xl border border-primary/40 bg-primary/15 px-3 py-1.5 text-[11px] font-bold text-primary transition-colors hover:bg-primary/25 cursor-pointer"
              >
                <Search size={12} /> Search symbols
              </button>
              <button
                onClick={refresh}
                className="inline-flex items-center gap-1.5 rounded-xl border border-border/40 bg-accent/30 px-3 py-1.5 text-[11px] font-bold text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
              >
                <RefreshCw size={12} /> Retry
              </button>
            </div>
          </div>
        )}
      </div>

      {!hideFooter && !compact && (
        <PriceFooter
          symbol={chartState.symbol}
          market={chartState.market}
          timeframe={chartState.timeframe}
          quote={quote}
          refreshMs={refreshMs}
          secondsLeft={secondsLeft}
          onRefreshMs={setRefreshMs}
          onRefresh={refresh}
          loading={loading}
        />
      )}
    </div>
  );
}

// ── Price footer ──────────────────────────────────────────────────────────────

/**
 * On-chart candle countdown, pinned to the top-right of the chart as a black
 * frosted-glass pill (always with a backdrop blur). The live PRICE is shown on
 * the right price axis (TradingView-style tag) by the provider, so this overlay
 * carries ONLY the time until the current candle closes.
 */
function LivePriceOverlay({
  symbol, market, timeframe,
}: {
  symbol: string;
  market: string;
  timeframe: Timeframe;
}) {
  const { candle, candleLeft, closedMarket } = useCandleCountdown(timeframe, symbol, market);

  return (
    <div
      className="pointer-events-none absolute right-3 top-3 z-20 flex items-center gap-1.5 rounded-lg border border-border/30 px-2 py-1 font-mono text-[10px] glass-ticker"
      title={`Time until the next ${candle.label}`}
    >
      <span className={cn('h-1.5 w-1.5 rounded-full', closedMarket ? 'bg-amber-400' : 'animate-pulse bg-primary')} />
      <span className="text-muted-foreground">{closedMarket ? 'closed' : candle.label}</span>
      <span className="font-bold tabular-nums text-foreground">{formatCountdown(candleLeft)}</span>
    </div>
  );
}

/**
 * Live price strip under the chart: shows the last quote, its change, and a
 * refresh timer with a selectable cadence (30s / 1m / 5m / 15m / Off).
 */
function PriceFooter({
  symbol, market, timeframe, quote, refreshMs, secondsLeft, onRefreshMs, onRefresh, loading,
}: {
  symbol: string;
  market: string;
  timeframe: Timeframe;
  quote: LiveQuote | null;
  refreshMs: number;
  secondsLeft: number;
  onRefreshMs: (ms: number) => void;
  onRefresh: () => void;
  loading: boolean;
}) {
  const palette = useChartPalette();
  const up = (quote?.changePercent ?? 0) >= 0;
  const color = quote ? (up ? palette.candles.up : palette.candles.down) : palette.candles.neutral;
  const fmtPrice = (n: number) =>
    n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: n < 1 ? 6 : 2 });
  const updated = quote?.at ? new Date(quote.at).toLocaleTimeString('en-US', { hour12: false }) : null;

  const { candle, candleLeft, closedMarket } = useCandleCountdown(timeframe, symbol, market);

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-xl border border-border/10 glass-card-subtle px-3 py-1.5 text-[11px] font-mono">
      <span className="font-bold text-foreground">{symbol}</span>
      {quote ? (
        <>
          <span className="font-bold" style={{ color }}>
            {quote.currency}{fmtPrice(quote.price)}
          </span>
          <span className="font-semibold" style={{ color }}>
            {up ? '+' : ''}{quote.changePercent.toFixed(2)}%
          </span>
        </>
      ) : (
        <span className="text-muted-foreground/60">— no quote</span>
      )}

      {/* Next-candle countdown */}
      <span
        className="flex items-center gap-1.5 rounded-lg bg-accent/30 px-2 py-0.5"
        title={`Time until the next ${candle.label}`}
      >
        <span className={cn('h-1.5 w-1.5 rounded-full', closedMarket ? 'bg-amber-400' : 'bg-primary')} />
        <span className="text-muted-foreground">
          {closedMarket ? 'market closed ·' : 'next'} {candle.label}
        </span>
        <span className="font-bold tabular-nums text-foreground">{formatCountdown(candleLeft)}</span>
      </span>

      <span className="ml-auto flex items-center gap-1.5 text-muted-foreground">
        {refreshMs > 0 ? (
          <>
            <span className={cn('relative flex h-1.5 w-1.5', loading && 'animate-pulse')}>
              <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: color }} />
            </span>
            <span title="Time until next refresh">
              refreshes in <span className="font-bold text-foreground">{secondsLeft}s</span>
            </span>
          </>
        ) : (
          <span>auto-refresh off</span>
        )}
        {updated && <span className="text-muted-foreground/50">· {updated}</span>}
      </span>

      {/* Refresh cadence */}
      <div className="flex items-center gap-0.5 rounded-lg bg-accent/30 p-0.5">
        {REFRESH_OPTIONS.map((o) => (
          <button
            key={o.label}
            onClick={() => onRefreshMs(o.ms)}
            title={o.ms ? `Refresh every ${o.label}` : 'Disable auto-refresh'}
            className={cn(
              'rounded-md px-1.5 py-0.5 text-[9px] font-bold transition-colors cursor-pointer',
              o.ms === refreshMs ? 'bg-muted-foreground/20 text-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {o.label}
          </button>
        ))}
      </div>

      <button
        onClick={onRefresh}
        title="Refresh now"
        className="inline-flex items-center gap-1 rounded-lg bg-accent/40 px-2 py-1 text-[10px] font-bold text-muted-foreground transition-colors hover:bg-accent/70 hover:text-foreground cursor-pointer"
      >
        <RefreshCw size={11} className={cn(loading && 'animate-spin')} />
      </button>
    </div>
  );
}

// ── Symbol search ─────────────────────────────────────────────────────────────

interface SymbolSuggestion {
  symbol: string;
  name: string;
  marketId: string;
  currency?: string;
  price?: number;
}

/**
 * Chart-toolbar symbol search. Queries /api/quote?q= for the full JDDS universe
 * (55k+ assets) and lets the user pick any tradable symbol + market. Falls back
 * to the global command palette via the magnifier button / Enter on empty.
 */
function SymbolSearch({
  current, onPick, onSubmit, onOpenPalette,
}: {
  current: string;
  onPick: (symbol: string, market: string) => void;
  onSubmit: (symbol: string) => void;
  onOpenPalette: () => void;
}) {
  const [query, setQuery] = useState(current);
  const [suggestions, setSuggestions] = useState<SymbolSuggestion[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => { setQuery(current); }, [current]);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 1 || q.toUpperCase() === current.toUpperCase()) {
      setSuggestions([]);
      return;
    }
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const res = await fetch(`/api/quote?q=${encodeURIComponent(q)}`);
        const data = (await res.json()) as { suggestions?: SymbolSuggestion[] };
        setSuggestions(data.suggestions ?? []);
        setHighlight(0);
        setOpen(true);
      } catch {
        setSuggestions([]);
      } finally {
        setLoading(false);
      }
    }, 180);
    return () => clearTimeout(t);
  }, [query, current]);

  useEffect(() => {
    const onDoc = (e: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, []);

  const choose = (s: SymbolSuggestion) => {
    onPick(s.symbol, s.marketId);
    setQuery(s.symbol);
    setOpen(false);
  };

  return (
    <div ref={boxRef} className="relative">
      <div className="flex items-center gap-1 rounded-lg bg-accent/40 px-2 py-1">
        <button
          type="button"
          onClick={onOpenPalette}
          title="Open command center (/ or Ctrl+K)"
          className="text-muted-foreground hover:text-foreground transition-colors cursor-pointer"
        >
          <Search size={12} />
        </button>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => { if (suggestions.length) setOpen(true); }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault();
              if (suggestions.length) setOpen(true);
              setHighlight((h) => Math.min(h + 1, suggestions.length - 1));
            } else if (e.key === 'ArrowUp') {
              e.preventDefault();
              setHighlight((h) => Math.max(h - 1, 0));
            } else if (e.key === 'Enter') {
              e.preventDefault();
              if (open && suggestions[highlight]) choose(suggestions[highlight]);
              else if (query.trim()) onSubmit(query.trim());
              setOpen(false);
            } else if (e.key === 'Escape') {
              setOpen(false);
            }
          }}
          className="w-20 bg-transparent font-mono text-[11px] font-bold text-foreground outline-none placeholder:text-muted-foreground/50"
          placeholder="Symbol"
          spellCheck={false}
        />
        {loading && <span className="h-3 w-3 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground/70" />}
      </div>

      {open && suggestions.length > 0 && (
        <div className="absolute left-0 top-full z-50 mt-1.5 w-72 max-h-72 overflow-y-auto rounded-xl border border-border/40 glass-card-strong p-1 shadow-2xl animate-fade-in">
          {suggestions.map((s, i) => (
            <button
              key={`${s.symbol}-${s.marketId}`}
              type="button"
              onMouseEnter={() => setHighlight(i)}
              onClick={() => choose(s)}
              className={cn(
                'flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-1.5 text-left transition-colors cursor-pointer',
                i === highlight ? 'bg-accent/60' : 'hover:bg-accent/50',
              )}
            >
              <span className="flex flex-col min-w-0">
                <span className="font-mono text-[11px] font-bold text-foreground">{s.symbol}</span>
                <span className="truncate text-[9px] text-muted-foreground">{s.name}</span>
              </span>
              <span className="ml-2 shrink-0 rounded bg-accent/40 px-1.5 py-0.5 text-[8px] font-bold uppercase text-muted-foreground">{s.marketId}</span>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Toolbar ───────────────────────────────────────────────────────────────────

function ChartToolbar({
  state, loading, compact, tool, onTool, onProvider, onTimeframe, onChartType, onSymbol, onPickSymbol, onSearch, onRefresh,
  onAddIndicator, onRemoveIndicator, showVolume, onToggleVolume, compare, compareSeries, onAddCompare, onRemoveCompare, manager, isEclipse, onZoomIn, onZoomOut, onPanLeft, onPanRight, onResetZoom,
}: {
  state: ChartState;
  loading: boolean;
  compact: boolean;
  showVolume: boolean;
  onToggleVolume: () => void;
  tool: DrawingToolMode;
  onTool: (t: DrawingToolMode) => void;
  onProvider: (p: ChartProviderId) => void;
  onTimeframe: (t: Timeframe) => void;
  onChartType: (t: ChartType) => void;
  onSymbol: (s: string) => void;
  onPickSymbol: (s: string, market: string) => void;
  onSearch: () => void;
  onRefresh: () => void;
  onAddIndicator: (config: ChartIndicatorConfig) => void;
  onRemoveIndicator: (id: string) => void;
  compare: ChartCompareItem[];
  compareSeries: ChartCompareSeries[];
  onAddCompare: (symbol: string, market: string) => void;
  onRemoveCompare: (id: string) => void;
  manager: DrawingManager;
  isEclipse: boolean;
  onZoomIn: () => void;
  onZoomOut: () => void;
  onPanLeft: () => void;
  onPanRight: () => void;
  onResetZoom: () => void;
}) {
  return (
    <div className={cn(
      'relative z-20 flex flex-wrap items-center gap-1.5 border border-border/10 glass-card-subtle',
      compact ? 'rounded-lg px-1 py-0.5' : 'rounded-2xl px-2 py-1.5',
    )}>
      {/* Symbol search — autocompletes against the full JDDS universe */}
      <SymbolSearch current={state.symbol} onPick={onPickSymbol} onSubmit={onSymbol} onOpenPalette={onSearch} />

      {/* Timeframe. Dense panels trim the list to the intraday + daily core. */}
      <div className="flex items-center gap-0.5 rounded-lg bg-accent/30 p-0.5">
        {(compact ? TIMEFRAMES.filter(t => ['5m', '15m', '1H', '4H', '1D'].includes(t)) : TIMEFRAMES).map((tf) => (
          <button
            key={tf}
            onClick={() => onTimeframe(tf)}
            className={cn(
              'rounded-md px-1.5 py-0.5 text-[10px] font-bold transition-colors cursor-pointer',
              tf === state.timeframe ? 'bg-muted-foreground/20 text-foreground' : 'text-muted-foreground hover:text-foreground'
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
              ct === state.chartType ? 'bg-muted-foreground/20 text-foreground' : 'text-muted-foreground hover:text-foreground'
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
        showVolume={showVolume}
        onToggleVolume={onToggleVolume}
      />


      {/* Compare — hidden on dense panels where toolbar space is scarce. */}
      {!compact && (
        <CompareMenu
          compare={compare}
          series={compareSeries}
          onAdd={onAddCompare}
          onRemove={onRemoveCompare}
          primarySymbol={state.symbol}
        />
      )}

      {/* Drawing tools */}
      <DrawingToolbar tool={tool} onTool={onTool} manager={manager} />

      {/* Navigation — pan / zoom / reset (Eclipse provider only) */}
      {isEclipse && !compact && (
        <div className="flex items-center gap-0.5 rounded-lg bg-accent/30 p-0.5">
          <button
            onClick={onPanLeft}
            title="Pan left"
            className="rounded-md p-1 text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors cursor-pointer"
          ><ChevronLeft size={13} /></button>
          <button
            onClick={onPanRight}
            title="Pan right"
            className="rounded-md p-1 text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors cursor-pointer"
          ><ChevronRight size={13} /></button>
          <button
            onClick={onZoomIn}
            title="Zoom in"
            className="rounded-md p-1 text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors cursor-pointer"
          ><ZoomIn size={13} /></button>
          <button
            onClick={onZoomOut}
            title="Zoom out"
            className="rounded-md p-1 text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors cursor-pointer"
          ><ZoomOut size={13} /></button>
          <button
            onClick={onResetZoom}
            title="Reset zoom (fit all)"
            className="rounded-md p-1 text-muted-foreground hover:text-foreground hover:bg-accent/60 transition-colors cursor-pointer"
          ><Maximize2 size={13} /></button>
        </div>
      )}

      <div className="flex-1" />

      {/* Provider selector */}
      <ProviderDropdown value={state.provider} onChange={onProvider} />

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
  active, onAdd, onRemove, showVolume, onToggleVolume,
}: {
  active: ChartIndicatorConfig[];
  onAdd: (config: ChartIndicatorConfig) => void;
  onRemove: (id: string) => void;
  showVolume: boolean;
  onToggleVolume: () => void;
}) {
  const indicators = getAllIndicators();

  const add = (id: string) => {
    const def = indicators.find((i) => i.id === id);
    if (!def) return;
    const settings: Record<string, number | string | boolean> = {};
    for (const input of def.inputs) settings[input.key] = input.default;
    onAdd({ id, settings });
  };

  return (
    <ToolbarMenu
      icon={<LineChart size={12} />}
      label={<>Indicators {active.length > 0 && `(${active.length})`}</>}
      active={active.length > 0}
      title="Indicators"
      width={256}
    >
      {() => (
        <>
          <div className="px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Panes</div>
          <button
            onClick={onToggleVolume}
            className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left transition-colors hover:bg-accent/40 cursor-pointer"
          >
            <span className="text-[11px] font-semibold text-foreground">Volume</span>
            <span className={cn('h-3.5 w-6 rounded-full border relative transition-colors', showVolume ? 'bg-muted-foreground/30 border-border/60' : 'bg-accent/40 border-border/40')}>
              <span className={cn('absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full transition-all', showVolume ? 'left-3 bg-foreground/70' : 'left-0.5 bg-muted-foreground/60')} />
            </span>
          </button>
          <div className="mt-1 border-t border-border/10 px-2 pt-1.5 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Active</div>
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
        </>
      )}
    </ToolbarMenu>
  );
}

// ── Compare menu ─────────────────────────────────────────────────────────────

/**
 * Compare menu — add extra instruments overlaid as relative-performance lines on
 * the main pane. Uses the same autocomplete source as the symbol search, and
 * shows each active compare's % change with a color swatch + remove control.
 */
function CompareMenu({
  compare, series, onAdd, onRemove, primarySymbol,
}: {
  compare: ChartCompareItem[];
  series: ChartCompareSeries[];
  onAdd: (symbol: string, market: string) => void;
  onRemove: (id: string) => void;
  primarySymbol: string;
}) {
  const palette = useChartPalette();
  const [query, setQuery] = useState('');
  const [suggestions, setSuggestions] = useState<SymbolSuggestion[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const q = query.trim();
    if (q.length < 1) { setSuggestions([]); return; }
    const controller = new AbortController();
    setLoading(true);
    const t = setTimeout(() => {
      fetch(`/api/quote?q=${encodeURIComponent(q)}`, { signal: controller.signal })
        .then((r) => (r.ok ? r.json() : { suggestions: [] }))
        .then((j: { suggestions?: SymbolSuggestion[] }) => {
          if (!controller.signal.aborted) setSuggestions((j.suggestions ?? []).slice(0, 50));
        })
        .catch(() => {})
        .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    }, 200);
    return () => { controller.abort(); clearTimeout(t); };
  }, [query]);

  const changeOf = (id: string) => series.find((s) => s.id === id)?.changePercent;

  return (
    <ToolbarMenu
      icon={<Plus size={12} />}
      label={<>Compare {compare.length > 0 && `(${compare.length})`}</>}
      active={compare.length > 0}
      title="Compare assets"
      width={288}
    >
      {() => (
        <>
          <div className="px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Comparing vs {primarySymbol}</div>
          {compare.length === 0 && (
            <div className="px-2 py-1 text-[10px] text-muted-foreground/60 italic">No assets added</div>
          )}
          {compare.map((c, index) => {
            const chg = changeOf(c.id);
            const seriesIndex = series.findIndex((s) => s.id === c.id);
            const color = palette.lines.series[(seriesIndex < 0 ? index : seriesIndex) % palette.lines.series.length];
            return (
              <div key={c.id} className="flex items-center justify-between rounded-lg px-2 py-1 hover:bg-accent/40">
                <span className="flex items-center gap-2 min-w-0">
                  <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: color }} />
                  <span className="truncate font-mono text-[11px] font-bold text-foreground">{c.symbol}</span>
                </span>
                <span className="flex items-center gap-1.5">
                  {chg != null && (
                    <span className={cn('font-mono text-[10px] font-bold', chg >= 0 ? 'text-emerald-400' : 'text-rose-400')}>
                      {chg >= 0 ? '+' : ''}{chg.toFixed(2)}%
                    </span>
                  )}
                  <button
                    onClick={() => onRemove(c.id)}
                    className="rounded p-0.5 text-muted-foreground hover:text-rose-400 transition-colors cursor-pointer"
                    title="Remove"
                  >
                    <X size={12} />
                  </button>
                </span>
              </div>
            );
          })}

          <div className="mt-1 border-t border-border/10 pt-1.5 px-1">
            <div className="mb-1 flex items-center gap-1.5 rounded-lg bg-accent/40 px-2 py-1">
              <Search size={12} className="shrink-0 text-muted-foreground" />
              <input
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Add symbol to compare…"
                spellCheck={false}
                className="w-full bg-transparent font-mono text-[11px] text-foreground outline-none placeholder:text-muted-foreground/50"
              />
              {loading && <span className="h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-muted-foreground/30 border-t-muted-foreground/70" />}
            </div>
            <div className="max-h-52 overflow-y-auto">
              {suggestions.map((s) => {
                const id = `${s.symbol.toUpperCase()}:${s.marketId}`;
                const already = compare.some((c) => c.id === id);
                return (
                  <button
                    key={`${s.symbol}-${s.marketId}`}
                    onClick={() => { onAdd(s.symbol, s.marketId); setQuery(''); setSuggestions([]); }}
                    disabled={already}
                    className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-left transition-colors cursor-pointer hover:bg-accent/40 disabled:opacity-40 disabled:cursor-not-allowed"
                  >
                    <span className="flex min-w-0 flex-col">
                      <span className="font-mono text-[11px] font-bold text-foreground">{s.symbol}</span>
                      <span className="truncate text-[9px] text-muted-foreground">{s.name}</span>
                    </span>
                    <span className="ml-2 shrink-0 rounded bg-accent/40 px-1.5 py-0.5 text-[8px] font-bold uppercase text-muted-foreground">{s.marketId}</span>
                  </button>
                );
              })}
              {query.trim().length > 0 && !loading && suggestions.length === 0 && (
                <div className="px-2 py-1.5 text-[10px] text-muted-foreground/60 italic">No matches</div>
              )}
            </div>
          </div>
        </>
      )}
    </ToolbarMenu>
  );
}

// ── Drawing toolbar ─────────────────────────────────────────────────────────

const TOOL_GROUPS: Array<{ label: string; tools: DrawingToolMode[] }> = [
  { label: 'Cursor', tools: ['cursor'] },
  { label: 'Lines', tools: ['trendline', 'ray', 'horizontal', 'vertical'] },
  { label: 'Shapes', tools: ['rectangle', 'text', 'arrow'] },
  { label: 'Analysis', tools: ['fibonacci', 'measure', 'long-position', 'short-position'] },
];

/**
 * Map each drawing tool's registry icon name to a lucide component. Kept local
 * to the toolbar because it is the only consumer that renders those strings.
 * Unknown names fall back to a generic glyph so a new tool never renders blank.
 */
const TOOL_ICON: Record<string, LucideIcon> = {
  'trending-up': TrendingUp,
  'trending-down': TrendingDown,
  minus: Minus,
  'move-vertical': MoveVertical,
  square: Square,
  'git-branch': GitBranch,
  type: Type,
  'arrow-up-right': ArrowUpRight,
  ruler: Ruler,
  'mouse-pointer': MousePointer2,
  'move-diagonal': MoveDiagonal,
  'arrow-left-right': ArrowLeftRight,
  spline: Spline,
  waypoints: Waypoints,
  pipette: Pipette,
};

function toolIcon(t: DrawingToolMode): LucideIcon {
  if (t === 'cursor') return MousePointer2;
  const name = getAllDrawingDefs().find((d) => d.type === t)?.icon;
  return (name && TOOL_ICON[name]) || MousePointer2;
}

function DrawingToolbar({
  tool, onTool, manager,
}: {
  tool: DrawingToolMode;
  onTool: (t: DrawingToolMode) => void;
  manager: DrawingManager;
}) {
  const defs = getAllDrawingDefs();
  const [, force] = useState(0);

  useEffect(() => {
    const unsub = manager.subscribe(() => force((n) => n + 1));
    return unsub;
  }, [manager]);

  const selected = manager.getSelected();
  const defName = (t: DrawingToolMode) => (t === 'cursor' ? 'Cursor' : defs.find((d) => d.type === t)?.name ?? t);

  return (
    <ToolbarMenu
      icon={<PenTool size={12} />}
      label={defName(tool)}
      active={tool !== 'cursor'}
      title="Drawing tools"
      width={256}
    >
      {() => (
        <>
          {TOOL_GROUPS.map((group) => (
            <div key={group.label} className="mb-1">
              <div className="px-2 py-0.5 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">{group.label}</div>
              <div className="grid grid-cols-2 gap-1">
                {group.tools.map((t) => {
                  const Icon = toolIcon(t);
                  const active = tool === t;
                  return (
                    <button
                      key={t}
                      onClick={() => onTool(t)}
                      className={cn(
                        'flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-left transition-colors cursor-pointer',
                        active ? 'bg-accent/60 text-foreground' : 'hover:bg-accent/40'
                      )}
                    >
                      <Icon size={11} className={cn('shrink-0', active ? 'text-foreground' : 'text-muted-foreground')} />
                      <span className="min-w-0 truncate text-[10px] font-semibold text-foreground">{defName(t)}</span>
                    </button>
                  );
                })}
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
                className="rounded-lg p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
              ><Undo2 size={13} /></button>
              <button
                onClick={() => manager.redo()}
                disabled={!manager.canRedo()}
                title="Redo (Ctrl+Shift+Z)"
                className="rounded-lg p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
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
                className="rounded-lg p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
              ><Lock size={13} /></button>
              <button
                onClick={() => selected && manager.setVisible(selected.id, !selected.visible)}
                disabled={!selected}
                title="Show/hide"
                className="rounded-lg p-1.5 text-muted-foreground hover:text-foreground disabled:opacity-30 cursor-pointer"
              >{selected?.visible ? <Eye size={13} /> : <EyeOff size={13} />}</button>
            </div>
          </div>
        </>
      )}
    </ToolbarMenu>
  );
}

// ── Provider dropdown ─────────────────────────────────────────────────────────

function ProviderDropdown({ value, onChange }: { value: ChartProviderId; onChange: (p: ChartProviderId) => void }) {
  const options: Array<{ id: ChartProviderId; label: string; desc: string }> = [
    { id: 'eclipse', label: 'Eclipse Chart', desc: 'Native BlackEclipse engine' },
    { id: 'tradingview', label: 'TradingView', desc: 'TradingView advanced chart' },
  ];

  const current = options.find((o) => o.id === value)!;

  return (
    <ToolbarMenu
      align="right"
      width={224}
      title="Chart provider"
      triggerClassName="border border-border/40"
      icon={<span className="text-[10px] text-muted-foreground">●</span>}
      label={current.label}
    >
      {(close) => (
        <>
          {options.map((o) => (
            <button
              key={o.id}
              onClick={() => { onChange(o.id); close(); }}
              className={cn(
                'flex w-full items-start gap-2 rounded-lg px-2.5 py-2 text-left transition-colors cursor-pointer',
                o.id === value ? 'bg-accent/60' : 'hover:bg-accent/50'
              )}
            >
              <span className="mt-0.5 text-[10px] text-muted-foreground">●</span>
              <span>
                <span className="block text-[11px] font-bold text-foreground">{o.label}</span>
                <span className="block text-[9px] text-muted-foreground">{o.desc}</span>
              </span>
            </button>
          ))}
        </>
      )}
    </ToolbarMenu>
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

