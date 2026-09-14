'use client';

// ── PanelHeader — the information header shared by every workspace panel ─────
// A compact, BlackEclipse-native header with a strict info hierarchy:
//   PRIMARY   symbol + exchange badge + price + change
//   SECONDARY OHLC + volume + market session status
//   TERTIARY  technical / AI hints (provided by children)
//
// It adapts to the panel's width: a narrow panel collapses the secondary row
// and shrinks the metadata, never clipping or overlapping the price.

import React from 'react';
import {
  Activity, AlertTriangle, ChevronDown, ChevronUp, Layers, RefreshCw, Settings2, X,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import {
  formatCompact, formatInstrumentChange, formatInstrumentPrice, formatPercent,
  instrumentMeta, marketSession, sessionLabel, toneClass, type SessionStatus,
} from '@/lib/market-workspace/instruments';

export interface PanelHeaderQuote {
  price?: number | null;
  changePercent?: number | null;
  change?: number | null;
  open?: number | null;
  high?: number | null;
  low?: number | null;
  volume?: number | null;
  source?: 'LIVE' | 'DELAYED' | 'DEMO' | 'CLOSED' | 'UNAVAILABLE';
}

const SOURCE_LABEL: Record<string, { label: string; className: string }> = {
  LIVE: { label: 'LIVE', className: 'text-emerald-400 border-emerald-400/30 bg-emerald-400/10' },
  DELAYED: { label: 'DELAYED', className: 'text-sky-400 border-sky-400/30 bg-sky-400/10' },
  DEMO: { label: 'DEMO', className: 'text-amber-400 border-amber-400/30 bg-amber-400/10' },
  CLOSED: { label: 'CLOSED', className: 'text-muted-foreground border-border/40 bg-accent/30' },
  UNAVAILABLE: { label: 'DATA UNAVAILABLE', className: 'text-rose-400 border-rose-400/30 bg-rose-400/10' },
};

const SESSION_TONE: Record<SessionStatus, string> = {
  open: 'text-emerald-400',
  pre: 'text-amber-400',
  after: 'text-amber-400',
  closed: 'text-muted-foreground',
};

export interface PanelHeaderProps {
  symbol: string;
  market: string;
  name?: string;
  quote?: PanelHeaderQuote;
  /** Force a status badge (e.g. DEMO / UNAVAILABLE) over the derived one. */
  status?: 'LIVE' | 'DELAYED' | 'DEMO' | 'CLOSED' | 'UNAVAILABLE';
  /** Dense mode for small panels — hides the OHLC/volume row. */
  compact?: boolean;
  loading?: boolean;
  /** Extra controls rendered at the right (timeframe, AI, menu…). */
  actions?: React.ReactNode;
  /** Slot under the identity block (e.g. timeframe chips). */
  children?: React.ReactNode;
  onRefresh?: () => void;
  onRemove?: () => void;
  onCollapse?: () => void;
  collapsed?: boolean;
  onFocus?: () => void;
  /** Highlight the panel as the workspace's active panel. */
  active?: boolean;
  className?: string;
}

export function PanelHeader({
  symbol, market, name, quote, status, compact = false, loading,
  actions, children, onRefresh, onRemove, onCollapse, collapsed, onFocus, active, className,
}: PanelHeaderProps) {
  const meta = React.useMemo(() => instrumentMeta(symbol, market, name), [symbol, market, name]);
  const session = React.useMemo(() => marketSession(meta), [meta]);
  const price = quote?.price ?? null;
  const changePct = quote?.changePercent ?? null;

  const sourceKey = status ?? quote?.source ?? (price == null ? 'UNAVAILABLE' : 'LIVE');
  const source = SOURCE_LABEL[sourceKey] ?? SOURCE_LABEL.LIVE;

  return (
    <div
      className={cn(
        'flex shrink-0 flex-col border-b border-border/10',
        compact ? 'gap-0.5 px-2 py-1' : 'gap-1 px-3 py-1.5',
        active && 'bg-primary/[0.04]',
        className,
      )}
      onMouseDown={onFocus}
    >
      {/* PRIMARY row */}
      <div className="flex min-w-0 items-center gap-2">
        <div className="flex min-w-0 items-baseline gap-1.5">
          <span className={cn('truncate font-mono font-bold text-foreground', compact ? 'text-[11px]' : 'text-sm')} title={name || symbol}>
            {symbol}
          </span>
          <span className={cn('shrink-0 rounded px-1 py-px font-bold uppercase tracking-wide text-muted-foreground bg-accent/40', compact ? 'text-[7px]' : 'text-[8px]')}>
            {meta.exchange}
          </span>
        </div>

        {price != null && (
          <span className={cn('shrink-0 font-mono font-bold tabular-nums', compact ? 'text-[11px]' : 'text-sm', toneClass(changePct))}>
            {formatInstrumentPrice(meta, price)}
          </span>
        )}
        {changePct != null && (
          <span className={cn('shrink-0 font-mono text-[10px] font-semibold tabular-nums', toneClass(changePct))}>
            {quote?.change != null ? `${formatInstrumentChange(meta, quote.change)} · ` : ''}{formatPercent(changePct)}
          </span>
        )}

        <div className="flex-1" />

        {/* status + controls */}
        <div className="flex shrink-0 items-center gap-1">
          {loading && <RefreshCw size={10} className="animate-spin text-muted-foreground/60" />}
          <span className={cn('rounded border px-1 py-px text-[7px] font-bold uppercase tracking-wider', source.className)}>
            {source.label}
          </span>
          {!compact && (
            <span className={cn('hidden font-mono text-[8px] font-bold uppercase tracking-wider sm:inline', SESSION_TONE[session])} title="Market session">
              {sessionLabel(session)}
            </span>
          )}
          {actions}
          {onRefresh && (
            <button onClick={onRefresh} title="Refresh" className="rounded p-0.5 text-muted-foreground hover:text-primary cursor-pointer">
              <RefreshCw size={11} />
            </button>
          )}
          {onCollapse && (
            <button onClick={onCollapse} title={collapsed ? 'Expand' : 'Collapse'} className="rounded p-0.5 text-muted-foreground hover:text-foreground cursor-pointer">
              {collapsed ? <ChevronDown size={12} /> : <ChevronUp size={12} />}
            </button>
          )}
          {onRemove && (
            <button onClick={onRemove} title="Remove panel" className="rounded p-0.5 text-muted-foreground hover:text-rose-400 cursor-pointer">
              <X size={11} />
            </button>
          )}
        </div>
      </div>

      {/* SECONDARY row — OHLC + volume. Hidden when dense or when no quote. */}
      {!compact && (quote?.open != null || quote?.high != null || quote?.volume != null) && (
        <div className="flex flex-wrap items-center gap-x-2.5 gap-y-0 font-mono text-[9px] text-muted-foreground">
          <Ohlc label="O" value={quote?.open} meta={meta} />
          <Ohlc label="H" value={quote?.high} meta={meta} />
          <Ohlc label="L" value={quote?.low} meta={meta} />
          <Ohlc label="C" value={price} meta={meta} />
          {quote?.volume != null && quote.volume > 0 && (
            <span className="flex items-center gap-1"><span className="text-muted-foreground/60">V</span> {formatCompact(quote.volume)}</span>
          )}
        </div>
      )}

      {children}
    </div>
  );
}

function Ohlc({ label, value, meta }: { label: string; value?: number | null; meta: ReturnType<typeof instrumentMeta> }) {
  return (
    <span className="flex items-center gap-1">
      <span className="text-muted-foreground/60">{label}</span>
      <span className="tabular-nums text-foreground/80">{value != null ? value.toLocaleString('en-US', { minimumFractionDigits: meta.decimals, maximumFractionDigits: meta.decimals }) : '—'}</span>
    </span>
  );
}

/** Small pill button used in panel headers/toolbars. */
export function PanelPill({
  active, onClick, title, children, className,
}: {
  active?: boolean;
  onClick?: () => void;
  title?: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={cn(
        'inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-[10px] font-bold transition-colors cursor-pointer',
        active ? 'bg-primary/20 text-primary' : 'text-muted-foreground hover:text-foreground hover:bg-accent/60',
        className,
      )}
    >
      {children}
    </button>
  );
}

export { Activity, AlertTriangle, Layers, Settings2 };
