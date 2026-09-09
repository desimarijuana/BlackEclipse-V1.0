'use client';

// ── Journal Reviews — Weekly Review + Monthly Trading Wrapped ────────────────

import React, { useCallback, useEffect, useState } from 'react';
import { MessageSquareText, TrendingUp, TrendingDown, CalendarRange, Award, Flame, Sparkles } from 'lucide-react';
import { cn } from '@/lib/utils';
import { fmtR, fmtMoney } from './charts';
import { AiReview } from './ai-review';

interface ReviewItem { label: string; value: string; tone?: 'pos' | 'neg' | 'neutral' }
interface WeekReview {
  periodStart: string;
  periodEnd: string;
  performance: { trades: number; winRate: number; netR: number; netPnl: number; profitFactor: number };
  whatWorked: { key: string; netR: number }[];
  whatHurt: { key: string; netR: number }[];
  biggestLeak: { key: string; netR: number } | null;
  bestDay: string | null;
  discipline: number;
  sections: { title: string; items: ReviewItem[] }[];
}
interface Wrapped {
  label: string;
  performance: { trades: number; winRate: number; netR: number; netPnl: number; profitFactor: number; expectancy: number; maxDrawdown: number };
  bestSetup: { key: string; netR: number } | null;
  bestMarket: { key: string; netR: number } | null;
  bestSession: { key: string; netR: number } | null;
  bestHour: { key: string; netR: number } | null;
  biggestLeak: { key: string; netR: number } | null;
  bestConfidence: { key: string; netR: number } | null;
  confidenceCorrelation: number | null;
  discipline: number;
}

type View = 'weekly' | 'monthly';

export function JournalReviews() {
  const [view, setView] = useState<View>('weekly');
  const [weeks, setWeeks] = useState<WeekReview[]>([]);
  const [wrapped, setWrapped] = useState<Wrapped | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [wRes, mRes] = await Promise.all([
        fetch('/api/journal/reviews?type=weekly'),
        fetch('/api/journal/reviews?type=monthly'),
      ]);
      const wData = await wRes.json();
      const mData = await mRes.json();
      setWeeks(wData.weeks ?? []);
      setWrapped(mData.wrapped ?? null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  return (
    <div className="flex flex-col gap-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-serif text-lg font-semibold text-foreground">Reviews</h2>
          <p className="text-xs text-muted-foreground mt-0.5">Weekly performance reviews and your monthly trading wrapped.</p>
        </div>
        <div className="flex items-center gap-1 rounded-2xl bg-[#0f0f0f]/60 p-1">
          {(['weekly', 'monthly'] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={cn(
                'inline-flex items-center gap-1.5 rounded-xl px-3 py-1.5 text-xs font-semibold transition-all cursor-pointer',
                view === v ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {v === 'weekly' ? <CalendarRange size={13} /> : <Award size={13} />}
              {v === 'weekly' ? 'Weekly' : 'Monthly Wrapped'}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-12 text-center text-xs text-muted-foreground">Loading reviews…</div>
      ) : view === 'weekly' ? (
        <WeeklyView weeks={weeks} />
      ) : (
        <WrappedView wrapped={wrapped} />
      )}
    </div>
  );
}

function WeeklyView({ weeks }: { weeks: WeekReview[] }) {
  if (weeks.length === 0) return <EmptyState text="No trades in recent weeks yet." />;
  return (
    <div className="flex flex-col gap-4">
      {weeks.map((w) => {
        const netR = w.performance.netR;
        return (
          <div key={w.periodStart} className="rounded-2xl bg-[#0f0f0f]/60 p-4">
            <div className="flex flex-wrap items-center justify-between gap-2 mb-3">
              <div>
                <h3 className="font-serif text-sm font-semibold text-foreground">
                  {fmtRange(w.periodStart, w.periodEnd)}
                </h3>
                <p className="font-mono text-[10px] text-muted-foreground">
                  {w.performance.trades} trades · {(w.performance.winRate * 100).toFixed(0)}% win rate · PF {w.performance.profitFactor === Infinity ? '∞' : w.performance.profitFactor.toFixed(2)}
                </p>
              </div>
              <div className="text-right">
                <p className={cn('font-mono text-xl font-bold', netR >= 0 ? 'text-emerald-400' : 'text-rose-400')}>{fmtR(netR)}</p>
                <p className={cn('font-mono text-[10px]', w.performance.netPnl >= 0 ? 'text-emerald-400/80' : 'text-rose-400/80')}>{fmtMoney(w.performance.netPnl)}</p>
              </div>
            </div>

            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              {w.sections.map((s) => (
                <div key={s.title} className="rounded-xl bg-white/[0.03] p-3">
                  <p className="mb-2 text-[9px] uppercase tracking-widest font-bold text-muted-foreground">{s.title}</p>
                  {s.items.length === 0 ? (
                    <p className="text-[11px] text-muted-foreground/60 italic">No significant entries.</p>
                  ) : (
                    <div className="flex flex-col gap-1">
                      {s.items.map((it) => (
                        <div key={it.label} className="flex items-center justify-between text-[11px]">
                          <span className="text-muted-foreground">{it.label}</span>
                          <span className={cn('font-mono font-bold', it.tone === 'pos' ? 'text-emerald-400' : it.tone === 'neg' ? 'text-rose-400' : 'text-foreground')}>{it.value}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {w.biggestLeak && (
              <div className="mt-3 flex items-center gap-2 rounded-xl bg-rose-500/5 p-3 text-[11px]">
                <Flame size={13} className="text-rose-400 shrink-0" />
                <span className="text-muted-foreground">Biggest leak: <span className="font-bold text-foreground">{w.biggestLeak.key}</span></span>
                <span className="ml-auto font-mono font-bold text-rose-400">{fmtR(w.biggestLeak.netR)}</span>
              </div>
            )}

            <div className="mt-3 flex items-center gap-2 text-[11px]">
              <Sparkles size={13} className="text-primary shrink-0" />
              <span className="text-muted-foreground">
                Discipline <span className="font-mono font-bold text-foreground">{w.discipline}/100</span>
                {w.bestDay && <> · Best hour <span className="font-mono font-bold text-foreground">{w.bestDay}</span></>}
              </span>
            </div>

            <div className="mt-3">
              <AiReview
                query={`Give an AI interpretation of this week's trading performance. Focus on what worked, what hurt, and what to improve next week.`}
                start={w.periodStart}
                end={w.periodEnd}
                buttonLabel="AI Weekly Review"
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function WrappedView({ wrapped }: { wrapped: Wrapped | null }) {
  if (!wrapped || wrapped.performance.trades === 0) {
    return <EmptyState text="No trades this month yet." />;
  }
  const p = wrapped.performance;
  const rows: { icon: React.ComponentType<{ size?: number; className?: string }>; label: string; value: string; sub?: string; tone?: 'pos' | 'neg' }[] = [
    { icon: MessageSquareText, label: 'Best Setup', value: wrapped.bestSetup?.key ?? '—', sub: wrapped.bestSetup ? fmtR(wrapped.bestSetup.netR) : undefined, tone: 'pos' },
    { icon: TrendingUp, label: 'Best Market', value: wrapped.bestMarket?.key ?? '—', sub: wrapped.bestMarket ? fmtR(wrapped.bestMarket.netR) : undefined, tone: 'pos' },
    { icon: TrendingUp, label: 'Best Session', value: wrapped.bestSession?.key ?? '—', sub: wrapped.bestSession ? fmtR(wrapped.bestSession.netR) : undefined, tone: 'pos' },
    { icon: CalendarRange, label: 'Best Hour', value: wrapped.bestHour?.key ?? '—', sub: wrapped.bestHour ? fmtR(wrapped.bestHour.netR) : undefined, tone: 'pos' },
    { icon: Flame, label: 'Biggest Leak', value: wrapped.biggestLeak?.key ?? '—', sub: wrapped.biggestLeak ? fmtR(wrapped.biggestLeak.netR) : undefined, tone: 'neg' },
  ];

  return (
    <div className="rounded-2xl bg-[#0f0f0f]/60 p-6 overflow-hidden relative">
      <div className="absolute -top-16 -right-16 h-56 w-56 rounded-full bg-primary/10 blur-[70px] pointer-events-none" />
      <div className="relative z-10">
        <div className="flex items-center gap-2 mb-6">
          <Sparkles size={16} className="text-primary" />
          <h3 className="font-serif text-2xl font-semibold text-foreground">Your {wrapped.label}</h3>
        </div>

        <div className="flex flex-wrap items-end gap-8 mb-8">
          <div>
            <p className="text-[10px] uppercase tracking-widest text-muted-foreground">Net R</p>
            <p className={cn('font-mono text-5xl font-bold leading-none', p.netR >= 0 ? 'text-emerald-400' : 'text-rose-400')}>{fmtR(p.netR)}</p>
          </div>
          <MiniMetric label="Trades" value={String(p.trades)} />
          <MiniMetric label="Win Rate" value={`${(p.winRate * 100).toFixed(0)}%`} />
          <MiniMetric label="Profit Factor" value={p.profitFactor === Infinity ? '∞' : p.profitFactor.toFixed(2)} />
          <MiniMetric label="Expectancy" value={fmtR(p.expectancy)} />
          <MiniMetric label="Net P&L" value={fmtMoney(p.netPnl)} />
        </div>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {rows.map((r) => {
            const Icon = r.icon;
            return (
              <div key={r.label} className={cn('rounded-2xl p-4', r.tone === 'neg' ? 'bg-rose-500/5' : 'bg-white/[0.03]')}>
                <div className="flex items-center gap-2 mb-1">
                  <Icon size={13} className={r.tone === 'neg' ? 'text-rose-400' : 'text-primary'} />
                  <span className="text-[9px] uppercase tracking-widest text-muted-foreground">{r.label}</span>
                </div>
                <p className="font-mono text-base font-bold text-foreground">{r.value}</p>
                {r.sub && <p className={cn('font-mono text-[10px] font-bold', r.tone === 'neg' ? 'text-rose-400' : 'text-emerald-400')}>{r.sub}</p>}
              </div>
            );
          })}
        </div>

        <div className="mt-6 flex flex-wrap gap-4 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1.5"><Award size={13} className="text-primary" /> Discipline <span className="font-mono font-bold text-foreground">{wrapped.discipline}/100</span></span>
          <span className="flex items-center gap-1.5"><TrendingDown size={13} className="text-rose-400" /> Max drawdown <span className="font-mono font-bold text-foreground">{fmtR(-p.maxDrawdown)}</span></span>
          {wrapped.bestConfidence && <span className="flex items-center gap-1.5"><TrendingUp size={13} className="text-emerald-400" /> Best confidence <span className="font-mono font-bold text-foreground">{wrapped.bestConfidence.key}</span></span>}
          {wrapped.confidenceCorrelation != null && (
            <span className="flex items-center gap-1.5">Confidence corr <span className="font-mono font-bold text-foreground">{wrapped.confidenceCorrelation.toFixed(2)}</span></span>
          )}
        </div>
      </div>
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-[10px] uppercase tracking-widest text-muted-foreground">{label}</p>
      <p className="font-mono text-2xl font-bold text-foreground leading-none mt-1">{value}</p>
    </div>
  );
}

function EmptyState({ text }: { text: string }) {
  return (
    <div className="rounded-2xl bg-[#0f0f0f]/60 p-12 text-center">
      <MessageSquareText className="mx-auto text-primary" size={28} />
      <h3 className="mt-3 font-serif text-base text-foreground">Nothing to review yet</h3>
      <p className="mt-1 text-xs text-muted-foreground max-w-md mx-auto">{text}</p>
    </div>
  );
}

function fmtRange(start: string, end: string): string {
  const s = new Date(start + 'T00:00:00Z');
  const e = new Date(end + 'T00:00:00Z');
  const fmt = (d: Date) => d.toLocaleDateString('en', { month: 'short', day: 'numeric' });
  return `${fmt(s)} – ${fmt(e)}, ${e.getUTCFullYear()}`;
}
