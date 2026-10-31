'use client';

import { useId, useState } from 'react';
import {
  AlertTriangle,
  BookOpen,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  ShieldAlert,
  ShieldCheck,
  ShieldQuestion,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { ResearchCitation, ResearchMetadata } from '@/lib/harness/types';
import {
  coerceResearchRun,
  coverageCounts,
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
  // An ordinary (non-gated) run that consulted retrieval sources. This is the
  // provenance of what was consulted — never a verification claim, so it uses
  // the neutral question mark, not the "verified" shield.
  collected: { label: 'Sources consulted', icon: ShieldQuestion, tone: 'text-muted-foreground' },
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
      <h4 className={cn('mb-1.5 text-[10px] font-semibold uppercase tracking-wide', tone ?? 'text-muted-foreground/80')}>
        {title}
      </h4>
      {children}
    </section>
  );
}

/**
 * Inline collapsible header used inside the panel body (e.g. "Research detail").
 * Deliberately muted and borderless so it does not nest a second glass box —
 * the whole panel is ONE frosted dropdown, like "What influenced this run".
 */
function InlineDisclosure({
  title,
  open,
  onToggle,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={open}
      className="flex w-full items-center gap-1.5 rounded-lg px-1 py-0.5 text-left text-muted-foreground transition-colors hover:bg-white/5 cursor-pointer"
    >
      {open ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
      <span className="font-medium">{title}</span>
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
    <li className="rounded-lg border border-primary/15 bg-primary/[0.05] px-3 py-2.5">
      <div className="flex items-baseline gap-2">
        <span className="shrink-0 font-mono text-[9px] text-primary/70">[{n}]</span>
        <span className="min-w-0 flex-1 font-semibold leading-relaxed text-foreground">{title}</span>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-x-2.5 gap-y-1 pl-4 text-[9px] text-muted-foreground/70">
        <span className={cn('rounded-full border border-border/30 px-1.5 py-0.5', tm.tone)}>{tm.label}</span>
        {citation.fiscalPeriod ? <span>{citation.fiscalPeriod}</span> : null}
        {citation.currency ? <span>{citation.currency}</span> : null}
        {citation.unit ? <span>{citation.unit}</span> : null}
        {citation.basis ? <span>{citation.basis}</span> : null}
        {published ? <span>published {published}</span> : null}
        {retrieved ? <span>retrieved {retrieved}</span> : null}
        {unverified ? <span className="text-amber-500">unverified</span> : null}
      </div>
      <div className="mt-2 pl-4">
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
  const sourcesSummary = citations.length > 0
    ? `${citations.length} source${citations.length === 1 ? '' : 's'}`
    : 'none cited';
  const detailSummary = legs.length > 0 ? `${coverageCounts(legs).covered}/${legs.length} legs covered` : undefined;

  return (
    <div className={cn('mt-3 w-full rounded-xl border border-border/20', compact ? 'p-2.5' : 'p-3')}>
      {/* One header line — same shape as "What influenced this run". */}
      <button
        type="button"
        onClick={() => setBlockOpen((v) => !v)}
        aria-expanded={blockOpen}
        aria-controls={bodyId}
        className="flex w-full items-start gap-2 py-0.5 text-left text-[11px] text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
      >
        <span className="mt-px shrink-0">{blockOpen ? <ChevronDown size={11} /> : <ChevronRight size={11} />}</span>
        <Icon size={11} className={cn('mt-px shrink-0', meta.tone)} />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5">
            <span className="font-medium text-foreground/90">{meta.label}</span>
            <span className="text-muted-foreground/80">{summary}</span>
            {limitationLabel ? <span className="text-amber-500/90">· {limitationLabel}</span> : null}
          </span>
        </span>
      </button>

      {blockOpen ? (
        <div id={bodyId} className="mt-3 space-y-4 text-[10px]">
          {/* 1. Calculations */}
          <Calculations calculations={calculations} index={index} />

          {/* 2. Limitations */}
          <Limitations limitations={limitations} />

          {/* 3. Sources — numbered, in a bounded scroll area so a long list stays
              manageable instead of spilling the whole transcript. */}
          {citations.length > 0 || failedRoutes.length > 0 ? (
            <section>
              <div className="flex items-center gap-2 px-1 pb-1">
                <BookOpen size={11} className="shrink-0 text-primary" />
                <span className="font-semibold text-foreground">Sources</span>
                <span className="text-muted-foreground/70">· {sourcesSummary}</span>
              </div>
              {citations.length > 0 ? (
                <ol className="mt-2 max-h-56 space-y-2 overflow-y-auto overscroll-contain pr-1">
                  {citations.map((citation, i) => (
                    <SourceRow key={citation.evidenceId || i} citation={citation} n={i + 1} />
                  ))}
                </ol>
              ) : (
                <p className="mt-1.5 px-1 text-muted-foreground/80">No source could be cited for this answer.</p>
              )}
              {failedRoutes.length > 0 ? (
                <div className="mt-2 px-1">
                  <p className="mb-0.5 font-semibold text-foreground">Routes tried but unavailable</p>
                  <ul className="space-y-0.5 text-[10px] text-muted-foreground/70">
                    {failedRoutes.map((route, i) => (
                      <li key={i} className="flex items-start gap-1.5">
                        <span className="mt-[3px] h-1 w-1 shrink-0 rounded-full bg-muted-foreground/40" />
                        <span>{route}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>
          ) : null}

          {/* 4. Run metadata (coverage, claims, conflicts, retrieval paths, receipt) */}
          {hasMetaDetail ? (
            <section>
              <InlineDisclosure
                title={detailSummary ? `Research detail · ${detailSummary}` : 'Research detail'}
                open={metaOpen}
                onToggle={() => setMetaOpen((v) => !v)}
              />
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
