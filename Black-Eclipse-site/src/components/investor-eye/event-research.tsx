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

import { Loader2, BookOpen, AlertTriangle, RefreshCw, ExternalLink } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { eventResearchQuestion } from '@/lib/investor-eye/research-question';
import { useEventResearch } from '@/lib/investor-eye/use-event-research';
import type { NormalizedEvent } from '@/lib/investor-eye/types';

interface ClaimRow { text?: string; kind?: string; status?: string; confidence?: number }
interface SourceRow { canonicalUrl?: string; domain?: string; publisher?: string; publishedAt?: string }
interface CitationRow { sourceUrl?: string; title?: string }

function claimTone(status: string | undefined): string {
  const s = (status ?? '').toLowerCase();
  if (s.includes('verif') || s.includes('support')) return 'border-emerald-500/25 text-emerald-300';
  if (s.includes('reject') || s.includes('contradict') || s.includes('fail')) return 'border-red-500/25 text-red-300';
  if (s.length) return 'border-amber-500/25 text-amber-300';
  return 'border-border/40 text-muted-foreground';
}

export function EventResearch({ event }: { event: NormalizedEvent }) {
  const dedupKey = event.id ?? event.dedupKey;
  const r = useEventResearch(dedupKey);

  const claims = (r.detail?.claims ?? []) as ClaimRow[];
  const sources = (r.detail?.sources ?? []) as SourceRow[];
  const citations = (r.detail?.citations ?? []) as CitationRow[];
  const conflictCount = r.detail?.conflicts?.length ?? 0;
  const answer = r.detail?.run?.answer ?? null;

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
        <div className="space-y-2">
          {answer && (
            <div className="whitespace-pre-wrap rounded-lg border border-border/25 px-2.5 py-2 text-[11px] leading-relaxed text-muted-foreground">
              {answer}
            </div>
          )}

          <div className="flex flex-wrap gap-1.5 text-[9px] font-mono text-muted-foreground">
            <span className="rounded-sm border border-border/30 px-1.5 py-0.5">{sources.length} sources</span>
            <span className="rounded-sm border border-border/30 px-1.5 py-0.5">{claims.length} claims</span>
            {conflictCount > 0 && (
              <span className="rounded-sm border border-amber-500/30 text-amber-300 px-1.5 py-0.5">
                {conflictCount} conflicts
              </span>
            )}
            {r.state === 'PARTIAL' && (
              <span className="rounded-sm border border-amber-500/30 text-amber-300 px-1.5 py-0.5">partial</span>
            )}
          </div>

          {claims.length > 0 && (
            <ul className="space-y-1">
              {claims.slice(0, 6).map((c, i) => (
                <li key={i} className="flex gap-1.5 text-[11px] leading-relaxed">
                  <span className={cn('mt-0.5 shrink-0 rounded-sm border px-1 text-[8px] font-mono uppercase', claimTone(c.status))}>
                    {c.status ?? c.kind ?? 'claim'}
                  </span>
                  <span className="text-muted-foreground">{c.text}</span>
                </li>
              ))}
            </ul>
          )}

          {sources.length > 0 && (
            <div className="space-y-0.5">
              {sources.slice(0, 5).map((s, i) => (
                <div key={i} className="flex items-center gap-1 text-[10px] text-muted-foreground/80">
                  <ExternalLink size={9} className="shrink-0" />
                  {s.canonicalUrl ? (
                    <a href={s.canonicalUrl} target="_blank" rel="noreferrer" className="truncate hover:text-foreground">
                      {s.publisher ?? s.domain ?? s.canonicalUrl}
                    </a>
                  ) : (
                    <span className="truncate">{s.publisher ?? s.domain ?? 'source'}</span>
                  )}
                </div>
              ))}
              {citations.length > 0 && (
                <div className="text-[9px] text-muted-foreground/60">{citations.length} citations linked</div>
              )}
            </div>
          )}
        </div>
      )}

      {r.error && (
        <div className={cn('flex items-start gap-1.5 rounded-lg border px-2 py-1.5',
          r.runtimeGap ? 'border-border/30 bg-transparent' : 'border-red-500/25 bg-red-500/5')}>
          {r.runtimeGap
            ? <BookOpen size={11} className="mt-0.5 shrink-0 text-muted-foreground" />
            : <AlertTriangle size={11} className="mt-0.5 shrink-0 text-red-400" />}
          <span className="text-[10px] text-muted-foreground">
            {r.runtimeGap
              ? 'Research runtime unavailable — install it with `npm run setup:python` to enable engine-backed research.'
              : r.error}
          </span>
        </div>
      )}
    </div>
  );
}
