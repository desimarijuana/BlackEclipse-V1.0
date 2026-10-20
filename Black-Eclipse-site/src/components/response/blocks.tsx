'use client';

// ── Response block components ─────────────────────────────────────────────────
// Presentational, registry-bound components for every non-chart, non-diagram
// block type. They render *validated* data only and never execute model output.

import { useState, type ComponentType, type ReactNode } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  Database,
  ExternalLink,
  Info,
  Lightbulb,
  Minus,
  TrendingDown,
  TrendingUp,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { extractHost, isUnavailableText } from '@/lib/chat/markdown';
import { Markdown } from '@/components/chat/markdown';
import type {
  CitationSource,
  Metric,
  ParsedResponse,
  ResponseDiagnostic,
  UnknownBlock,
  ValidatedBlock,
} from '@/lib/response/contract';

// ── Content ───────────────────────────────────────────────────────────────────

export function MarkdownBlock({ markdown, compact }: { markdown: string; compact?: boolean }) {
  return <Markdown content={markdown} compact={compact} className="w-full" />;
}

export function HeadingBlock({ text, level, compact }: { text: string; level: number; compact?: boolean }) {
  const Tag = (`h${Math.min(Math.max(level, 1), 4)}`) as 'h1' | 'h2' | 'h3' | 'h4';
  const size =
    level <= 1
      ? 'text-lg md:text-xl'
      : level === 2
        ? 'text-base md:text-lg'
        : 'text-sm md:text-base';
  return <Tag className={cn('font-semibold tracking-tight text-foreground', size, compact && 'text-[14px]')}>{text}</Tag>;
}

const CALLOUT_TONE = {
  info: {
    icon: Info,
    bar: 'from-sky-300 to-sky-500/60',
    chip: 'bg-sky-400/15 text-sky-300 ring-sky-400/30',
    title: 'text-sky-100',
    glow: 'bg-sky-500/30',
    wash: 'from-sky-500/[0.10]',
  },
  note: {
    icon: Lightbulb,
    bar: 'from-violet-300 to-violet-500/60',
    chip: 'bg-violet-400/15 text-violet-300 ring-violet-400/30',
    title: 'text-violet-100',
    glow: 'bg-violet-500/30',
    wash: 'from-violet-500/[0.10]',
  },
  success: {
    icon: CheckCircle2,
    bar: 'from-emerald-300 to-emerald-500/60',
    chip: 'bg-emerald-400/15 text-emerald-300 ring-emerald-400/30',
    title: 'text-emerald-100',
    glow: 'bg-emerald-500/30',
    wash: 'from-emerald-500/[0.10]',
  },
  warning: {
    icon: AlertTriangle,
    bar: 'from-amber-300 to-amber-500/60',
    chip: 'bg-amber-400/15 text-amber-300 ring-amber-400/30',
    title: 'text-amber-100',
    glow: 'bg-amber-500/30',
    wash: 'from-amber-500/[0.10]',
  },
  danger: {
    icon: AlertTriangle,
    bar: 'from-rose-300 to-rose-500/60',
    chip: 'bg-rose-400/15 text-rose-300 ring-rose-400/30',
    title: 'text-rose-100',
    glow: 'bg-rose-500/30',
    wash: 'from-rose-500/[0.10]',
  },
} as const;

export type NoticeTone = keyof typeof CALLOUT_TONE;

type NoticeIcon = ComponentType<{ size?: number | string; className?: string }>;

/**
 * The shared visual language for every inline notice/warning surface in the
 * response renderer (callouts, unsupported-block cards, render failures, …):
 * a frosted subtle surface with a tone accent bar, a tone-tinted icon chip and
 * tone-coloured title. Keeps warnings from looking like detached flat boxes.
 */
export function NoticeCard({
  tone,
  icon,
  title,
  dense,
  className,
  children,
}: {
  tone: NoticeTone;
  icon?: NoticeIcon;
  title?: ReactNode;
  dense?: boolean;
  className?: string;
  children?: ReactNode;
}) {
  const { icon: DefaultIcon, bar, chip, title: titleCls, glow, wash } = CALLOUT_TONE[tone];
  const Icon = icon ?? DefaultIcon;
  return (
    <div
      className={cn(
        'glass-card-subtle relative overflow-hidden rounded-xl pl-4 pr-3.5 ring-1 ring-inset ring-white/[0.06]',
        dense ? 'py-1.5' : 'py-2.5',
        className,
      )}
    >
      <span className={cn('pointer-events-none absolute inset-0 bg-gradient-to-r to-transparent', wash)} aria-hidden />
      <span className={cn('pointer-events-none absolute -left-12 -top-14 h-28 w-28 rounded-full opacity-50 blur-2xl', glow)} aria-hidden />
      <span className={cn('absolute inset-y-1.5 left-0 w-[3px] rounded-full bg-gradient-to-b', bar)} aria-hidden />
      <div className="relative flex items-start gap-2.5">
        <span
          className={cn(
            'flex h-5 w-5 shrink-0 items-center justify-center rounded-[7px] shadow-sm ring-1 ring-inset',
            dense ? 'mt-px' : 'mt-0.5',
            chip,
          )}
        >
          <Icon size={12} />
        </span>
        <div className="min-w-0 flex-1">
          {title != null && <div className={cn('text-[13px] font-semibold leading-5', titleCls)}>{title}</div>}
          {children}
        </div>
      </div>
    </div>
  );
}

export function CalloutBlock({
  tone,
  title,
  markdown,
  compact,
}: {
  tone: NoticeTone;
  title?: string;
  markdown: string;
  compact?: boolean;
}) {
  return (
    <NoticeCard tone={tone} title={title}>
      <Markdown content={markdown} compact={compact} className={cn('text-[13px] text-foreground/85', title != null && 'mt-1')} />
    </NoticeCard>
  );
}

export function KeyValueBlock({
  title,
  items,
}: {
  title?: string;
  items: { label: string; value: string | number; hint?: string }[];
}) {
  return (
    <div className="w-full">
      {title && <h4 className="mb-1.5 text-sm font-semibold text-foreground">{title}</h4>}
      <dl className="grid grid-cols-1 gap-x-6 gap-y-1.5 sm:grid-cols-2">
        {items.map((item, i) => (
          <div key={i} className="flex items-baseline justify-between gap-3 border-b border-white/[0.06] py-1 last:border-0">
            <dt className="text-[12px] text-muted-foreground" title={item.hint}>
              {item.label}
            </dt>
            <dd className="text-right text-[13px] tabular-nums text-foreground">{String(item.value)}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

export function DetailsBlock({
  summary,
  markdown,
  open,
  compact,
}: {
  summary: string;
  markdown: string;
  open?: boolean;
  compact?: boolean;
}) {
  return (
    <details className="group rounded-xl border border-white/10 bg-accent/10 px-3 py-2" open={open}>
      <summary className="flex cursor-pointer list-none items-center gap-1.5 text-[13px] font-medium text-foreground">
        <ChevronRight size={13} className="transition-transform group-open:rotate-90" />
        {summary}
      </summary>
      <div className="mt-2 pl-4">
        <Markdown content={markdown} compact={compact} className="text-[13px]" />
      </div>
    </details>
  );
}

// ── Data ──────────────────────────────────────────────────────────────────────

function DeltaBadge({ delta, tone }: { delta: string | number; tone?: Metric['deltaTone'] }) {
  const numeric = typeof delta === 'number' ? delta : Number(String(delta).replace(/[%,$\s]/g, ''));
  const resolved = tone ?? (Number.isFinite(numeric) ? (numeric > 0 ? 'up' : numeric < 0 ? 'down' : 'flat') : 'neutral');
  const Icon = resolved === 'up' ? TrendingUp : resolved === 'down' ? TrendingDown : Minus;
  const cls =
    resolved === 'up'
      ? 'text-emerald-400'
      : resolved === 'down'
        ? 'text-rose-400'
        : 'text-muted-foreground/70';
  return (
    <span className={cn('inline-flex items-center gap-1 text-[11px] font-medium', cls)}>
      <Icon size={11} />
      {typeof delta === 'number' ? `${delta > 0 ? '+' : ''}${delta}` : delta}
    </span>
  );
}

export function MetricGridBlock({
  title,
  source,
  asOf,
  columns,
  metrics,
}: {
  title?: string;
  source?: string;
  asOf?: string;
  columns?: number;
  metrics: Metric[];
}) {
  const cols = columns ?? Math.min(metrics.length, 4);
  const gridClass =
    cols <= 1 ? 'grid-cols-1' : cols === 2 ? 'grid-cols-1 sm:grid-cols-2' : cols === 3 ? 'grid-cols-2 sm:grid-cols-3' : 'grid-cols-2 md:grid-cols-4';
  return (
    <div className="w-full">
      {(title || source || asOf) && (
        <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-2">
          {title && <h4 className="text-sm font-semibold text-foreground">{title}</h4>}
          {(source || asOf) && (
            <span className="font-mono text-[10px] text-muted-foreground/60">
              {source}
              {source && asOf ? ' · ' : ''}
              {asOf}
            </span>
          )}
        </div>
      )}
      <div className={cn('grid gap-2.5', gridClass)}>
        {metrics.map((metric, i) => {
          const unavailable = metric.unavailable || (typeof metric.value === 'string' && isUnavailableText(metric.value));
          return (
            <div key={i} className="glass-card-subtle rounded-xl px-3 py-2.5">
              <p className="truncate text-[11px] uppercase tracking-wide text-muted-foreground/70" title={metric.hint}>
                {metric.label}
              </p>
              <div className="mt-1 flex items-baseline gap-1.5">
                {unavailable ? (
                  <span className="rounded border border-border/50 bg-accent/20 px-1.5 py-0.5 text-[0.75em] font-medium uppercase tracking-wide text-muted-foreground/80">
                    UNAVAILABLE
                  </span>
                ) : (
                  <>
                    {metric.prefix && <span className="text-[13px] text-muted-foreground">{metric.prefix}</span>}
                    <span className="text-[18px] font-semibold tabular-nums leading-none text-foreground">
                      {typeof metric.value === 'number'
                        ? metric.value.toLocaleString()
                        : typeof metric.value === 'string'
                          ? metric.value
                          : ''}
                    </span>
                    {metric.unit && <span className="text-[11px] text-muted-foreground">{metric.unit}</span>}
                  </>
                )}
              </div>
              <div className="mt-1.5 flex items-center justify-between gap-2">
                {metric.delta != null && <DeltaBadge delta={metric.delta} tone={metric.deltaTone} />}
                {metric.hint && <span className="truncate text-[10px] text-muted-foreground/50" title={metric.hint}>{metric.hint}</span>}
              </div>
              {metric.provenance && (metric.provenance.source || metric.provenance.asOf) && (
                <p
                  className="mt-1 truncate text-[9.5px] text-muted-foreground/50"
                  title={metric.provenance.method ?? metric.provenance.source}
                >
                  {metric.provenance.source}
                  {metric.provenance.source && metric.provenance.asOf ? ' · ' : ''}
                  {metric.provenance.asOf}
                </p>
              )}
              {metric.provenance?.formula && (
                <p
                  className="mt-0.5 truncate font-mono text-[9.5px] text-muted-foreground/60"
                  title={metric.provenance.formula}
                >
                  {metric.provenance.formula}
                </p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ── Sources ───────────────────────────────────────────────────────────────────

export function CitationsBlock({ title, sources }: { title?: string; sources: CitationSource[] }) {
  if (sources.length === 0) {
    return <p className="text-[12px] italic text-muted-foreground/70">No sources were recorded for this answer.</p>;
  }
  return (
    <div className="w-full">
      <h4 className="mb-1.5 text-[0.8em] font-medium uppercase tracking-wider text-muted-foreground/70">
        {title ?? 'Sources'}
      </h4>
      <ol className="space-y-2 pl-0">
        {sources.map((source, i) => {
          const host = source.url ? extractHost(source.url) : null;
          return (
            <li key={i} className="flex gap-2 border-l-2 border-border/40 pl-3">
              <span className="shrink-0 font-mono text-[11px] text-muted-foreground/50">{i + 1}.</span>
              <div className="min-w-0">
                {source.url ? (
                  <a
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="group inline-flex items-baseline gap-1 text-[13px] text-primary underline underline-offset-2 hover:opacity-80"
                  >
                    <span className="truncate">{source.title}</span>
                    <ExternalLink size={11} className="shrink-0 opacity-0 group-hover:opacity-70" />
                  </a>
                ) : (
                  <span className="text-[13px] text-foreground">{source.title}</span>
                )}
                <div className="flex flex-wrap items-center gap-x-2 text-[10px] text-muted-foreground/60">
                  {source.source && <span>{source.source}</span>}
                  {host && <span>{host}</span>}
                  {source.publishedAt && <span>published {source.publishedAt}</span>}
                  {source.retrievedAt && <span>retrieved {source.retrievedAt}</span>}
                </div>
                {source.snippet && <p className="mt-0.5 line-clamp-2 text-[12px] text-muted-foreground/80">{source.snippet}</p>}
              </div>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// ── Timeline ──────────────────────────────────────────────────────────────────

const TONE_DOT: Record<string, string> = {
  neutral: 'bg-muted-foreground/50',
  info: 'bg-sky-400',
  success: 'bg-emerald-400',
  warning: 'bg-amber-400',
  danger: 'bg-rose-400',
};

export function TimelineBlock({
  title,
  events,
}: {
  title?: string;
  events: { time: string; title: string; description?: string; tone: string }[];
}) {
  return (
    <div className="w-full">
      {title && <h4 className="mb-2 text-sm font-semibold text-foreground">{title}</h4>}
      <ol className="relative space-y-3 border-l border-border/40 pl-4">
        {events.map((event, i) => (
          <li key={i} className="relative">
            <span className={cn('absolute -left-[21px] top-1 h-2.5 w-2.5 rounded-full ring-2 ring-background', TONE_DOT[event.tone] ?? TONE_DOT.neutral)} />
            <div className="flex flex-wrap items-baseline gap-x-2">
              <span className="font-mono text-[11px] text-muted-foreground/70">{event.time}</span>
              <span className="text-[13px] font-medium text-foreground">{event.title}</span>
            </div>
            {event.description && <p className="mt-0.5 text-[12px] text-muted-foreground/80">{event.description}</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}

// ── Tabs / layout ─────────────────────────────────────────────────────────────

export function TabsBlock({
  tabs,
  renderBlocks,
}: {
  tabs: { label: string; blocks: ValidatedBlock[] }[];
  renderBlocks: (blocks: ValidatedBlock[]) => ReactNode;
}) {
  const [active, setActive] = useState(0);
  const current = tabs[Math.min(active, tabs.length - 1)];
  return (
    <div className="w-full">
      <div role="tablist" className="mb-2 flex flex-wrap gap-1 border-b border-border/40 pb-1">
        {tabs.map((tab, i) => (
          <button
            key={i}
            role="tab"
            type="button"
            aria-selected={i === active}
            onClick={() => setActive(i)}
            className={cn(
              'rounded-md px-2.5 py-1 text-[12px] transition-colors',
              i === active ? 'bg-accent text-foreground' : 'text-muted-foreground hover:bg-accent/50 hover:text-foreground',
            )}
          >
            {tab.label}
          </button>
        ))}
      </div>
      <div role="tabpanel">{current ? renderBlocks(current.blocks) : null}</div>
    </div>
  );
}

// ── Diagnostics ───────────────────────────────────────────────────────────────

export function UnknownBlockCard({ block }: { block: UnknownBlock }) {
  return (
    <NoticeCard
      tone="warning"
      icon={AlertTriangle}
      title={
        <span className="font-medium">
          Unsupported block type:{' '}
          <code className="font-mono text-[11px] text-amber-200">{block.declaredType}</code>
        </span>
      }
    >
      <details className="mt-1">
        <summary className="cursor-pointer text-[11px] text-foreground/60">Show raw content</summary>
        <pre className="mt-1 max-h-40 overflow-auto whitespace-pre-wrap break-all font-mono text-[10px] text-foreground/70">
          {JSON.stringify(block.raw, null, 2)}
        </pre>
      </details>
    </NoticeCard>
  );
}

export function DiagnosticsPanel({ diagnostics }: { diagnostics: ResponseDiagnostic[] }) {
  if (diagnostics.length === 0) return null;
  return (
    <NoticeCard
      tone="warning"
      icon={Database}
      dense
      title={`${diagnostics.length} response diagnostic${diagnostics.length === 1 ? '' : 's'}`}
    >
      <details className="group mt-1">
        <summary className="flex cursor-pointer list-none items-center gap-1 text-[11px] text-foreground/60 hover:text-foreground/80">
          <ChevronRight size={11} className="transition-transform group-open:rotate-90" />
          Show details
        </summary>
        <ul className="mt-1 space-y-0.5 pl-4">
          {diagnostics.map((d, i) => (
            <li key={i} className="list-disc text-[11px] text-foreground/70">
              <code className="font-mono">{d.code}</code> — {d.message}
              {d.blockIndex != null ? ` (block #${d.blockIndex})` : ''}
            </li>
          ))}
        </ul>
      </details>
    </NoticeCard>
  );
}

export function ResponseHeader({ response }: { response: ParsedResponse }) {
  if (!response.title && !response.summary) return null;
  return (
    <div className="mb-1">
      {response.title && <h3 className="text-base font-semibold tracking-tight text-foreground">{response.title}</h3>}
      {response.summary && <p className="mt-0.5 text-[13px] text-muted-foreground">{response.summary}</p>}
    </div>
  );
}
