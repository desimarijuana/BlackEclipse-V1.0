'use client';

// ── AiReview — reusable AI interpretation panel ───────────────────────────────
// Runs the journal agent with a query and shows the AI interpretation.
// Used by the trade detail (trade review), reviews (weekly), and insights
// (natural-language) tabs.

import React, { useState } from 'react';
import { Sparkles, Loader2, X } from 'lucide-react';

interface AiReviewProps {
  query: string;
  tradeId?: string;
  start?: string;
  end?: string;
  buttonLabel?: string;
  placeholder?: string;
  /** If true, show a text input for the user to type a custom query. */
  allowCustomQuery?: boolean;
}

export function AiReview({ query, tradeId, start, end, buttonLabel = 'Analyze', placeholder, allowCustomQuery = false }: AiReviewProps) {
  const [customQuery, setCustomQuery] = useState('');
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (q: string) => {
    setLoading(true);
    setError(null);
    setAnalysis(null);
    try {
      const res = await fetch('/api/journal/agent', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: q, tradeId, start, end }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || 'Analysis failed');
      setAnalysis(data.answer);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to reach the analysis engine');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-2xl glass-card p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Sparkles size={14} className="text-primary" />
          <h3 className="font-serif text-sm font-semibold text-foreground">AI Analysis</h3>
        </div>
        <button
          onClick={() => void run(customQuery || query)}
          disabled={loading}
          className="inline-flex items-center gap-1.5 rounded-lg border border-primary/40 bg-primary/15 text-primary px-3 py-1.5 text-xs font-bold hover:bg-primary/25 transition-all cursor-pointer disabled:opacity-50"
        >
          {loading ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
          {loading ? 'Analyzing…' : buttonLabel}
        </button>
      </div>

      {allowCustomQuery && (
        <div className="mb-3 flex items-center gap-2">
          <input
            value={customQuery}
            onChange={(e) => setCustomQuery(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && customQuery.trim()) void run(customQuery); }}
            placeholder={placeholder ?? 'Ask about your trading…'}
            className="flex-1 rounded-lg bg-background/60 border border-border/40 px-2.5 py-1.5 text-xs font-mono focus:ring-1 focus:ring-primary outline-none"
          />
        </div>
      )}

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
          Run an AI analysis to get personalized insights grounded in your real trading data.
        </p>
      ) : null}
    </div>
  );
}
