'use client';

import React, { useState, useEffect } from 'react';
import { Loader2, Sparkles, ExternalLink } from '@/lib/icons';

interface CalendarEvent {
  id: string;
  date: string;
  time?: string | null;
  country: string;
  title: string;
  importance: 'high' | 'medium' | 'low';
  actual: string | null;
  forecast: string | null;
  previous: string | null;
  confirmed?: boolean;
  source?: 'mirror' | 'official' | 'web';
  url?: string | null;
}

interface ResearchResult {
  answer: string;
  verdict?: string;
  confidence?: number;
}

type Filter = 'all' | 'high' | 'medium' | 'low';

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'all', label: 'All' },
  { id: 'high', label: 'High' },
  { id: 'medium', label: 'Medium' },
  { id: 'low', label: 'Low' },
];

const IMP_DOT: Record<CalendarEvent['importance'], string> = {
  high: 'bg-rose-400',
  medium: 'bg-amber-400',
  low: 'bg-neutral-400',
};

const IMP_LABEL: Record<CalendarEvent['importance'], string> = {
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

/**
 * Match an indicator focus token (from global search, e.g. 'NFP', 'CPI',
 * 'FOMC', 'Unemployment') against event titles. Mirrors `EVENT_KEYWORDS` in
 * `src/lib/search/events.ts` so the palette focus and the calendar agree.
 */
const FOCUS_PATTERNS: Record<string, RegExp> = {
  nfp: /nonfarm|non-farm|payroll|nfp/i,
  cpi: /cpi|consumer price/i,
  gdp: /gdp|gross domestic/i,
  fomc: /fomc|federal reserve|interest rate decision/i,
  pmi: /pmi|ism|purchasing managers/i,
  unemployment: /unemployment|jobless/i,
  unemp: /unemployment|jobless/i,
  ecb: /ecb|european central bank/i,
  boe: /boe|bank of england/i,
  boj: /boj|bank of japan/i,
};

export function CalendarView({ focus }: { focus?: string } = {}) {
  const [events, setEvents] = useState<CalendarEvent[]>([]);
  const [source, setSource] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
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

  const visible = filter === 'all' ? events : events.filter((e) => e.importance === filter);

  // Focus highlight: when global search dispatched `focus: 'NFP'`, ring those
  // rows and reorder them to the top so the user sees the target immediately.
  const focusRe = focus ? FOCUS_PATTERNS[focus.toLowerCase()] : undefined;
  const isFocused = (e: CalendarEvent) => !!focusRe && focusRe.test(e.title);
  const ordered = focusRe
    ? [...visible].sort((a, b) => Number(isFocused(b)) - Number(isFocused(a)))
    : visible;

  const sourceLabel =
    source === 'mirror+official'
      ? 'mirror + official schedules'
      : source === 'official'
        ? 'official schedules only'
        : source === 'mirror'
          ? 'release mirror'
          : source === 'cached'
            ? 'cached official schedule'
            : source === 'unavailable'
              ? 'sources unavailable'
              : '';

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between flex-wrap gap-2">
        <p className="text-[10px] font-mono text-muted-foreground/70">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-primary mr-1.5 align-middle" />
          Economic Calendar{sourceLabel ? ` · ${sourceLabel}` : ''} · {events.length} releases
        </p>
        <div className="flex flex-wrap gap-1.5" role="group" aria-label="Calendar filters">
          {FILTERS.map((f) => (
            <button
              key={f.id}
              onClick={() => setFilter(f.id)}
              aria-pressed={filter === f.id}
              className={`h-8 px-3.5 rounded-full border font-mono text-[11px] transition-colors cursor-pointer ${
                filter === f.id
                  ? 'bg-primary/10 border-primary text-primary'
                  : 'border-border/30 text-muted-foreground hover:border-foreground hover:text-foreground'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {visible.length === 0 && (
        <div className="py-8 text-center text-[12px] font-mono text-muted-foreground border border-dashed border-border/25 rounded-xl">
          No upcoming releases found.
        </div>
      )}

      {focus && (
        <p className="text-[11px] font-mono text-primary/80">
          Showing <span className="font-bold">{focus.toUpperCase()}</span> releases first.
        </p>
      )}

      {visible.length > 0 && (
        <div className="rounded-xl glass-card border border-border/10 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-border/10">
                  <th className="text-left px-3 py-2.5 font-mono text-[11px] uppercase tracking-[0.05em] text-muted-foreground font-medium">Date</th>
                  <th className="text-left px-3 py-2.5 font-mono text-[11px] uppercase tracking-[0.05em] text-muted-foreground font-medium">Time</th>
                  <th className="text-left px-3 py-2.5 font-mono text-[11px] uppercase tracking-[0.05em] text-muted-foreground font-medium">Country</th>
                  <th className="text-left px-3 py-2.5 font-mono text-[11px] uppercase tracking-[0.05em] text-muted-foreground font-medium">Event</th>
                  <th className="text-left px-3 py-2.5 font-mono text-[11px] uppercase tracking-[0.05em] text-muted-foreground font-medium">Importance</th>
                  <th className="text-right px-3 py-2.5 font-mono text-[11px] uppercase tracking-[0.05em] text-muted-foreground font-medium">Actual</th>
                  <th className="text-right px-3 py-2.5 font-mono text-[11px] uppercase tracking-[0.05em] text-muted-foreground font-medium">Forecast</th>
                  <th className="text-right px-3 py-2.5 font-mono text-[11px] uppercase tracking-[0.05em] text-muted-foreground font-medium">Previous</th>
                  <th className="text-right px-3 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {ordered.map((e) => {
                  const dateOnly = /^\d{4}-\d{2}-\d{2}$/.test(e.date);
                  const when = new Date(dateOnly ? `${e.date}T00:00:00Z` : e.date);
                  const day = when.toUTCString().slice(0, 16);
                  const time = e.time ?? (dateOnly ? '—' : `${when.toISOString().slice(11, 16)} UTC`);
                  const focused = isFocused(e);
                  return (
                    <tr key={e.id} className={`border-b border-border/10 last:border-0 hover:bg-accent/20 transition-colors ${focused ? 'bg-primary/[0.07] ring-1 ring-inset ring-primary/30' : ''}`}>
                      <td className="px-3 py-2.5 font-mono font-semibold text-foreground whitespace-nowrap">{day}</td>
                      <td className="px-3 py-2.5 font-mono text-muted-foreground whitespace-nowrap">{time}</td>
                      <td className="px-3 py-2.5 font-mono font-semibold text-foreground">{e.country}</td>
                      <td className="px-3 py-2.5 text-foreground">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <span>{e.title}</span>
                          {e.confirmed === false && (
                            <span className="rounded border border-amber-400/30 bg-amber-400/10 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wide text-amber-300">
                              Tentative
                            </span>
                          )}
                          {e.source === 'official' && e.url && (
                            <a
                              href={e.url}
                              target="_blank"
                              rel="noreferrer"
                              title="Official schedule"
                              className="text-muted-foreground hover:text-primary"
                            >
                              <ExternalLink size={10} />
                            </a>
                          )}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 whitespace-nowrap">
                        <span className="inline-flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
                          <span className={`w-2 h-2 rounded-sm ${IMP_DOT[e.importance]}`} />
                          {IMP_LABEL[e.importance]}
                        </span>
                      </td>
                      <td className="px-3 py-2.5 text-right font-mono text-foreground">{e.actual ?? '—'}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-muted-foreground">{e.forecast ?? '—'}</td>
                      <td className="px-3 py-2.5 text-right font-mono text-muted-foreground">{e.previous ?? '—'}</td>
                      <td className="px-3 py-2.5 text-right whitespace-nowrap">
                        <button
                          onClick={() => void analyzeEvent(e)}
                          disabled={researchLoading && analyzedId === e.id}
                          className="h-7 px-2.5 rounded-lg bg-primary/10 hover:bg-primary/20 text-primary border border-primary/20 text-[11px] font-bold inline-flex items-center gap-1 cursor-pointer transition-colors disabled:opacity-40"
                        >
                          {researchLoading && analyzedId === e.id ? <Loader2 size={10} className="animate-spin" /> : <Sparkles size={10} />} Analyze
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="flex items-center gap-2 text-[12px] text-muted-foreground">
        <span className="w-1.5 h-1.5 rounded-full bg-primary" />
        <span>Dates come from the release mirror plus official central-bank schedules (FOMC dates are read from federalreserve.gov). Cells stay blank until a real value exists — no fabricated dates or numbers.</span>
      </div>

      {research && (
        <div className="p-4 rounded-xl bg-primary/[0.04] border border-primary/20 animate-fade-in-up">
          <div className="flex items-center gap-2 mb-2 flex-wrap">
            <Sparkles size={13} className="text-primary" />
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
