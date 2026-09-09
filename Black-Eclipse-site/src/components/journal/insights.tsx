'use client';

// ── Journal Insights — BlackEclipse-generated behavioral insights ────────────
// Deterministic observations derived from the analytics engine. AI will later
// interpret these, but the underlying facts are always computed, never
// fabricated.

import React, { useMemo } from 'react';
import { Sparkles, TrendingUp, TrendingDown, AlertTriangle, Lightbulb } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { JournalAnalytics } from '@/lib/journal/types';
import { fmtR } from './charts/echarts-container';

interface InsightsProps {
  analytics: JournalAnalytics | null;
}

interface Insight {
  kind: 'positive' | 'negative' | 'neutral';
  icon: React.ComponentType<{ size?: number; className?: string }>;
  title: string;
  body: string;
}

export function JournalInsights({ analytics }: InsightsProps) {
  const insights = useMemo<Insight[]>(() => {
    if (!analytics) return [];
    const p = analytics.performance;
    const out: Insight[] = [];

    // Best / worst symbol.
    if (analytics.bySymbol.length > 0) {
      const best = analytics.bySymbol[0];
      const worst = analytics.bySymbol[analytics.bySymbol.length - 1];
      if (best.netR > 0) out.push({ kind: 'positive', icon: TrendingUp, title: `Strongest market: ${best.key}`, body: `${best.key} is your best market at ${fmtR(best.netR)} across ${best.trades} trades (${(best.winRate * 100).toFixed(0)}% win rate).` });
      if (worst.netR < 0) out.push({ kind: 'negative', icon: TrendingDown, title: `Weakest market: ${worst.key}`, body: `${worst.key} has cost you ${fmtR(worst.netR)} across ${worst.trades} trades. Consider reducing exposure here.` });
    }

    // Best / worst session.
    if (analytics.bySession.length > 0) {
      const best = analytics.bySession[0];
      if (best.netR > 0) out.push({ kind: 'positive', icon: TrendingUp, title: `Best session: ${best.key}`, body: `You perform best during ${best.key} (${fmtR(best.netR)}). Prioritize this session.` });
    }

    // Emotional leak.
    const negativeEmotions = analytics.byEmotion.filter((e) => e.netR < 0);
    if (negativeEmotions.length > 0) {
      const worst = negativeEmotions[negativeEmotions.length - 1];
      out.push({ kind: 'negative', icon: AlertTriangle, title: `Behavioral leak: ${worst.key}`, body: `Trading while ${worst.key.toLowerCase()} has cost you ${fmtR(worst.netR)}. This is your biggest emotional leak.` });
    }

    // Risk violations.
    if (p.riskViolations > 0) {
      out.push({ kind: 'negative', icon: AlertTriangle, title: 'Risk violations detected', body: `${p.riskViolations} trade(s) exceeded your 1% risk rule. This is a discipline leak.` });
    }

    // Overtrading.
    if (p.totalTrades > 0 && p.totalTrades / Math.max(1, analytics.days.length) > 3) {
      out.push({ kind: 'neutral', icon: Lightbulb, title: 'High trade frequency', body: `You average ${(p.totalTrades / Math.max(1, analytics.days.length)).toFixed(1)} trades/day. Overtrading is a common leak — consider fewer, higher-quality setups.` });
    }

    // Discipline.
    if (p.totalTrades > 0) {
      const d = analytics.discipline.total;
      if (d >= 80) out.push({ kind: 'positive', icon: Sparkles, title: 'Strong discipline', body: `Your Eclipse Discipline Score is ${d}/100. You are following your rules well.` });
      else if (d < 50) out.push({ kind: 'negative', icon: AlertTriangle, title: 'Discipline needs work', body: `Your Eclipse Discipline Score is ${d}/100. Focus on risk and stop compliance.` });
    }

    // Expectancy.
    if (p.totalTrades > 0) {
      out.push({
        kind: p.expectancy >= 0 ? 'positive' : 'negative',
        icon: p.expectancy >= 0 ? TrendingUp : TrendingDown,
        title: `Expectancy: ${fmtR(p.expectancy)} per trade`,
        body: `Across ${p.totalTrades} trades, your average edge is ${fmtR(p.expectancy)} per trade. ${p.expectancy >= 0 ? 'Your system has a positive edge.' : 'Your system is currently losing money per trade.'}`,
      });
    }

    return out;
  }, [analytics]);

  if (!analytics || analytics.performance.totalTrades === 0) {
    return (
      <div className="rounded-2xl bg-[#0f0f0f]/60 p-12 text-center">
        <Sparkles className="mx-auto text-primary" size={28} />
        <h3 className="mt-3 font-serif text-base text-foreground">No insights yet</h3>
        <p className="mt-1 text-xs text-muted-foreground">Add trades and BlackEclipse will surface behavioral patterns.</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-5">
      <div>
        <h2 className="font-serif text-lg font-semibold text-foreground">BlackEclipse Insights</h2>
        <p className="text-xs text-muted-foreground mt-0.5">Deterministic observations from your trading data.</p>
      </div>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {insights.map((ins, i) => {
          const Icon = ins.icon;
          return (
            <div
              key={i}
              className={cn(
                'rounded-2xl border p-4',
                ins.kind === 'positive' ? 'border-emerald-500/15 bg-emerald-500/5'
                  : ins.kind === 'negative' ? 'border-rose-500/15 bg-rose-500/5'
                    : 'border-white/10 bg-[#0f0f0f]/60',
              )}
            >
              <div className="flex items-center gap-2 mb-1.5">
                <Icon size={14} className={ins.kind === 'positive' ? 'text-emerald-400' : ins.kind === 'negative' ? 'text-rose-400' : 'text-primary'} />
                <h3 className="font-serif text-sm font-semibold text-foreground">{ins.title}</h3>
              </div>
              <p className="text-xs text-muted-foreground leading-relaxed">{ins.body}</p>
            </div>
          );
        })}
      </div>
    </div>
  );
}
