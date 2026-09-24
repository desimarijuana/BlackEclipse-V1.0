'use client';

import { useId, useState } from 'react';
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import type { ResearchCitation, ResearchMetadata } from '@/lib/harness/types';
import {
  coerceResearchRun,
  hasSecondarySource,
  mergeLimitations,
  shortDate,
  sourceIndexById,
  sourceMarkers,
  summarizeRun,
} from '@/lib/chat/research-provenance';

// ─── Phase 4/5 research provenance panel ────────────────────────────────────
// A compact, frosted-glass view of a gated research run. It renders BELOW the
// assistant answer (the answer prose no longer embeds citations or footers) in
// a deliberate order:
//
//   1. Calculations   (optional, deterministic inputs + formula)
//   2. Limitations    (always visible; kept separate from the source list)
//   3. Sources        (collapsible, numbered [1], [2] … — never a raw URL in prose)
//   4. Run metadata   (coverage, claims, conflicts, retrieval paths, receipt link)
//
// It never claims "verified" for a claim the deterministic validator left as
// `needs_review`; the status word comes straight from the runtime metadata.

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

/** Render `[1,2]` source markers for a claim's evidence ids (unknown ids hidden). */
function SourceRefs({ ids, index }: { ids: string[]; index: Map<string, number> }) {
  const nums = sourceMarkers(ids, index);
  if (nums.length === 0) return null;
  return (
    <span className="ml-1 align-super text-[9px] font-medium text-primary/80" aria-label={`Sources ${nums.join(', ')}`}>
      {nums.map((n) => `[${n}]`).join('')}
    </span>
  );
}

function Section({ title, children, tone }: { title: string; children: React.ReactNode; tone?: string }) {
  return (
    <section>
      <h4 className={cn('mb-1 text-[10px] font-semibold uppercase tracking-wide', tone ?? 'text-muted-foreground/80')}>
        {title}
      </h4>
      {children}
    </section>
  );
}

/**
 * A collapsible sub-section header (Sources, Research detail). Deliberately
 * muted — these are provenance, not the answer — so the assistant's prose stays
 * the only full-brightness text in the transcript.
 */
function Disclosure({
  title,
  count,
  open,
  onToggle,
}: {
  title: string;
  count?: number;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="flex w-full items-center gap-2 rounded-lg px-1 py-0.5 text-left text-muted-foreground transition-colors hover:bg-white/5"
    >
      <span className="font-medium">{title}</span>
      {typeof count === 'number' ? <span className="text-muted-foreground/70">({count})</span> : null}
      <span className="ml-auto text-muted-foreground/70">
        {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
      </span>
    </button>
  );
}

/** One numbered source row: title, tier/period/currency/basis/dates, View source. */
function SourceRow({ citation, n }: { citation: ResearchCitation; n: number }) {
  const tm = tierMeta(citation.sourceType);
  const title = citation.title || citation.source || citation.kind || 'Source';
  const published = shortDate(citation.publishedAt);
  const retrieved = shortDate(citation.retrievedAt);
  const unverified = citation.validationStatus === 'unverified';
  return (
    <li className="flex flex-col gap-0.5">
      <div className="flex items-baseline gap-2">
        <span className="shrink-0 font-mono text-[10px] text-muted-foreground/70">[{n}]</span>
        <span className="min-w-0 flex-1 font-medium text-muted-foreground">{title}</span>
      </div>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5 pl-5 text-[10px] text-muted-foreground/70">
        <span className={tm.tone}>{tm.label}</span>
        {citation.fiscalPeriod ? <span>{citation.fiscalPeriod}</span> : null}
        {citation.currency ? <span>{citation.currency}</span> : null}
        {citation.unit ? <span>{citation.unit}</span> : null}
        {citation.basis ? <span>{citation.basis}</span> : null}
        {published ? <span>published {published}</span> : null}
        {retrieved ? <span>retrieved {retrieved}</span> : null}
        {unverified ? <span className="text-amber-500">unverified</span> : null}
      </div>
      <div className="pl-5">
        {citation.url ? (
          <a
            href={citation.url}
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1 text-[10px] font-medium text-primary hover:underline"
          >
            View source <ExternalLink className="h-3 w-3" />
          </a>
        ) : (
          <span className="text-[10px] text-muted-foreground">No link available for this source</span>
        )}
      </div>
    </li>
  );
}

function Calculations({ calculations, index }: { calculations: Array<Record<string, unknown>>; index: Map<string, number> }) {
  if (calculations.length === 0) return null;
  return (
    <Section title="Calculation">
      <ul className="space-y-1.5">
        {calculations.map((calc, i) => {
          const metric = String(calc.metric ?? 'calculation');
          const value = calc.value !== undefined ? String(calc.value) : null;
          const currency = calc.currency ? String(calc.currency) : null;
          const formula = calc.formula ? String(calc.formula) : null;
          const inputs = typeof calc.inputs === 'string' ? calc.inputs : null;
          const ids = Array.isArray(calc.inputEvidenceIds) ? (calc.inputEvidenceIds as string[]) : [];
          return (
            <li key={i} className="text-muted-foreground/80">
              <div className="text-muted-foreground">
                {metric}
                {value !== null ? ` = ${value}` : ''}
                {currency ? ` ${currency}` : ''}
                <SourceRefs ids={ids} index={index} />
              </div>
              {inputs ? <div className="text-[10px]">Inputs: {inputs}</div> : null}
              {formula ? <div className="text-[10px]">Formula: {formula}</div> : null}
            </li>
          );
        })}
      </ul>
    </Section>
  );
}

function Limitations({ limitations }: { limitations: string[] }) {
  if (limitations.length === 0) return null;
  return (
    <Section title="Limitations" tone="text-amber-500">
      <ul className="space-y-0.5">
        {limitations.map((item, i) => (
          <li key={i} className="flex items-start gap-1.5 text-muted-foreground">
            <AlertTriangle className="mt-0.5 h-3 w-3 shrink-0 text-amber-500/80" />
            <span>{item}</span>
          </li>
        ))}
      </ul>
    </Section>
  );
}

export function ResearchEvidencePanel({ research, compact = false }: { research: unknown; compact?: boolean }) {
  const info = coerceResearchRun(research);
  // The whole provenance block is COLLAPSED by default and muted, so it reads as
  // attached metadata rather than an extension of the answer. The one always-
  // visible line is the status summary, which includes source/limitation counts.
  const [blockOpen, setBlockOpen] = useState(false);
  const [sourcesOpen, setSourcesOpen] = useState(true);
  const [metaOpen, setMetaOpen] = useState(false);
  const bodyId = useId();
  if (!info) return null;

  const meta = STATUS_META[info.status] ?? STATUS_META.partial;
  const Icon = meta.icon;
  const metadata: ResearchMetadata | null | undefined = info.metadata;
  const legs = info.coverage?.legs ?? [];
  const claims = info.validation?.claims ?? [];
  const citations = metadata?.citations ?? [];
  const calculations = metadata?.calculations ?? [];
  const conflicts = metadata?.conflicts ?? [];
  const escalation = info.escalation ?? null;
  const budget = info.budget ?? null;
  const failedRoutes = info.failedRoutes ?? [];
  const stopReasonText = info.stopReasonText ?? null;
  const limitations = mergeLimitations(metadata);

  const index = sourceIndexById(citations);
  const hasSecondary = hasSecondarySource(citations);
  const hasMetaDetail = legs.length > 0 || claims.length > 0 || conflicts.length > 0 || Boolean(escalation || budget);

  const nothingToShow =
    citations.length === 0 && calculations.length === 0 && limitations.length === 0 && !hasMetaDetail;
  if (nothingToShow) return null;

  const summary = summarizeRun(info);
  const limitationLabel = limitations.length > 0 ? `${limitations.length} limitation${limitations.length === 1 ? '' : 's'}` : '';

  return (
    <div
      className={cn(
        'mt-3 w-full rounded-2xl border border-white/10 p-0 dark:border-white/8 glass-card-subtle',
        compact ? 'text-[11px]' : 'text-xs',
      )}
    >
      {/* The one always-visible line: status + counts. Click to expand provenance. */}
      <button
        type="button"
        onClick={() => setBlockOpen((v) => !v)}
        aria-expanded={blockOpen}
        aria-controls={bodyId}
        className="flex w-full flex-wrap items-center gap-2 rounded-2xl px-3 py-2 text-left transition-colors hover:bg-white/5"
      >
        <Icon className={cn('h-3.5 w-3.5 shrink-0', meta.tone)} />
        <span className={cn('font-semibold', meta.tone)}>{meta.label}</span>
        <span className="text-muted-foreground/80">{summary}</span>
        {limitationLabel ? <span className="text-amber-500/90">{limitationLabel}</span> : null}
        <span className="ml-auto text-muted-foreground/70">
          {blockOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
        </span>
      </button>

      {blockOpen ? (
        <div id={bodyId} className="space-y-3 border-t border-white/10 px-3 py-2.5">
          {/* 1. Calculations */}
          <Calculations calculations={calculations} index={index} />

          {/* 2. Limitations */}
          <Limitations limitations={limitations} />

          {/* 3. Sources (collapsible, numbered) */}
          {citations.length > 0 || failedRoutes.length > 0 ? (
            <section>
              <Disclosure
                title="Sources"
                count={citations.length}
                open={sourcesOpen}
                onToggle={() => setSourcesOpen((v) => !v)}
              />
              {sourcesOpen ? (
                <div className="mt-1.5 space-y-2">
                  {citations.length > 0 ? (
                    <ol className="space-y-2">
                      {citations.map((citation, i) => (
                        <SourceRow key={citation.evidenceId || i} citation={citation} n={i + 1} />
                      ))}
                    </ol>
                  ) : (
                    <p className="pl-1 text-muted-foreground/80">No source could be cited for this answer.</p>
                  )}
                  {failedRoutes.length > 0 ? (
                    <div className="pl-1">
                      <p className="mb-0.5 font-medium text-muted-foreground/80">Routes tried but unavailable</p>
                      <ul className="space-y-0.5 text-[10px] text-muted-foreground/70">
                        {failedRoutes.map((route, i) => (
                          <li key={i}>{route}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ) : null}
            </section>
          ) : null}

          {/* 4. Run metadata (coverage, claims, conflicts, retrieval paths, receipt) */}
          {hasMetaDetail ? (
            <section>
              <Disclosure title="Research detail" open={metaOpen} onToggle={() => setMetaOpen((v) => !v)} />
              {metaOpen ? (
                <div className="mt-1.5 space-y-3">
              {legs.length > 0 ? (
                <Section title="Coverage">
                  <ul className="space-y-0.5">
                    {legs.map((leg) => {
                      const lm = legMeta(leg.status);
                      return (
                        <li key={leg.legId} className="flex items-center gap-2">
                          <span className={cn('inline-block h-1.5 w-1.5 shrink-0 rounded-full', lm.dot)} />
                          <span className="text-muted-foreground">
                            {leg.metric}
                            {leg.period ? ` · ${leg.period}` : ''}
                          </span>
                          <span className={cn(lm.tone)}>— {lm.label}</span>
                          <SourceRefs ids={leg.evidenceIds} index={index} />
                        </li>
                      );
                    })}
                  </ul>
                </Section>
              ) : null}

              {claims.length > 0 ? (
                <Section title="Claims">
                  <ul className="space-y-0.5">
                    {claims.map((claim, i) => (
                      <li key={i} className="flex items-start gap-2">
                        <span className="text-muted-foreground">
                          {claim.supportStatus === 'supported' ? '✓' : claim.supportStatus === 'needs_review' ? '?' : '✕'}
                        </span>
                        <span className={cn(claim.supportStatus === 'supported' ? 'text-muted-foreground' : 'text-muted-foreground/70')}>
                          {claim.text}
                          {claim.supportStatus === 'needs_review' ? ' (unverified)' : ''}
                          <SourceRefs ids={claim.evidenceIds} index={index} />
                        </span>
                      </li>
                    ))}
                  </ul>
                </Section>
              ) : null}

              {conflicts.length > 0 ? (
                <Section title="Unresolved conflicts" tone="text-amber-500">
                  <ul className="space-y-0.5">
                    {conflicts.map((conflict, i) => (
                      <li key={i} className="text-muted-foreground">
                        {String(conflict.metric ?? 'metric')} {String(conflict.period ?? '')} — sources disagree
                      </li>
                    ))}
                  </ul>
                </Section>
              ) : null}

              {escalation || budget ? (
                <Section title="Retrieval paths">
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
                    {hasSecondary ? (
                      <li className="text-amber-500">Includes secondary sources — treat as lower confidence.</li>
                    ) : null}
                  </ul>
                </Section>
              ) : null}

              {stopReasonText ? <p className="text-[10px] text-muted-foreground">Stopped because: {stopReasonText}.</p> : null}

              <p className="text-[10px] text-muted-foreground/80">
                {info.persistenceError
                  ? `Receipt not saved: ${info.persistenceError}`
                  : info.receiptAvailable
                    ? 'A durable research receipt was saved for this run.'
                    : 'No research receipt is available for this run.'}
              </p>
                </div>
              ) : null}
            </section>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
