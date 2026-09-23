'use client';

import { useState } from 'react';
import { ChevronDown, ChevronRight, ShieldAlert, ShieldCheck, ShieldQuestion } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ResearchMetadata, ResearchRunInfo } from '@/lib/harness/types';

// ─── Phase 4 evidence panel ─────────────────────────────────────────────────
// A compact, frosted-glass view of a gated research run: status, coverage,
// citations, gaps and limitations. It never claims "verified" for a claim that
// the deterministic validator left as `needs_review`; the status word comes
// straight from the runtime metadata.

const STATUS_META: Record<string, { label: string; icon: typeof ShieldCheck; tone: string }> = {
  accepted: { label: 'Evidence-grounded', icon: ShieldCheck, tone: 'text-emerald-500' },
  partial: { label: 'Partial — gaps disclosed', icon: ShieldQuestion, tone: 'text-amber-500' },
  rejected: { label: 'Not established', icon: ShieldAlert, tone: 'text-rose-500' },
};

// Coverage leg status → dot colour + plain-language label (Phase 5 statuses).
const LEG_META: Record<string, { dot: string; label: string; tone: string }> = {
  covered: { dot: 'bg-emerald-500', label: 'covered', tone: 'text-foreground' },
  qualified: { dot: 'bg-amber-500', label: 'qualified (metadata unconfirmed)', tone: 'text-amber-500' },
  conflicting: { dot: 'bg-amber-500', label: 'sources conflict', tone: 'text-amber-500' },
  no_matching_period: { dot: 'bg-rose-500', label: 'no matching period', tone: 'text-rose-500' },
  stale: { dot: 'bg-amber-500', label: 'stale', tone: 'text-amber-500' },
  unknown: { dot: 'bg-rose-500', label: 'metadata unknown', tone: 'text-rose-500' },
  unavailable: { dot: 'bg-rose-500', label: 'no evidence retrieved', tone: 'text-rose-500' },
  not_applicable: { dot: 'bg-muted-foreground', label: 'not applicable', tone: 'text-muted-foreground' },
};

/** Source tier → a short, honest label. Secondary sources are never disguised. */
const TIER_META: Record<string, { label: string; tone: string }> = {
  primary: { label: 'primary source', tone: 'text-emerald-500' },
  official: { label: 'official source', tone: 'text-emerald-500' },
  structured: { label: 'structured data', tone: 'text-foreground' },
  secondary: { label: 'secondary source', tone: 'text-amber-500' },
  derived: { label: 'derived', tone: 'text-muted-foreground' },
  cache: { label: 'cached', tone: 'text-amber-500' },
  unknown: { label: 'source tier unknown', tone: 'text-muted-foreground' },
};

function tierMeta(tier: string | null | undefined) {
  return TIER_META[tier ?? 'unknown'] ?? { label: tier ?? 'unknown', tone: 'text-muted-foreground' };
}

function legMeta(status: string) {
  return LEG_META[status] ?? { dot: 'bg-muted-foreground', label: status, tone: 'text-muted-foreground' };
}

function coerce(info: unknown): ResearchRunInfo | null {
  if (!info || typeof info !== 'object') return null;
  const candidate = info as ResearchRunInfo;
  if (!candidate.status) return null;
  return candidate;
}

export function ResearchEvidencePanel({ research, compact = false }: { research: unknown; compact?: boolean }) {
  const info = coerce(research);
  const [open, setOpen] = useState(false);
  if (!info) return null;

  const meta = STATUS_META[info.status] ?? STATUS_META.partial;
  const Icon = meta.icon;
  const metadata: ResearchMetadata | null | undefined = info.metadata;
  const legs = info.coverage?.legs ?? [];
  const claims = info.validation?.claims ?? [];
  const citations = metadata?.citations ?? [];
  const limitations = metadata?.limitations ?? [];
  const conflicts = metadata?.conflicts ?? [];
  const calculations = metadata?.calculations ?? [];
  const escalation = info.escalation ?? null;
  const budget = info.budget ?? null;

  const covered = legs.filter((l) => l.status === 'covered').length;
  const unmet = legs.filter((l) => l.status !== 'covered' && l.status !== 'not_applicable').length;
  const hasSecondary = citations.some((c) => c.sourceType === 'secondary');

  return (
    <div
      className={cn(
        'mt-2 overflow-hidden rounded-2xl border border-white/12 dark:border-white/8 glass-card-subtle',
        compact ? 'text-[11px]' : 'text-xs',
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-white/5"
      >
        <Icon className={cn('h-3.5 w-3.5 shrink-0', meta.tone)} />
        <span className={cn('font-semibold', meta.tone)}>{meta.label}</span>
        <span className="text-muted-foreground">
          {covered}/{legs.length} legs covered
          {unmet > 0 ? ` · ${unmet} unmet` : ''}
        </span>
        {conflicts.length > 0 ? (
          <span className="text-amber-500">· {conflicts.length} conflict(s)</span>
        ) : null}
        <span className="ml-auto text-muted-foreground">
          {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </span>
      </button>

      {open ? (
        <div className="space-y-3 border-t border-white/10 px-3 py-2.5">
          {legs.length > 0 ? (
            <section>
              <h4 className="mb-1 font-semibold text-muted-foreground">Coverage</h4>
              <ul className="space-y-0.5">
                {legs.map((leg) => {
                  const lm = legMeta(leg.status);
                  return (
                    <li key={leg.legId} className="flex items-center gap-2">
                      <span className={cn('inline-block h-1.5 w-1.5 shrink-0 rounded-full', lm.dot)} />
                      <span className="text-foreground">
                        {leg.metric}
                        {leg.period ? ` · ${leg.period}` : ''}
                      </span>
                      <span className={cn(lm.tone)}>— {lm.label}</span>
                    </li>
                  );
                })}
              </ul>
            </section>
          ) : null}

          {claims.length > 0 ? (
            <section>
              <h4 className="mb-1 font-semibold text-muted-foreground">Claims</h4>
              <ul className="space-y-0.5">
                {claims.map((claim, i) => (
                  <li key={i} className="flex items-start gap-2">
                    <span className="text-muted-foreground">
                      {claim.supportStatus === 'supported'
                        ? '✓'
                        : claim.supportStatus === 'needs_review'
                          ? '?'
                          : '✕'}
                    </span>
                    <span
                      className={cn(
                        claim.supportStatus === 'supported' ? 'text-foreground' : 'text-muted-foreground',
                      )}
                    >
                      {claim.text}
                      {claim.supportStatus === 'needs_review' ? ' (unverified)' : ''}
                    </span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {citations.length > 0 ? (
            <section>
              <h4 className="mb-1 font-semibold text-muted-foreground">Evidence</h4>
              <ul className="space-y-1.5">
                {citations.map((citation) => {
                  const tm = tierMeta(citation.sourceType);
                  return (
                    <li key={citation.evidenceId} className="flex flex-col gap-0.5">
                      <div className="flex items-baseline gap-2">
                        <span className="font-mono text-[10px] text-muted-foreground">[{citation.evidenceId}]</span>
                        {citation.url ? (
                          <a
                            href={citation.url}
                            target="_blank"
                            rel="noreferrer"
                            className="truncate text-primary hover:underline"
                          >
                            {citation.title || citation.source || citation.url}
                          </a>
                        ) : (
                          <span className="text-muted-foreground">
                            {citation.title || citation.source || citation.kind}
                            {citation.validationStatus === 'unverified' ? ' (unverified)' : ''}
                          </span>
                        )}
                      </div>
                      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 pl-4 text-[10px] text-muted-foreground">
                        <span className={tm.tone}>{tm.label}</span>
                        {citation.fiscalPeriod ? <span>{citation.fiscalPeriod}</span> : null}
                        {citation.currency ? <span>{citation.currency}</span> : null}
                        {citation.basis ? <span>{citation.basis}</span> : null}
                        {citation.publishedAt ? <span>published {citation.publishedAt.slice(0, 10)}</span> : null}
                        {citation.retrievedAt ? <span>retrieved {citation.retrievedAt.slice(0, 10)}</span> : null}
                      </div>
                    </li>
                  );
                })}
              </ul>
            </section>
          ) : null}

          {conflicts.length > 0 ? (
            <section>
              <h4 className="mb-1 font-semibold text-amber-500">Unresolved conflicts</h4>
              <ul className="space-y-0.5">
                {conflicts.map((conflict, i) => (
                  <li key={i} className="text-muted-foreground">
                    {String(conflict.metric ?? 'metric')} {String(conflict.period ?? '')} — sources disagree
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {calculations.length > 0 ? (
            <section>
              <h4 className="mb-1 font-semibold text-muted-foreground">Calculations</h4>
              <ul className="space-y-0.5">
                {calculations.map((calc, i) => (
                  <li key={i} className="text-muted-foreground">
                    {String(calc.metric ?? 'calculation')}
                    {calc.value !== undefined ? ` = ${String(calc.value)}` : ''}
                    {Array.isArray(calc.inputEvidenceIds) && calc.inputEvidenceIds.length > 0
                      ? ` (inputs: ${(calc.inputEvidenceIds as string[]).join(', ')})`
                      : ''}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {limitations.length > 0 ? (
            <section>
              <h4 className="mb-1 font-semibold text-muted-foreground">Limitations</h4>
              <ul className="space-y-0.5">
                {limitations.map((item, i) => (
                  <li key={i} className="text-muted-foreground">
                    {item}
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {escalation || budget ? (
            <section>
              <h4 className="mb-1 font-semibold text-muted-foreground">Retrieval paths</h4>
              <ul className="space-y-0.5 text-[10px] text-muted-foreground">
                {escalation?.stages?.length ? (
                  <li>Web escalation stages: {escalation.stages.join(' → ')}</li>
                ) : (
                  <li>No web escalation was required or possible.</li>
                )}
                {budget ? (
                  <li>
                    Budget: {budget.used.searches}/{budget.limits.maxSearches} searches,{' '}
                    {budget.used.fetches}/{budget.limits.maxFetches} fetches
                    {budget.exhausted ? ` — exhausted (${budget.exhausted})` : ''}
                  </li>
                ) : null}
                {hasSecondary ? <li className="text-amber-500">Includes secondary sources — treat as lower confidence.</li> : null}
              </ul>
            </section>
          ) : null}

          <p className="text-[10px] text-muted-foreground">
            {info.persistenceError
              ? `Receipt not saved: ${info.persistenceError}`
              : info.receiptAvailable
                ? 'A durable research receipt was saved for this run.'
                : 'No research receipt is available for this run.'}
          </p>
        </div>
      ) : null}
    </div>
  );
}
