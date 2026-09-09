'use client';

// ── AI Analysis — BlackEclipse agentic analysis of the journal ───────────────
// Sends the deterministic analytics summary to the research engine and shows
// the AI interpretation. The AI interprets real computed stats — it never
// fabricates numbers.

import React, { useState } from 'react';
import { Sparkles, Loader2, X } from 'lucide-react';
import type { JournalAnalytics } from '@/lib/journal/types';
import { fmtR, fmtMoney } from './charts/echarts-container';

interface AiAnalysisProps {
  analytics: JournalAnalytics;
}

export function AiAnalysis({ analytics }: AiAnalysisProps) {
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const p = analytics.performance;
  const bestSymbol = analytics.bySymbol[0];
  const worstSymbol = analytics.bySymbol[analytics.bySymbol.length - 1];
  const bestSetup = analytics.bySetup[0];
  const bestSession = analytics.bySession[0];
  const leak = analytics.byEmotion.filter((e) => e.netR < 0).pop();

  const runAnalysis = async () => {
    setLoading(true);
    setError(null);
    setAnalysis(null);
    try {
      const summary = [
        `Trading journal performance summary:`,
        `- ${p.totalTrades} trades, ${(p.winRate * 100).toFixed(1)}% win rate, ${p.wins}W/${p.losses}L/${p.breakevens}B`,
        `- Net P&L ${fmtMoney(p.netPnl)}, Net R ${fmtR(p.netR)}, expectancy ${fmtR(p.expectancy)} per trade`,
        `- Profit factor ${p.profitFactor === Infinity ? '∞' : p.profitFactor.toFixed(2)}, max drawdown ${fmtR(-p.maxDrawdown)}`,
        `- Discipline score ${analytics.discipline.total}/100`,
        bestSymbol ? `- Best market: ${bestSymbol.key} (${fmtR(bestSymbol.netR)})` : '',
        worstSymbol && worstSymbol.netR < 0 ? `- Weakest market: ${worstSymbol.key} (${fmtR(worstSymbol.netR)})` : '',
        bestSetup ? `- Best setup: ${bestSetup.key} (${fmtR(bestSetup.netR)})` : '',
        bestSession ? `- Best session: ${bestSession.key} (${fmtR(bestSession.netR)})` : '',
        leak ? `- Biggest emotional leak: ${leak.key} (${fmtR(leak.netR)})` : '',
      ].filter(Boolean).join('\n');

      const res = await fetch('/api/agent/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `Analyze this trader's performance and give 3-5 concise, actionable insights. Be specific and reference the actual numbers. Focus on what's working, what's leaking money, and what to improve next.\n\n${summary}`,
        }),
      });
      const data = await res.json();
      if (data.success) setAnalysis(data.answer);
      else setError(data.error || 'Analysis failed');
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reach the analysis engine');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-2xl bg-[#0f0f0f]/60 p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-primary" />
          <h3 className="font-serif text-sm font-semibold text-foreground">AI Analysis</h3>
        </div>
        <button
          onClick={runAnalysis}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-primary/40 bg-primary/15 text-primary px-3 py-1.5 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50"
        >
          {loading ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
          {loading ? 'Analyzing…' : 'Analyze'}
        </button>
      </div>

      {error && (
        <div className="mb-2 flex items-center justify-between rounded-lg bg-rose-500/5 border border-rose-500/20 p-2.5 text-xs text-rose-400">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-rose-400/70 hover:text-rose-400 cursor-pointer"><X size={12} /></button>
        </div>
      )}

      {analysis ? (
        <p className="text-xs text-foreground/90 leading-relaxed whitespace-pre-wrap">{analysis}</p>
      ) : !loading && !error ? (
        <p className="text-xs text-muted-foreground italic">
          Run an AI analysis to get personalized insights from your trading data. The AI interprets your real computed statistics.
        </p>
      ) : null}
    </div>
  );
}
