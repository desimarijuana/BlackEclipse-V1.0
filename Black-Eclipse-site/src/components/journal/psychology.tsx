'use client';

// ── Journal Psychology — behavioral analysis ─────────────────────────────────
// Emotion performance, confidence correlation, and biggest behavioral leaks.

import React, { useMemo } from 'react';
import { Brain, AlertTriangle, Target } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { JournalAnalytics, TradeRecord } from '@/lib/journal/types';
import { DimensionBarChart, fmtR } from './charts';

interface PsychologyProps {
  analytics: JournalAnalytics | null;
  trades: TradeRecord[];
}

export function JournalPsychology({ analytics, trades }: PsychologyProps) {
  const leaks = useMemo<{ worstMistake?: [string, number]; worstEmotion?: [string, number] }>(() => {
    const byMistake = new Map<string, number>();
    const byEmotionNeg = new Map<string, number>();
    for (const t of trades) {
      if (t.status !== 'closed') continue;
      if (t.emotion && t.rMultiple < 0) byEmotionNeg.set(t.emotion, (byEmotionNeg.get(t.emotion) ?? 0) + t.rMultiple);
      if (t.mistakes) {
        try {
          const arr = JSON.parse(t.mistakes) as string[];
          for (const m of arr) byMistake.set(m, (byMistake.get(m) ?? 0) + t.rMultiple);
        } catch { /* ignore */ }
      }
    }
    const worstMistake = [...byMistake.entries()].sort((a, b) => a[1] - b[1])[0];
    const worstEmotion = [...byEmotionNeg.entries()].sort((a, b) => a[1] - b[1])[0];
    return { worstMistake, worstEmotion };
  }, [trades]);

  if (!analytics || analytics.performance.totalTrades === 0) {
    return (
      <div className="rounded-2xl bg-[#0f0f0f]/60 p-12 text-center">
        <Brain className="mx-auto text-primary" size={28} />
        <h3 className="mt-3 font-serif text-base text-foreground">No psychology data yet</h3>
        <p className="mt-1 text-xs text-muted-foreground">Record emotions and confidence on your trades to see behavioral patterns.</p>
      </div>
    );
  }

  const corr = analytics.confidenceCorrelation;
  const corrTone = corr == null ? 'neutral' : corr > 0.2 ? 'pos' : corr < -0.2 ? 'neg' : 'neutral';

  return (
    <div className="flex flex-col gap-5">
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* Emotion performance */}
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <DimensionBarChart rows={analytics.byEmotion} title="Performance by Emotion" hint="NET R" height={Math.max(160, analytics.byEmotion.length * 30)} />
        </div>

        {/* Confidence correlation */}
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <DimensionBarChart rows={analytics.byConfidence} title="Performance by Confidence" hint="NET R" height={Math.max(160, analytics.byConfidence.length * 30)} />
        </div>
      </div>

      {/* Correlation readout */}
      <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
        <div className="flex items-center gap-2 mb-3">
          <Target size={14} className="text-primary" />
          <h3 className="font-serif text-sm font-semibold text-foreground">Confidence vs Outcome</h3>
        </div>
        {corr == null ? (
          <p className="text-xs text-muted-foreground italic">Not enough confidence-tagged trades to compute a correlation (need at least 3).</p>
        ) : (
          <div className="flex items-center gap-3">
            <span className={cn(
              'font-mono text-3xl font-bold',
              corrTone === 'pos' ? 'text-emerald-400' : corrTone === 'neg' ? 'text-rose-400' : 'text-foreground',
            )}>
              {corr.toFixed(2)}
            </span>
            <p className="text-xs text-muted-foreground leading-relaxed">
              {corrTone === 'pos'
                ? 'Your higher-confidence trades tend to perform better. Confidence is a reliable signal for you.'
                : corrTone === 'neg'
                  ? 'Your lower-confidence trades actually perform better. Be wary of overconfidence.'
                  : 'There is no meaningful relationship between your confidence and outcomes.'}
            </p>
          </div>
        )}
      </div>

      {/* Biggest leaks */}
      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={14} className="text-rose-400" />
            <h3 className="font-serif text-sm font-semibold text-foreground">Most Costly Emotional State</h3>
          </div>
          {leaks.worstEmotion ? (
            <div className="flex items-center justify-between">
              <span className="font-mono text-sm font-bold text-foreground">{leaks.worstEmotion[0]}</span>
              <span className="font-mono text-sm font-bold text-rose-400">{fmtR(leaks.worstEmotion[1])}</span>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground italic">No losing trades tagged with an emotion.</p>
          )}
        </div>

        <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertTriangle size={14} className="text-rose-400" />
            <h3 className="font-serif text-sm font-semibold text-foreground">Most Costly Mistake</h3>
          </div>
          {leaks.worstMistake ? (
            <div className="flex items-center justify-between">
              <span className="font-mono text-sm font-bold text-foreground">{leaks.worstMistake[0]}</span>
              <span className="font-mono text-sm font-bold text-rose-400">{fmtR(leaks.worstMistake[1])}</span>
            </div>
          ) : (
            <p className="text-xs text-muted-foreground italic">No mistakes recorded on losing trades.</p>
          )}
        </div>
      </div>
    </div>
  );
}
