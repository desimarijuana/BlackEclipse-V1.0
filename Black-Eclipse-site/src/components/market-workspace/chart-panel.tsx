'use client';

// ── ChartPanel — a single workspace chart with a BlackEclipse-native header ──
// Owns the per-panel chart state (symbol/timeframe/type/indicators/drawings)
// through the shared ChartWidget, exposes the compact controls, the AI drawer
// and the link toggles. Data is deduped by the DataSubscriptionManager, so
// duplicate symbols never create duplicate subscriptions.
//
// Linked crosshair/range flow through the imperative link bus (NOT React state)
// so a crosshair move on one chart never re-renders the whole workspace.

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Bot, Copy, GripVertical, Link2, Maximize2, MoreHorizontal, Trash2,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { ChartWidget } from '@/components/chart/chart-widget';
import { PanelHeader, PanelPill } from './panel-header';
import { ToolbarMenu } from '@/components/chart/toolbar-menu';
import { AiPanel } from './ai-panel';
import { useChartBars, useLiveQuote } from '@/lib/chart/subscription-manager';
import { linkBus } from '@/lib/market-workspace/link-bus';
import type { MarketPanel, ChartLink } from '@/lib/market-workspace/types';
import type { ChartProvider, ChartState, ChartType } from '@/lib/chart/types';
import { CHART_TYPES } from '@/lib/chart/types';

export interface ChartPanelProps {
  panel: MarketPanel;
  /** Dense layout for small cells. */
  compact: boolean;
  /** Grid cell class assigned by the workspace. */
  gridStyle: React.CSSProperties;
  active: boolean;
  editMode?: boolean;
  /** Chart-link state for this panel. */
  onChartChange: (chart: ChartState) => void;
  onLinkChange: (link: ChartLink) => void;
  onToggleAi: () => void;
  onRemove: () => void;
  onDuplicate: () => void;
  onFocus: () => void;
  /** Edit-mode drag handle props (spread onto the header). */
  dragHandleProps?: { onPointerDown: React.PointerEventHandler };
  /** Edit-mode resize handle props (spread onto the corner grip). */
  resizeHandleProps?: { onPointerDown: React.PointerEventHandler };
  /** Drop target callback when a symbol from the watchlist is dropped. */
  onDropSymbol?: (symbol: string, market?: string) => void;
  /**
   * `minimal` = full-page mode: hide every interactive control (toolbar, AI,
   * link, menu, remove) so the screen is pure price action. The header keeps
   * only symbol + price + change.
   */
  chrome?: 'full' | 'minimal';
}

/** A chart panel only needs the chart fields of a ChartState. */
function normalizeChart(panel: MarketPanel): ChartState {
  const base = panel.chart;
  if (base) return base;
  return {
    symbol: panel.symbol ?? 'AAPL',
    market: panel.market ?? 'US',
    timeframe: '1D',
    chartType: 'candlestick',
    provider: 'eclipse',
    indicators: [],
    drawings: [],
    panes: [],
    structure: {},
    compare: [],
    settings: {},
  } as ChartState;
}

export function ChartPanel({
  panel, compact, gridStyle, active, editMode,
  onChartChange, onLinkChange, onToggleAi,
  onRemove, onDuplicate, onFocus,
  dragHandleProps, resizeHandleProps,
  onDropSymbol, chrome = 'full',
}: ChartPanelProps) {
  const minimal = chrome === 'minimal';
  const chart = useMemo(() => normalizeChart(panel), [panel]);
  const providerRef = useRef<ChartProvider | null>(null);

  // Header quote — OHLC comes from the latest bar; live price from the shared
  // quote subscription; both deduped.
  const { data, loading, refresh } = useChartBars(chart.symbol, chart.market, chart.timeframe);
  const quoteStream = useLiveQuote(chart.symbol, chart.market);
  const lastBar = data?.bars?.[data.bars.length - 1];
  const [aiOpen, setAiOpen] = useState(panel.aiOpen ?? false);
  const [dragOver, setDragOver] = useState(false);

  useEffect(() => { setAiOpen(panel.aiOpen ?? false); }, [panel.aiOpen]);

  const quote = useMemo(() => ({
    price: quoteStream.price ?? lastBar?.close ?? null,
    changePercent: quoteStream.found ? quoteStream.changePercent : null,
    open: lastBar?.open ?? null,
    high: lastBar?.high ?? null,
    low: lastBar?.low ?? null,
    volume: lastBar?.volume ?? null,
    source: data
      ? (data.source === 'yfinance' ? 'LIVE' as const : data.source === 'snapshot' ? 'DELAYED' as const : data.source === 'none' ? 'UNAVAILABLE' as const : 'LIVE' as const)
      : 'UNAVAILABLE' as const,
  }), [quoteStream, lastBar, data]);

  // ── Linked crosshair / range (imperative, no React state) ──────────────────
  const linkRef = useRef(panel.link);
  linkRef.current = panel.link;

  // Subscribe once; forward to the live provider. The bus hands us back our own
  // publications too, but the provider's echo-suppression makes that a no-op.
  useEffect(() => {
    const unsubX = linkBus.subscribeCrosshair((time, source) => {
      if (source === panel.id) return;
      if (!linkRef.current?.crosshair) return;
      providerRef.current?.setCrosshair?.(time);
    });
    const unsubR = linkBus.subscribeRange((range, source) => {
      if (source === panel.id) return;
      if (!linkRef.current?.range) return;
      providerRef.current?.setRange?.(range);
    });
    return () => { unsubX(); unsubR(); };
  }, [panel.id]);

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const raw = e.dataTransfer.getData('text/plain');
    if (!raw) return;
    try {
      const parsed = JSON.parse(raw) as { symbol?: string; market?: string };
      if (parsed.symbol) onDropSymbol?.(parsed.symbol, parsed.market);
    } catch {
      onDropSymbol?.(raw.toUpperCase());
    }
  }, [onDropSymbol]);

  const setChartType = (chartType: ChartType) => onChartChange({ ...chart, chartType });

  const link = panel.link;
  const linkActive = !!(link?.symbol || link?.timeframe || link?.crosshair || link?.range);
  const toggleLink = (key: keyof ChartLink) => {
    onLinkChange({ symbol: false, timeframe: false, crosshair: false, range: false, ...link, [key]: !link?.[key] });
  };

  return (
    <div
      className={cn(
        'group/panel relative flex min-h-0 flex-col overflow-hidden rounded-2xl glass-card shadow-md shadow-black/10 transition-all',
        active && 'ring-1 ring-primary/50',
        dragOver && 'ring-2 ring-primary/70',
      )}
      style={gridStyle}
      data-market-panel-id={panel.id}
      tabIndex={0}
      onPointerDownCapture={(e) => {
        const interactive = (e.target as HTMLElement).closest('input, textarea, select, [contenteditable], button, a, [tabindex]');
        if (e.button === 0 && interactive === e.currentTarget) e.currentTarget.focus({ preventScroll: true });
      }}
      onDragOver={(e) => { if (e.dataTransfer.types.includes('text/plain')) { e.preventDefault(); e.dataTransfer.dropEffect = 'copy'; setDragOver(true); } }}
      onDragLeave={() => setDragOver(false)}
      onDrop={onDrop}
    >
      {/* Edit-mode move bar — a dedicated strip ABOVE the header so it never
          covers the header's controls (AI, link, menu, refresh). */}
      {editMode && dragHandleProps && (
        <div
          {...dragHandleProps}
          className="flex h-5 shrink-0 cursor-grab items-center justify-center gap-1 border-b border-border/10 bg-primary/10 active:cursor-grabbing"
          title="Drag to move panel"
        >
          <GripVertical size={12} className="text-primary" />
        </div>
      )}

      <PanelHeader
        symbol={chart.symbol}
        market={chart.market}
        quote={quote}
        loading={loading}
        compact={compact}
        active={active}
        onRefresh={minimal ? undefined : refresh}
        onRemove={minimal ? undefined : onRemove}
        actions={minimal ? undefined : (
          <>
            <LinkMenu link={link} active={linkActive} onToggle={toggleLink} />

            {/* AI toggle */}
            <button
              onClick={() => { setAiOpen(v => !v); onToggleAi(); }}
              className={cn('inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-bold transition-colors cursor-pointer', aiOpen ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:text-primary hover:bg-accent/60')}
              title="AI market view"
            >
              <Bot size={11} /> AI
            </button>

            {/* Panel menu */}
            <ToolbarMenu icon={<MoreHorizontal size={12} />} label={null} align="right" width={220} title="Panel options">
              {(close) => (
                <>
                  <div className="px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Chart type</div>
                  <div className="grid grid-cols-2 gap-1">
                    {CHART_TYPES.map(ct => (
                      <PanelPill key={ct} active={ct === chart.chartType} onClick={() => { setChartType(ct); close(); }} className="justify-start capitalize">
                        {ct === 'candlestick' ? 'Candle' : ct}
                      </PanelPill>
                    ))}
                  </div>
                  <div className="mt-1 border-t border-border/10 pt-1" />
                  <MenuItem icon={<Maximize2 size={12} />} label="Chart fullscreen" onClick={() => { onFocus(); close(); }} />
                  <MenuItem icon={<Copy size={12} />} label="Duplicate panel" onClick={() => { onDuplicate(); close(); }} />
                  <MenuItem icon={<Trash2 size={12} />} label="Remove panel" onClick={() => { onRemove(); close(); }} danger />
                </>
              )}
            </ToolbarMenu>
          </>
        )}
      />

      <div className={cn('relative flex min-h-0 flex-1', aiOpen && !compact ? 'flex-row' : 'flex-col')}>
        <ChartWidget
          state={chart}
          onStateChange={onChartChange}
          compact={compact}
          hideToolbar={minimal}
          hideFooter
          onProviderReady={(p) => { providerRef.current = p; }}
          onCrosshair={(t) => linkBus.publishCrosshair(t, panel.id)}
          onRange={(r) => linkBus.publishRange(r, panel.id)}
          className="min-h-0 flex-1"
        />

        {/* AI drawer — sits BESIDE the chart on wide panels, overlays as a bottom
            sheet on narrow ones so it never hides the candles. */}
        {aiOpen && (
          compact ? (
            <div className="absolute inset-x-0 bottom-0 z-20 max-h-[60%] overflow-hidden rounded-t-2xl border-t border-primary/20 glass-card-strong">
              <AiPanel symbol={chart.symbol} market={chart.market} timeframe={chart.timeframe} compact />
            </div>
          ) : (
            <div className="w-64 shrink-0 overflow-hidden border-l border-border/10 bg-background/20">
              <AiPanel symbol={chart.symbol} market={chart.market} timeframe={chart.timeframe} />
            </div>
          )
        )}
      </div>

      {/* Fullscreen affordance on hover — hidden in minimal (full-page) chrome. */}
      {!minimal && (
        <button
          onClick={onFocus}
          title="Fullscreen (F)"
          className="absolute bottom-2 right-2 z-20 hidden items-center gap-1 rounded-lg border border-border/40 bg-background/80 px-2 py-1 text-[9px] font-bold text-muted-foreground transition-colors hover:text-primary group-hover/panel:flex cursor-pointer"
        >
          <Maximize2 size={10} /> Fullscreen
        </button>
      )}

      {/* Edit-mode resize grip (bottom-right corner). */}
      {editMode && resizeHandleProps && (
        <div
          {...resizeHandleProps}
          className="absolute bottom-0 right-0 z-30 h-4 w-4 cursor-nwse-resize"
          title="Drag to resize panel"
        >
          <div className="absolute bottom-1 right-1 h-2 w-2 rounded-sm border-b-2 border-r-2 border-primary/70" />
        </div>
      )}
    </div>
  );
}

function MenuItem({ icon, label, onClick, danger }: { icon: React.ReactNode; label: string; onClick: () => void; danger?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] font-semibold transition-colors cursor-pointer',
        danger ? 'text-rose-400 hover:bg-rose-500/10' : 'text-foreground hover:bg-accent/50',
      )}
    >
      {icon} {label}
    </button>
  );
}

function LinkMenu({ link, active, onToggle }: { link?: ChartLink; active: boolean; onToggle: (k: keyof ChartLink) => void }) {
  const items: Array<{ key: keyof ChartLink; label: string }> = [
    { key: 'symbol', label: 'Symbol' },
    { key: 'timeframe', label: 'Timeframe' },
    { key: 'crosshair', label: 'Crosshair' },
    { key: 'range', label: 'Range' },
  ];
  return (
    <ToolbarMenu
      icon={<Link2 size={11} />}
      label={null}
      active={active}
      align="right"
      width={200}
      title="Link charts"
    >
      {() => (
        <>
          <div className="px-2 py-1 text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Link this chart</div>
          {items.map(it => (
            <button
              key={it.key}
              onClick={() => onToggle(it.key)}
              className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-[11px] font-semibold text-foreground transition-colors hover:bg-accent/50 cursor-pointer"
            >
              {it.label}
              <span className={cn('relative h-3.5 w-6 rounded-full border transition-colors', link?.[it.key] ? 'border-primary/50 bg-primary/30' : 'border-border/40 bg-accent/40')}>
                <span className={cn('absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 rounded-full transition-all', link?.[it.key] ? 'left-3 bg-primary' : 'left-0.5 bg-muted-foreground/60')} />
              </span>
            </button>
          ))}
          <p className="px-2 pt-1 text-[9px] leading-snug text-muted-foreground/70">Linked charts share symbol, timeframe, crosshair or visible range.</p>
        </>
      )}
    </ToolbarMenu>
  );
}
