'use client';

// ── Market Regime control (top bar) ─────────────────────────────────────────
// The accessible, interactive front door to the Market Regime model. The Aurora
// backdrop stays decorative; THIS is the surface a keyboard/screen-reader user
// reaches. It opens a frosted-glass panel with the current regime, score,
// confidence and freshness; a per-component contribution breakdown; what changed
// since the last reading; supporting headlines; and real actions (open Market
// Overview, filter news, ask Eclipse, create a regime-change alert).
//
// All data comes from `GET /api/regime` via the shared `useRegime` hook — no
// second client-side data source.

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle, ArrowRight, Bell, HelpCircle,
  Minus, Newspaper, RefreshCw, TrendingDown, TrendingUp, X,
} from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { Dialog, DialogContent } from '@/components/ui/dialog';
import { useRegime } from '@/lib/regime/client';
import { useRegimeScopeStore, useHydrateRegimeScope } from '@/lib/regime/store';
import { REGIME_BLURBS } from '@/lib/regime/visuals';
import { formatAge, REGIME_LABELS } from '@/lib/regime/scoring';
import type { RegimeComponent, RegimeId, RegimeResult, RegimeScope } from '@/lib/regime/types';
import { createQuickAlert } from '@/lib/alerts/quick-alert';
import { dataHub } from '@/lib/workspace/data-hub';
import { cn } from '@/lib/utils';

const REGIME_TONE: Record<RegimeId, string> = {
  risk_on_broadening: 'text-emerald-400',
  fragile_rally: 'text-amber-300',
  mixed: 'text-muted-foreground',
  risk_off: 'text-rose-400',
  narrative_shock: 'text-fuchsia-400',
  unavailable: 'text-muted-foreground/70',
};

const SCOPES: Array<{ id: RegimeScope; label: string }> = [
  { id: 'selected', label: 'Selected' },
  { id: 'us', label: 'US' },
  { id: 'global', label: 'Global' },
];

interface LastReading {
  regime: RegimeId;
  score: number | null;
  at: number;
}

const LAST_KEY = 'be_regime_last_v1';

function loadLast(topicId: string): LastReading | null {
  if (typeof window === 'undefined') return null;
  try {
    const raw = window.localStorage.getItem(`${LAST_KEY}:${topicId}`);
    return raw ? (JSON.parse(raw) as LastReading) : null;
  } catch {
    return null;
  }
}

function saveLast(topicId: string, reading: LastReading) {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(`${LAST_KEY}:${topicId}`, JSON.stringify(reading));
  } catch {
    /* ignore quota */
  }
}

function ScoreIcon({ score }: { score: number | null }) {
  if (score === null) return <Minus className="w-3.5 h-3.5" />;
  if (score > 0.05) return <TrendingUp className="w-3.5 h-3.5" />;
  if (score < -0.05) return <TrendingDown className="w-3.5 h-3.5" />;
  return <Minus className="w-3.5 h-3.5" />;
}

function ContributionRow({ c }: { c: RegimeComponent }) {
  const pct = Math.round(c.usedWeight * 100);
  const barPct = c.score === null ? 0 : Math.round(Math.abs(c.score) * 100);
  const tone = c.score === null ? 'bg-muted-foreground/20' : c.score >= 0 ? 'bg-emerald-400/70' : 'bg-rose-400/70';
  return (
    <div className="glass-card-subtle rounded-lg px-3 py-2" title={c.detail}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs text-foreground/90 flex items-center gap-1.5">
          <ScoreIcon score={c.available ? c.score : null} />
          {c.label}
        </span>
        <span className="text-[11px] font-mono text-muted-foreground">
          {c.available ? `${c.score! >= 0 ? '+' : ''}${c.score!.toFixed(2)}` : c.stale ? 'stale' : 'n/a'}
          {c.available ? ` · w ${pct}%` : ''}
        </span>
      </div>
      <div className="mt-1.5 h-1 rounded-full bg-white/5 overflow-hidden">
        <div className={cn('h-full rounded-full', tone)} style={{ width: `${barPct}%` }} />
      </div>
      <p className="mt-1 text-[10px] text-muted-foreground/70 leading-snug">
        {c.source} · {c.available ? `conf ${Math.round(c.confidence * 100)}%` : c.stale ? 'excluded (stale)' : 'unavailable'}
        {c.available && c.asOf ? ` · ${formatAge(Date.now() - c.asOf)}` : ''}
      </p>
    </div>
  );
}

function diffText(prev: LastReading | null, result: RegimeResult): string {
  if (!prev) return 'First reading on this device — no prior update to compare.';
  if (prev.regime !== result.regime) {
    return `Regime moved ${REGIME_LABELS[prev.regime]} → ${result.label}.`;
  }
  if (prev.score != null && result.score != null) {
    const d = result.score - prev.score;
    if (Math.abs(d) < 0.03) return `Still ${result.label}; score steady.`;
    return `Still ${result.label}; score ${d > 0 ? 'rose' : 'fell'} ${Math.abs(d).toFixed(2)} (${prev.score.toFixed(2)} → ${result.score.toFixed(2)}).`;
  }
  return `Still ${result.label}.`;
}

export function MarketRegimeControl() {
  const [toast, setToast] = useState<string | null>(null);
  useHydrateRegimeScope();
  const scope = useRegimeScopeStore((s) => s.scope);
  const setScope = useRegimeScopeStore((s) => s.setScope);
  const open = useRegimeScopeStore((s) => s.panelOpen);
  const setOpen = useRegimeScopeStore((s) => s.setPanelOpen);
  const { result, topicId, entry } = useRegime();

  // Track "what changed since last update" per topic.
  const prevRef = useRef<LastReading | null>(null);
  const [diff, setDiff] = useState<string>('');
  useEffect(() => {
    if (!result) return;
    const prev = prevRef.current ?? loadLast(topicId);
    setDiff(diffText(prev, result));
    const reading: LastReading = { regime: result.regime, score: result.score, at: result.builtAt };
    prevRef.current = reading;
    saveLast(topicId, reading);
  }, [result, topicId]);

  useEffect(() => {
    if (!toast) return;
    const t = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(t);
  }, [toast]);

  const loading = !result && entry.source !== 'UNAVAILABLE';
  const label = result?.label ?? 'Market Regime';
  const tone = result ? REGIME_TONE[result.regime] : 'text-muted-foreground';

  const ageText = useMemo(
    () => (result?.asOf ? formatAge(Date.now() - result.asOf) : 'no data'),
    [result],
  );

  const openMarketOverview = () => {
    window.dispatchEvent(new CustomEvent('be:navigate', { detail: { tab: 'discovery' } }));
    setOpen(false);
  };
  const openNews = () => {
    window.dispatchEvent(new CustomEvent('be:navigate', { detail: { tab: 'news' } }));
    setOpen(false);
  };
  const askEclipse = () => {
    const r = result;
    const prompt = r
      ? `Explain the current market regime for ${r.market}. It reads "${r.label}" with score ${r.score ?? 'n/a'} and confidence ${Math.round(r.confidence * 100)}%. Break down each input (price & breadth, volatility, macro, news) and tell me what would change the regime.`
      : 'Explain the current market regime and why the reading is unavailable.';
    window.dispatchEvent(new CustomEvent('be:ask-eclipse', { detail: { prompt } }));
    setOpen(false);
  };
  const createAlert = async () => {
    const sym = result?.benchmarkSymbol;
    if (!sym) {
      setToast('No benchmark instrument to watch for this scope.');
      return;
    }
    const res = await createQuickAlert(sym, 3);
    setToast(res.ok ? `Regime-change alert created on ${sym} (±3%).` : `Could not create alert: ${res.error}`);
  };

  const refresh = () => {
    void dataHub.refresh(topicId);
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent
        className="glass-card-strong sm:max-w-lg max-h-[85dvh] overflow-y-auto rounded-2xl text-foreground"
        showCloseButton={false}
      >
        <div className="flex items-start justify-between gap-3">
          <div>
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground/60">Market Regime</p>
            <h2 className={cn('text-lg font-semibold leading-tight', tone)}>{label}</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">
              {result ? REGIME_BLURBS[result.regime] : loading ? 'Loading…' : 'No trustworthy reading.'}
            </p>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            <button
              onClick={refresh}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent/40 cursor-pointer"
              aria-label="Refresh regime reading"
            >
              <RefreshCw className={cn('w-4 h-4', loading && 'animate-spin')} />
            </button>
            <button
              onClick={() => setOpen(false)}
              className="p-1.5 rounded-lg text-muted-foreground hover:text-foreground hover:bg-accent/40 cursor-pointer"
              aria-label="Close market regime"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Scope selector */}
        <div
          role="group"
          aria-label="Regime scope"
          className="glass-card-subtle inline-flex rounded-xl p-0.5 self-start"
        >
          {SCOPES.map((s) => (
            <button
              key={s.id}
              type="button"
              onClick={() => setScope(s.id)}
              aria-pressed={scope === s.id}
              className={cn(
                'px-3 py-1 rounded-lg text-[11px] font-mono transition-colors cursor-pointer',
                scope === s.id ? 'bg-primary/15 text-primary' : 'text-muted-foreground hover:text-foreground',
              )}
            >
              {s.label}
            </button>
          ))}
        </div>

        {/* Headline metrics */}
        {result && (
          <div className="grid grid-cols-3 gap-2">
            <div className="glass-card-subtle rounded-lg px-3 py-2">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground/60">Score</p>
              <p className={cn('text-sm font-mono', tone)}>
                {result.score === null ? '—' : `${result.score >= 0 ? '+' : ''}${result.score.toFixed(2)}`}
              </p>
            </div>
            <div className="glass-card-subtle rounded-lg px-3 py-2">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground/60">Confidence</p>
              <p className="text-sm font-mono">{Math.round(result.confidence * 100)}%</p>
            </div>
            <div className="glass-card-subtle rounded-lg px-3 py-2">
              <p className="text-[10px] uppercase tracking-wider text-muted-foreground/60">Freshness</p>
              <p className="text-sm font-mono">{ageText}</p>
            </div>
          </div>
        )}

        {result?.regime === 'unavailable' && (
          <div className="flex items-start gap-2 rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2">
            <AlertTriangle className="w-4 h-4 text-amber-300 shrink-0 mt-0.5" />
            <p className="text-[11px] text-amber-200/90">
              Core market inputs are missing or stale, so no regime is asserted. Missing data lowers confidence rather than defaulting to neutral.
            </p>
          </div>
        )}

        {/* What changed */}
        {result && (
          <div className="glass-card-subtle rounded-lg px-3 py-2">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground/60">What changed since last update</p>
            <p className="text-xs text-foreground/85 mt-0.5">{diff}</p>
          </div>
        )}

        {/* Contribution breakdown */}
        {result && (
          <div className="flex flex-col gap-2">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground/60">
              Contributions ({Math.round(result.coverage * 100)}% input coverage)
            </p>
            {result.components.map((c) => <ContributionRow key={c.id} c={c} />)}
          </div>
        )}

        {/* Drivers */}
        {result && result.drivers.length > 0 && (
          <div className="flex flex-col gap-1.5">
            <p className="text-[10px] uppercase tracking-wider text-muted-foreground/60">Market drivers</p>
            {result.drivers.slice(0, 5).map((d, i) => (
              <div key={i} className="flex items-start gap-2 glass-card-subtle rounded-lg px-3 py-2">
                <span
                  className={cn(
                    'mt-1 w-1.5 h-1.5 rounded-full shrink-0',
                    d.sentiment === 'bullish' ? 'bg-emerald-400' : d.sentiment === 'bearish' ? 'bg-rose-400' : 'bg-muted-foreground/50',
                  )}
                  aria-hidden
                />
                <div className="min-w-0">
                  <p className="text-[11px] text-foreground/85 leading-snug">{d.headline}</p>
                  <p className="text-[10px] text-muted-foreground/60">{d.source}{d.at ? ` · ${formatAge(Date.now() - d.at)}` : ''}</p>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-wrap gap-2 pt-1">
          <Button variant="outline" size="sm" onClick={openMarketOverview} className="gap-1.5">
            <ArrowRight className="w-3.5 h-3.5" /> Market Overview
          </Button>
          <Button variant="outline" size="sm" onClick={openNews} className="gap-1.5">
            <Newspaper className="w-3.5 h-3.5" /> Relevant news
          </Button>
          <Button variant="outline" size="sm" onClick={askEclipse} className="gap-1.5">
            <HelpCircle className="w-3.5 h-3.5" /> Ask Eclipse
          </Button>
          <Button variant="outline" size="sm" onClick={createAlert} className="gap-1.5">
            <Bell className="w-3.5 h-3.5" /> Alert on regime change
          </Button>
        </div>

        {toast && (
          <p className="text-[11px] text-primary" role="status">{toast}</p>
        )}
        <p className="text-[10px] text-muted-foreground/50">
          Source: JDDS. Data age and source shown per component; stale or missing inputs are excluded.
        </p>
      </DialogContent>
    </Dialog>
  );
}
