'use client';

// Shared presentation for Evidence & Research Engine results. Used by the event
// dossier (`event-research.tsx`) and the window-level conflict search
// (`conflict-research-panel.tsx`) so the two never drift. It renders ONLY what
// the engine stored — answer, sources, claims with verification status,
// citations and a conflict count.

import { ExternalLink } from '@/lib/icons';
import { cn } from '@/lib/utils';

export interface ResearchClaimRow { text?: string; kind?: string; status?: string }
export interface ResearchSourceRow { canonicalUrl?: string; domain?: string; publisher?: string }
export interface ResearchFindingsData {
  answer?: string | null;
  claims?: ResearchClaimRow[];
  sources?: ResearchSourceRow[];
  citations?: unknown[];
  conflicts?: unknown[];
  state?: string | null;
}

function claimTone(status: string | undefined): string {
  const s = (status ?? '').toLowerCase();
  if (s.includes('verif') || s.includes('support')) return 'border-emerald-500/25 text-emerald-300';
  if (s.includes('reject') || s.includes('contradict') || s.includes('fail')) return 'border-red-500/25 text-red-300';
  if (s.length) return 'border-amber-500/25 text-amber-300';
  return 'border-border/40 text-muted-foreground';
}

export function ResearchFindings({ data }: { data: ResearchFindingsData }) {
  const claims = data.claims ?? [];
  const sources = data.sources ?? [];
  const conflictCount = data.conflicts?.length ?? 0;
  const citations = data.citations ?? [];
  const answer = data.answer ?? null;

  return (
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
        {data.state === 'PARTIAL' && (
          <span className="rounded-sm border border-amber-500/30 text-amber-300 px-1.5 py-0.5">partial</span>
        )}
      </div>

      {claims.length > 0 && (
        <ul className="space-y-1">
          {claims.slice(0, 8).map((c, i) => (
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
          {sources.slice(0, 6).map((s, i) => (
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
  );
}
