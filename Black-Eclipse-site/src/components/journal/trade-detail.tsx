'use client';

// ── Trade Detail — market context, replay chart, and similar trades ──────────

import React, { useCallback, useEffect, useState } from 'react';
import { X, Activity, Layers, ImagePlus, Trash2, PencilLine, Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { TradeRecord } from '@/lib/journal/types';
import { TradeReplayChart, type ReplayBar, type ReplayTrade } from './trade-replay';
import { fmtR } from './charts/echarts-container';

interface TradeDetailProps {
  trade: TradeRecord;
  allTrades: TradeRecord[];
  onClose: () => void;
  onChanged?: () => void;
}

interface MarketContext {
  trend?: string | null;
  vwap?: string | null;
  ema50AboveEma200?: boolean | null;
  adx?: number | null;
  atr?: number | null;
  regime?: string | null;
  volatility?: string | null;
  session?: string | null;
}

interface SimilarTrade {
  trade: TradeRecord;
  score: number;
}

export function TradeDetail({ trade, allTrades, onClose, onChanged }: TradeDetailProps) {
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ entry: String(trade.entry), exit: String(trade.exit), stopLoss: trade.stopLoss != null ? String(trade.stopLoss) : '', takeProfit: trade.takeProfit != null ? String(trade.takeProfit) : '' });
  const [savingEdit, setSavingEdit] = useState(false);
  const [series, setSeries] = useState<ReplayBar[]>([]);
  const [marketContext, setMarketContext] = useState<MarketContext | null>(null);
  const [similar, setSimilar] = useState<SimilarTrade[]>([]);
  const [similarStats, setSimilarStats] = useState<{ winRate: number; averageR: number; count: number } | null>(null);
  const [screenshots, setScreenshots] = useState<{ id: string; url: string; phase?: string | null; caption?: string | null }[]>([]);
  const [shotUrl, setShotUrl] = useState('');
  const [shotPhase, setShotPhase] = useState('during');

  const loadScreenshots = useCallback(async () => {
    const res = await fetch(`/api/journal/screenshots?tradeId=${trade.id}`);
    const data = await res.json();
    setScreenshots(data.screenshots ?? []);
  }, [trade.id]);

  const addScreenshot = async () => {
    if (!shotUrl.trim()) return;
    const res = await fetch('/api/journal/screenshots', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tradeId: trade.id, url: shotUrl.trim(), phase: shotPhase }),
    });
    if (res.ok) {
      setShotUrl('');
      await loadScreenshots();
    }
  };

  const removeScreenshot = async (id: string) => {
    const res = await fetch(`/api/journal/screenshots/${id}`, { method: 'DELETE' });
    if (res.ok) await loadScreenshots();
  };

  const saveEdit = async () => {
    setSavingEdit(true);
    try {
      const res = await fetch(`/api/journal/trades/${trade.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entry: Number(editForm.entry),
          exit: Number(editForm.exit),
          stopLoss: editForm.stopLoss ? Number(editForm.stopLoss) : null,
          takeProfit: editForm.takeProfit ? Number(editForm.takeProfit) : null,
          eventKind: 'updated',
        }),
      });
      if (res.ok) {
        setEditing(false);
        onChanged?.();
      }
    } finally {
      setSavingEdit(false);
    }
  };

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch(`/api/journal/market-intel/${trade.id}`);
      const data = await res.json();
      if (data.series) setSeries(data.series);
      if (data.marketContext) setMarketContext(data.marketContext);
      if (data.trade) {
        // Compute similar trades client-side from the loaded trade list.
        const target: TradeRecord = { ...trade, mfe: data.trade.mfe, mae: data.trade.mae };
        const scored = allTrades
          .filter((t) => t.id !== trade.id && t.status === 'closed')
          .map((t) => ({ trade: t, score: similarity(t, target) }))
          .filter((s) => s.score >= 0.2)
          .sort((a, b) => b.score - a.score)
          .slice(0, 6);
        setSimilar(scored);
        if (scored.length > 0) {
          const rValues = scored.map((s) => s.trade.rMultiple);
          const wins = scored.filter((s) => s.trade.rMultiple > 0).length;
          setSimilarStats({
            winRate: wins / scored.length,
            averageR: rValues.reduce((a, b) => a + b, 0) / rValues.length,
            count: scored.length,
          });
        }
      }
    } finally {
      setLoading(false);
    }
  }, [trade, allTrades]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => { void loadScreenshots(); }, [loadScreenshots]);

  const replayTrade: ReplayTrade = {
    symbol: trade.symbol,
    direction: trade.direction,
    entry: trade.entry,
    exit: trade.exit,
    stopLoss: trade.stopLoss,
    takeProfit: trade.takeProfit,
    entryTime: trade.entryTime,
    exitTime: trade.exitTime,
    rMultiple: trade.rMultiple,
    mfe: trade.mfe,
    mae: trade.mae,
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4" onClick={onClose}>
      <div className="w-full max-w-4xl max-h-[90vh] overflow-y-auto rounded-2xl bg-[#0f0f0f] border border-white/10 p-5" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h2 className="font-serif text-lg font-semibold text-foreground">{trade.symbol}</h2>
            <span className={trade.direction === 'LONG' ? 'text-emerald-400' : 'text-rose-400'}>{trade.direction}</span>
            <span className="font-mono text-xs text-muted-foreground">{trade.exitTime.slice(0, 10)}</span>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setEditing((v) => !v)}
              className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 bg-accent/30 px-2.5 py-1.5 text-[11px] font-semibold text-muted-foreground hover:text-primary transition-all cursor-pointer"
            >
              <PencilLine size={12} /> {editing ? 'Cancel' : 'Edit'}
            </button>
            <button onClick={onClose} className="rounded-lg p-1.5 text-muted-foreground hover:text-foreground hover:bg-accent cursor-pointer">
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Edit form */}
        {editing && (
          <div className="rounded-2xl bg-white/[0.02] p-4 mb-4">
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <EditField label="Entry">
                <input type="number" step="any" value={editForm.entry} onChange={(e) => setEditForm((f) => ({ ...f, entry: e.target.value }))} className="w-full rounded-lg bg-background/60 border border-border/40 px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none" />
              </EditField>
              <EditField label="Exit">
                <input type="number" step="any" value={editForm.exit} onChange={(e) => setEditForm((f) => ({ ...f, exit: e.target.value }))} className="w-full rounded-lg bg-background/60 border border-border/40 px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none" />
              </EditField>
              <EditField label="Stop Loss">
                <input type="number" step="any" value={editForm.stopLoss} onChange={(e) => setEditForm((f) => ({ ...f, stopLoss: e.target.value }))} className="w-full rounded-lg bg-background/60 border border-border/40 px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none" />
              </EditField>
              <EditField label="Take Profit">
                <input type="number" step="any" value={editForm.takeProfit} onChange={(e) => setEditForm((f) => ({ ...f, takeProfit: e.target.value }))} className="w-full rounded-lg bg-background/60 border border-border/40 px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none" />
              </EditField>
            </div>
            <button
              onClick={saveEdit}
              disabled={savingEdit}
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-primary/40 bg-primary/15 text-primary px-3 py-1.5 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50"
            >
              {savingEdit ? <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-primary/30 border-t-primary" /> : <Check size={13} />}
              {savingEdit ? 'Saving…' : 'Save Changes'}
            </button>
          </div>
        )}

        {/* Key stats */}
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4 mb-4">
          <Stat label="Entry" value={String(trade.entry)} />
          <Stat label="Exit" value={String(trade.exit)} />
          <Stat label="R" value={fmtR(trade.rMultiple)} tone={trade.rMultiple >= 0 ? 'text-emerald-400' : 'text-rose-400'} />
          <Stat label="Duration" value={fmtDuration(trade.durationSec)} />
        </div>

        {/* Replay chart */}
        <div className="rounded-2xl bg-white/[0.02] p-4 mb-4">
          {loading ? (
            <div className="h-64 flex items-center justify-center text-xs text-muted-foreground">Loading market data…</div>
          ) : series.length >= 2 ? (
            <TradeReplayChart series={series} trade={replayTrade} />
          ) : (
            <div className="h-64 flex items-center justify-center text-xs text-muted-foreground italic">
              No price history available for {trade.symbol}.
            </div>
          )}
        </div>

        {/* Market context */}
        {marketContext && (
          <div className="rounded-2xl bg-white/[0.02] p-4 mb-4">
            <div className="flex items-center gap-2 mb-3">
              <Activity size={14} className="text-primary" />
              <h3 className="font-serif text-sm font-semibold text-foreground">Market Context</h3>
            </div>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
              <Ctx label="Trend" value={marketContext.trend ?? '—'} tone={marketContext.trend === 'Bullish' ? 'text-emerald-400' : marketContext.trend === 'Bearish' ? 'text-rose-400' : undefined} />
              <Ctx label="VWAP" value={marketContext.vwap ?? '—'} />
              <Ctx label="Regime" value={marketContext.regime ?? '—'} />
              <Ctx label="Volatility" value={marketContext.volatility ?? '—'} />
              <Ctx label="ADX" value={marketContext.adx != null ? marketContext.adx.toFixed(1) : '—'} />
              <Ctx label="ATR" value={marketContext.atr != null ? marketContext.atr.toFixed(2) : '—'} />
              <Ctx label="Session" value={marketContext.session ?? '—'} />
              <Ctx label="EMA50>EMA200" value={marketContext.ema50AboveEma200 == null ? '—' : marketContext.ema50AboveEma200 ? 'Yes' : 'No'} />
            </div>
          </div>
        )}

        {/* Similar trades */}
        {similar.length > 0 && (
          <div className="rounded-2xl bg-white/[0.02] p-4">
            <div className="flex items-center gap-2 mb-3">
              <Layers size={14} className="text-primary" />
              <h3 className="font-serif text-sm font-semibold text-foreground">Similar Historical Trades</h3>
              {similarStats && (
                <span className="ml-auto font-mono text-[10px] text-muted-foreground">
                  {similarStats.count} trades · {(similarStats.winRate * 100).toFixed(0)}% win · avg {fmtR(similarStats.averageR)}
                </span>
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              {similar.map((s) => (
                <div key={s.trade.id} className="flex items-center justify-between rounded-lg bg-white/[0.03] px-3 py-1.5 text-[11px]">
                  <span className="font-mono text-muted-foreground">
                    {s.trade.symbol} · {s.trade.direction} · {s.trade.setupName ?? '—'} · {s.trade.session ?? '—'}
                  </span>
                  <span className="flex items-center gap-3">
                    <span className="font-mono text-muted-foreground/60">{Math.round(s.score * 100)}% match</span>
                    <span className={cn('font-mono font-bold', s.trade.rMultiple >= 0 ? 'text-emerald-400' : 'text-rose-400')}>{fmtR(s.trade.rMultiple)}</span>
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Screenshots */}
        <div className="rounded-2xl bg-white/[0.02] p-4">
          <div className="flex items-center gap-2 mb-3">
            <ImagePlus size={14} className="text-primary" />
            <h3 className="font-serif text-sm font-semibold text-foreground">Screenshots</h3>
          </div>
          <div className="flex items-center gap-2 mb-3">
            <input
              value={shotUrl}
              onChange={(e) => setShotUrl(e.target.value)}
              placeholder="Paste image URL…"
              className="flex-1 rounded-lg bg-background/60 border border-border/40 px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none"
            />
            <select value={shotPhase} onChange={(e) => setShotPhase(e.target.value)} className="rounded-lg bg-background/60 border border-border/40 px-2 py-1.5 text-xs font-mono">
              <option value="before">Before</option>
              <option value="during">During</option>
              <option value="after">After</option>
            </select>
            <button
              onClick={addScreenshot}
              disabled={!shotUrl.trim()}
              className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-primary/40 bg-primary/15 text-primary px-3 py-1.5 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50"
            >
              <ImagePlus size={13} /> Add
            </button>
          </div>
          {screenshots.length === 0 ? (
            <p className="text-xs text-muted-foreground italic">No screenshots yet.</p>
          ) : (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
              {screenshots.map((s) => (
                <div key={s.id} className="group relative rounded-lg overflow-hidden border border-white/10">
                  <img src={s.url} alt={s.caption ?? 'trade screenshot'} className="h-24 w-full object-cover" />
                  <div className="absolute inset-0 flex items-center justify-center bg-black/50 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onClick={() => removeScreenshot(s.id)} className="rounded-lg bg-rose-500/20 p-1.5 text-rose-400 hover:bg-rose-500/30 cursor-pointer">
                      <Trash2 size={13} />
                    </button>
                  </div>
                  {s.phase && <span className="absolute bottom-1 left-1 rounded bg-black/60 px-1.5 py-0.5 text-[8px] font-mono uppercase text-muted-foreground">{s.phase}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-xl bg-white/[0.03] p-2.5">
      <p className="text-[9px] uppercase tracking-widest text-muted-foreground">{label}</p>
      <p className={cn('mt-0.5 font-mono text-sm font-bold', tone ?? 'text-foreground')}>{value}</p>
    </div>
  );
}

function Ctx({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <div className="rounded-lg bg-white/[0.02] p-2">
      <p className="text-[8px] uppercase tracking-widest text-muted-foreground">{label}</p>
      <p className={cn('mt-0.5 font-mono text-[11px] font-bold', tone ?? 'text-foreground')}>{value}</p>
    </div>
  );
}

function EditField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[9px] uppercase tracking-widest text-muted-foreground">{label}</span>
      {children}
    </label>
  );
}

function fmtDuration(sec: number | null): string {
  if (sec == null) return '—';
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.round(sec / 60)}m`;
  return `${(sec / 3600).toFixed(1)}h`;
}

/** Lightweight structured similarity (mirrors the server engine). */
function similarity(a: TradeRecord, b: TradeRecord): number {
  let score = 0;
  const eq = (x?: string | null, y?: string | null) => (x && y && x.toLowerCase() === y.toLowerCase() ? 1 : 0);
  score += eq(a.symbol, b.symbol) * 0.25;
  score += eq(a.direction, b.direction) * 0.1;
  score += eq(a.setupName ?? a.setupId, b.setupName ?? b.setupId) * 0.15;
  score += eq(a.session, b.session) * 0.1;
  score += eq(a.timeframe, b.timeframe) * 0.1;
  score += eq(a.marketRegime, b.marketRegime) * 0.05;
  score += eq(a.trend, b.trend) * 0.05;
  return Math.max(0, Math.min(1, score));
}
