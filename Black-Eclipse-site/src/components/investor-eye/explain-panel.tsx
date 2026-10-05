'use client';

// ── Investor Eye — Explain this event ────────────────────────────────────────
// The AI analyst, placed where the question is asked. The 7 read-only Investor
// Eye agent tools already existed but were only reachable from the chat, so a
// user had to leave the event and re-describe it. This runs the world analyst
// against THIS event's structured record.
//
// Grounded, not generative: the model receives the event as data and can call the
// read-only tools, so it cites the feed. It never invents events, numbers or
// sources, and it is instructed to label inferred exposure as potential.
//
// Offline-honest: with no LLM configured the route returns 503 and the button
// says so, rather than pretending to work.

import { useEffect, useState } from 'react';
import { Sparkles, Loader2, AlertTriangle, RefreshCw } from '@/lib/icons';
import { cn } from '@/lib/utils';

interface ExplainResponse {
  success?: boolean;
  answer?: string;
  toolCalls?: number;
  error?: string;
  hint?: string;
}

interface ExplainState {
  status: 'idle' | 'loading' | 'done' | 'error' | 'unconfigured';
  answer?: string;
  toolCalls?: number;
  error?: string;
}

export function ExplainPanel({ eventId }: { eventId?: string }) {
  const [state, setState] = useState<ExplainState>({ status: 'idle' });

  // An explanation belongs to one event: drop it when the selection changes, so
  // a stale answer can never be read against a different event.
  useEffect(() => {
    setState({ status: 'idle' });
  }, [eventId]);

  const run = async () => {
    if (!eventId) return;
    setState({ status: 'loading' });
    try {
      const res = await fetch('/api/investor-eye/explain', {
        method: 'POST',
        headers: { 'content-type': 'application/json' },
        body: JSON.stringify({ id: eventId }),
      });
      const json = (await res.json()) as ExplainResponse;
      if (res.status === 503) {
        setState({ status: 'unconfigured', error: json.hint ?? json.error });
        return;
      }
      if (!res.ok || !json.answer) {
        setState({ status: 'error', error: json.error ?? 'The analyst could not answer.' });
        return;
      }
      setState({ status: 'done', answer: json.answer, toolCalls: json.toolCalls });
    } catch {
      setState({ status: 'error', error: 'The analyst is unavailable right now.' });
    }
  };

  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
          Analyst
        </span>
        {state.status === 'done' && (
          <button
            onClick={() => void run()}
            className="flex items-center gap-1 text-[9px] text-muted-foreground hover:text-foreground cursor-pointer"
            title="Re-run the analysis"
          >
            <RefreshCw size={9} /> re-run
          </button>
        )}
      </div>

      {state.status === 'idle' && (
        <>
          <button
            onClick={() => void run()}
            disabled={!eventId}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-primary/25 bg-primary/10 px-2 py-1.5 text-[10px] font-semibold text-foreground hover:bg-primary/15 disabled:opacity-40 cursor-pointer"
          >
            <Sparkles size={11} /> Explain this event
          </button>
          <div className="mt-1 text-[9px] leading-relaxed text-muted-foreground/60">
            Runs the read-only world analyst over this event&apos;s record. It cites the feed and
            labels inferred exposure as potential.
          </div>
        </>
      )}

      {state.status === 'loading' && (
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <Loader2 size={11} className="animate-spin" />
          Reading the record and gathering context…
        </div>
      )}

      {state.status === 'done' && (
        <>
          <div className="whitespace-pre-wrap rounded-lg border border-border/25 px-2.5 py-2 text-[11px] leading-relaxed text-muted-foreground">
            {state.answer}
          </div>
          <div className="mt-1 text-[9px] text-muted-foreground/60">
            Generated from this event&apos;s structured record
            {typeof state.toolCalls === 'number' ? ` and ${state.toolCalls} tool call${state.toolCalls === 1 ? '' : 's'}` : ''}.
            Treat inferred exposure as potential, not causal.
          </div>
        </>
      )}

      {state.status === 'error' && (
        <div className={cn('flex items-start gap-1.5 rounded-lg border border-red-500/25 bg-red-500/5 px-2 py-1.5')}>
          <AlertTriangle size={11} className="mt-0.5 shrink-0 text-red-400" />
          <span className="text-[10px] text-muted-foreground">{state.error}</span>
        </div>
      )}

      {state.status === 'unconfigured' && (
        <div className="rounded-lg border border-border/30 px-2 py-1.5 text-[10px] text-muted-foreground">
          No AI provider is configured, so the analyst is unavailable.
          {state.error ? <span className="block text-[9px] text-muted-foreground/70">{state.error}</span> : null}
        </div>
      )}
    </div>
  );
}
