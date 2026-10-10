'use client';

// ── Investor Eye — Conflict research (AI, cited) ─────────────────────────────
// The "use AI to make conflicts appear" action. When the structured feed's
// conflict coverage is thin — or the user simply wants independent
// corroboration — this asks the SHARED Evidence & Research Engine for a conflict
// situation report over the current window and renders the engine's cited
// findings.
//
// It deliberately does NOT create map pins: turning an LLM finding into a
// plotted event needs a provenance/identity policy we will not fake. What it
// gives is exactly what the engine can defend — sources, claims with
// verification status, contradictions — clearly labelled as research, not as
// provider observations.

import { Loader2, Radio, AlertTriangle, RefreshCw, Settings } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { AI_SETTINGS_SECTION, openSettingsSection } from '@/lib/investor-eye/navigation';
import { windowConflictQuestion } from '@/lib/investor-eye/research-question';
import { useEventResearch } from '@/lib/investor-eye/use-event-research';
import { ResearchFindings } from './research-findings';

export function ConflictResearchPanel({ windowHours }: { windowHours: number }) {
  const key = `window-conflicts:${windowHours}`;
  const r = useEventResearch(key);
  const question = windowConflictQuestion(windowHours);

  return (
    <div className="glass-card rounded-xl border border-white/10 dark:border-white/5 px-3 py-2">
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <span className="text-[9px] font-bold uppercase tracking-widest text-muted-foreground">
          Conflict research (AI, cited)
        </span>
        {(r.state === 'COMPLETED' || r.state === 'PARTIAL') && (
          <button
            onClick={() => r.run(question)}
            className="flex items-center gap-1 text-[9px] text-muted-foreground hover:text-foreground cursor-pointer"
            title="Run a fresh conflict search"
          >
            <RefreshCw size={9} /> re-run
          </button>
        )}
      </div>

      {!r.running && !r.detail && !r.error && (
        <>
          <button
            onClick={() => r.reuse(question)}
            className="flex w-full items-center justify-center gap-1.5 rounded-lg border border-amber-500/25 bg-amber-500/10 px-2 py-1.5 text-[10px] font-semibold text-foreground hover:bg-amber-500/15 cursor-pointer"
          >
            <Radio size={11} /> Find conflicts with AI
          </button>
          <div className="mt-1 text-[9px] leading-relaxed text-muted-foreground/60">
            Asks the Evidence &amp; Research Engine for a cited conflict situation report over the last
            window. Research findings are labelled as such — they are not mapped as provider events.
          </div>
        </>
      )}

      {r.running && (
        <div className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
          <Loader2 size={11} className="animate-spin" />
          Searching independent reporting…
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
              ? <Radio size={11} className="mt-0.5 shrink-0 text-muted-foreground" />
              : <AlertTriangle size={11} className="mt-0.5 shrink-0 text-red-400" />}
            <span className="text-[10px] text-muted-foreground">
              {r.runtimeGap
                ? 'Research runtime unavailable — install it with `npm run setup:python` to enable AI conflict research.'
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
