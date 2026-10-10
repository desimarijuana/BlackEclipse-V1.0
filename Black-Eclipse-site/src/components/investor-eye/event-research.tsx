'use client';

// ── Investor Eye — Evidence & Research (shared engine) ───────────────────────
// The event dossier's window into the SHARED Evidence & Research Engine: the
// same Python engine behind the Research screen and the company brief. Where
// the inline Analyst (`explain-panel.tsx`) gives a conversational grounding,
// this retrieves actual evidence — sources, claims, citations, conflicts — for
// the event, and can be asked to corroborate a conflict the structured feed only
// hinted at.
//
// Honest by construction: it renders only what the engine stored. With no
// runtime it says the runtime is unavailable rather than showing a fake brief.

import { Loader2, BookOpen, AlertTriangle, RefreshCw, Settings } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { AI_SETTINGS_SECTION, openSettingsSection } from '@/lib/investor-eye/navigation';
import { eventResearchQuestion } from '@/lib/investor-eye/research-question';
import { useEventResearch } from '@/lib/investor-eye/use-event-research';
import type { NormalizedEvent } from '@/lib/investor-eye/types';
import { ResearchFindings } from './research-findings';

export function EventResearch({ event }: { event: NormalizedEvent }) {
  const dedupKey = event.id ?? event.dedupKey;
  const r = useEventResearch(dedupKey);

  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
          Evidence &amp; Research (engine)
        </span>
        {(r.state === 'COMPLETED' || r.state === 'PARTIAL') && (
          <button
            onClick={() => r.run(eventResearchQuestion(event))}
            className="flex items-center gap-1 text-[9px] text-muted-foreground hover:text-foreground cursor-pointer"
            title="Run a fresh web-research pass"
          >
            <RefreshCw size={9} /> re-run
          </button>
        )}
      </div>

      {!r.running && !r.detail && !r.error && (
        <>
          <button
            onClick={() => r.reuse(eventResearchQuestion(event))}
            disabled={!dedupKey}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-sky-500/25 bg-sky-500/10 px-2 py-1.5 text-[10px] font-semibold text-foreground hover:bg-sky-500/15 disabled:opacity-40 cursor-pointer"
          >
            <BookOpen size={11} /> Research this event
          </button>
          <div className="mt-1 text-[9px] leading-relaxed text-muted-foreground/60">
            Runs the shared Evidence &amp; Research Engine over this event — independent sources, cited
            findings and contradictions. Findings are the engine&apos;s, not synthesized here.
          </div>
        </>
      )}

      {r.running && (
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <Loader2 size={11} className="animate-spin" />
          Searching and validating sources…
          {typeof r.status?.sourceCount === 'number' ? ` (${r.status.sourceCount} sources)` : ''}
        </div>
      )}

      {(r.state === 'COMPLETED' || r.state === 'PARTIAL') && r.detail && (
        <ResearchFindings
          data={{
            answer: r.detail.run?.answer,
            claims: r.detail.claims,
            sources: r.detail.sources,
            citations: r.detail.citations,
            conflicts: r.detail.conflicts,
            state: r.state,
          }}
        />
      )}

      {r.error && (
        <div className={cn('space-y-1.5 rounded-lg border px-2 py-1.5',
          r.runtimeGap ? 'border-border/30 bg-transparent' : 'border-red-500/25 bg-red-500/5')}>
          <div className="flex items-start gap-1.5">
            {r.runtimeGap
              ? <BookOpen size={11} className="mt-0.5 shrink-0 text-muted-foreground" />
              : <AlertTriangle size={11} className="mt-0.5 shrink-0 text-red-400" />}
            <span className="text-[10px] text-muted-foreground">
              {r.runtimeGap
                ? 'Research runtime unavailable — install it with `npm run setup:python` to enable engine-backed research.'
                : r.error}
            </span>
          </div>
          {!r.runtimeGap && (
            <button
              onClick={() => openSettingsSection(AI_SETTINGS_SECTION)}
              className="flex items-center gap-1.5 rounded-lg border border-primary/30 bg-primary/15 px-2 py-1 text-[10px] font-semibold text-foreground hover:bg-primary/25 cursor-pointer"
            >
              <Settings size={11} /> Open AI settings
            </button>
          )}
        </div>
      )}
    </div>
  );
}
