'use client';

import React, { useState, useEffect } from 'react';
import { CalendarClock, Loader2, Sparkles, Flame } from 'lucide-react';

interface CalendarEvent {
  id: string;
  date: string;
  country: string;
  title: string;
  importance: 'high' | 'medium' | 'low';
  actual: string | null;
  forecast: string | null;
  previous: string | null;
}

interface ResearchResult {
  answer: string;
  verdict?: string;
  confidence?: number;
}

const IMPORTANCE_STYLES: Record<CalendarEvent['importance'], { dot: string; pill: string }> = {
  high: { dot: 'bg-rose-400', pill: 'bg-rose-500/10 text-rose-400 border-rose-500/30' },
  medium: { dot: 'bg-amber-400', pill: 'bg-amber-400/10 text-amber-400 border-amber-400/30' },
  low: { dot: 'bg-neutral-400', pill: 'bg-neutral-400/10 text-neutral-400 border-neutral-400/30' },
};

export function CalendarView() {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [source, setSource] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [analyzedId, setAnalyzedId] = useState<string | null>(null);
  const [research, setResearch] = useState<ResearchResult | null>(null);
  const [researchLoading, setResearchLoading] = useState(false);

  useEffect(() => {
    void (async () => {
      try {
        const res = await fetch('/api/economics/calendar');
        const d = await res.json();
        setEvents(d.events || []);
        setSource(d.source || '');
      } catch {
        setError('Failed to load the economic calendar');
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const analyzeEvent = async (e: CalendarEvent) => {
    setAnalyzedId(e.id);
    setResearchLoading(true);
    setResearch(null);
    try {
      const res = await fetch('/api/agent/research', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          query: `Analyze this upcoming economic release for markets: "${e.title}" (${e.country})${
            e.previous ? `, previous: ${e.previous}` : ''
          }${e.forecast ? `, forecast: ${e.forecast}` : ''}${e.actual ? `, actual: ${e.actual}` : ''}. What's at stake, which assets react most, and how should traders position?`,
          market: 'US',
        }),
      });
      const d = await res.json();
      if (d.success) setResearch({ answer: d.answer, verdict: d.verdict, confidence: d.confidence });
      else setError(d.error || 'Research failed');
    } catch {
      setError('Failed to reach the research engine');
    } finally {
      setResearchLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-16 gap-2 text-muted-foreground text-xs font-mono">
        <Loader2 size={14} className="animate-spin" /> Loading economic calendar…
      </div>
    );
  }

  if (error && events.length === 0) {
    return <div className="p-4 rounded-xl bg-rose-500/5 border border-rose-500/30 text-[12px] text-rose-400 font-mono">{error}</div>;
  }

  return (
    <div className="flex flex-col gap-3">
      <p className="text-[10px] font-mono text-muted-foreground/70 px-1">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-emerald-400 mr-1.5 align-middle" />
        Economic Calendar{source === 'schedule-fallback' ? ' · recurring schedule (mirror offline)' : ` · ${events.length} releases`}
      </p>

      {events.length === 0 && (
        <div className="py-8 text-center text-[12px] font-mono text-muted-foreground border border-dashed border-border/25 rounded-xl">
          No upcoming releases found.
        </div>
      )}

      {events.map((e) => {
        const style = IMPORTANCE_STYLES[e.importance];
        const when = new Date(e.date);
        return (
          <div
            key={e.id}
            className={`rounded-xl border p-3.5 bg-[#0f0f0f]/60 backdrop-blur-xl flex flex-col md:flex-row md:items-center gap-3 transition-all ${
              e.importance === 'high' ? 'border-rose-500/25 hover:border-rose-500/50' : 'border-border/10 hover:border-primary/40'
            }`}
          >
            <div className="flex items-center gap-2.5 min-w-[170px] shrink-0">
              <span className={`w-2 h-2 rounded-full shrink-0 ${style.dot} ${e.importance === 'high' ? 'animate-pulse' : ''}`} />
              <div>
                <p className="text-[12px] font-mono font-bold text-foreground">{when.toUTCString().slice(5, 22)}</p>
                <p className="text-[9px] font-mono text-muted-foreground">{when.toISOString().slice(0, 16).replace('T', ' ')} UTC</p>
              </div>
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] font-bold font-mono text-primary bg-primary/10 border border-primary/20 px-1.5 py-0.5 rounded">{e.country}</span>
                <p className="text-[13px] font-semibold text-foreground flex items-center gap-1.5">
                  {e.title}
                  {e.importance === 'high' && <Flame size={12} className="text-rose-400" />}
                </p>
              </div>
              {(e.actual || e.forecast || e.previous) && (
                <div className="flex gap-3 mt-1 font-mono text-[10px] text-muted-foreground">
                  {e.actual && <span>actual <span className="text-emerald-400 font-bold">{e.actual}</span></span>}
                  {e.forecast && <span>forecast <span className="text-foreground font-bold">{e.forecast}</span></span>}
                  {e.previous && <span>prev <span className="text-muted-foreground">{e.previous}</span></span>}
                </div>
              )}
            </div>
            <span className={`text-[9px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border shrink-0 w-fit ${style.pill}`}>
              {e.importance}
            </span>
            <button
              onClick={() => void analyzeEvent(e)}
              disabled={researchLoading && analyzedId === e.id}
              className="h-8 px-3 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 text-[11px] font-bold inline-flex items-center gap-1.5 cursor-pointer transition-colors disabled:opacity-40 shrink-0"
            >
              {researchLoading && analyzedId === e.id ? <Loader2 size={11} className="animate-spin" /> : <Sparkles size={11} />} Analyze
            </button>
          </div>
        );
      })}

      {research && (
        <div className="p-4 rounded-xl bg-primary/[0.04] border border-primary/20 animate-fade-in-up">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <CalendarClock size={13} className="text-primary" />
            <span className="text-[11px] font-bold text-primary uppercase tracking-wider">Event Analysis</span>
            {research.verdict && (
              <span className="text-[10px] font-bold font-mono uppercase px-2 py-0.5 rounded-full bg-primary/10 text-primary border border-primary/20">{research.verdict}</span>
            )}
            {typeof research.confidence === 'number' && (
              <span className="text-[10px] font-mono text-muted-foreground">confidence {Math.round(research.confidence * 100)}%</span>
            )}
          </div>
          <p className="text-[12px] text-foreground/90 leading-relaxed whitespace-pre-wrap">{research.answer}</p>
        </div>
      )}
    </div>
  );
}