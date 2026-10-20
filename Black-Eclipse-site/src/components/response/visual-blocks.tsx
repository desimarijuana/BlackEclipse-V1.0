'use client';

// ── Website-style visual blocks ────────────────────────────────────────────────
// Presentational renderers for the "figure" family: stat hero, gauges, comparison
// grid, ranked list, badge row and a slide carousel. They render *validated* data
// only and never execute model output. Every numeric value is shown verbatim; a
// bar that is clipped by its `max` still displays the true number, so no visual
// can ever overstate the data.

import { useState, type ReactNode } from 'react';
import {
  Check,
  ChevronLeft,
  ChevronRight,
  Minus,
  TrendingDown,
  TrendingUp,
  X,
  type LucideIcon,
} from '@/lib/icons';
import { cn } from '@/lib/utils';
import { isUnavailableText } from '@/lib/chat/markdown';
import { resolveResponseIcon } from '@/lib/response/icons';
import type {
  BadgeRowBlock as BadgeRowBlockType,
  CarouselBlock as CarouselBlockType,
  ComparisonGridBlock as ComparisonGridBlockType,
  GaugeBlock as GaugeBlockType,
  RankedListBlock as RankedListBlockType,
  StatHeroBlock as StatHeroBlockType,
  ValidatedBlock,
} from '@/lib/response/contract';

type Tone = 'neutral' | 'info' | 'success' | 'warning' | 'danger';

const TONE_FILL: Record<Tone, string> = {
  neutral: 'bg-muted-foreground/40',
  info: 'bg-sky-500/70',
  success: 'bg-emerald-500/70',
  warning: 'bg-amber-500/70',
  danger: 'bg-rose-500/70',
};

const TONE_TEXT: Record<Tone, string> = {
  neutral: 'text-muted-foreground',
  info: 'text-sky-300',
  success: 'text-emerald-300',
  warning: 'text-amber-300',
  danger: 'text-rose-300',
};

const TONE_PILL: Record<Tone, string> = {
  neutral: 'border-border/50 bg-accent/30 text-muted-foreground',
  info: 'border-sky-500/30 bg-sky-500/10 text-sky-200/90',
  success: 'border-emerald-500/30 bg-emerald-500/10 text-emerald-200/90',
  warning: 'border-amber-500/30 bg-amber-500/10 text-amber-200/90',
  danger: 'border-rose-500/30 bg-rose-500/10 text-rose-200/90',
};

function numeric(value: string | number): number | null {
  const n = typeof value === 'number' ? value : Number(String(value).replace(/[%,$\s]/g, ''));
  return Number.isFinite(n) ? n : null;
}

function UnavailableChip() {
  return (
    <span className="rounded border border-border/50 bg-accent/20 px-1.5 py-0.5 text-[0.7em] font-medium uppercase tracking-wide text-muted-foreground/80">
      UNAVAILABLE
    </span>
  );
}

/**
 * The honest empty state for a figure block: the producer marked the whole block
 * `unavailable` (or supplied no data points). The figure is NOT rendered blank —
 * the UNAVAILABLE state and the producer's explanation are shown instead.
 */
function UnavailableFigure({ note }: { note?: string }) {
  return (
    <div className="glass-card-subtle flex flex-wrap items-center gap-2 rounded-xl px-3 py-2.5">
      <UnavailableChip />
      {note && <span className="min-w-0 flex-1 text-[11.5px] text-muted-foreground/80">{note}</span>}
    </div>
  );
}

function DeltaBadge({ delta, tone }: { delta: string | number; tone?: 'up' | 'down' | 'flat' | 'neutral' }) {
  const n = numeric(delta);
  const resolved = tone ?? (n == null ? 'neutral' : n > 0 ? 'up' : n < 0 ? 'down' : 'flat');
  const Icon = resolved === 'up' ? TrendingUp : resolved === 'down' ? TrendingDown : Minus;
  const cls = resolved === 'up' ? 'text-emerald-400' : resolved === 'down' ? 'text-rose-400' : 'text-muted-foreground/70';
  return (
    <span className={cn('inline-flex items-center gap-1 text-[11px] font-medium', cls)}>
      <Icon size={11} />
      {typeof delta === 'number' ? `${delta > 0 ? '+' : ''}${delta}` : delta}
    </span>
  );
}

// ── Stat hero ──────────────────────────────────────────────────────────────────

export function StatHeroBlock({ block }: { block: StatHeroBlockType }) {
  const cols = block.stats.length;
  const gridClass = cols <= 1 ? 'grid-cols-1' : cols === 2 ? 'grid-cols-1 sm:grid-cols-2' : 'grid-cols-2 md:grid-cols-4';
  const empty = block.unavailable === true || cols === 0;
  return (
    <div className="w-full">
      {(block.title || block.source || block.asOf) && (
        <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-2">
          {block.title && <h4 className="text-sm font-semibold text-foreground">{block.title}</h4>}
          {(block.source || block.asOf) && (
            <span className="font-mono text-[10px] text-muted-foreground/60">
              {block.source}
              {block.source && block.asOf ? ' · ' : ''}
              {block.asOf}
            </span>
          )}
        </div>
      )}
      {empty ? (
        <UnavailableFigure note={block.description ?? block.caption} />
      ) : (
        <div className={cn('grid gap-2.5', gridClass)}>
          {block.stats.map((stat, i) => {
            const unavailable = stat.unavailable || (typeof stat.value === 'string' && isUnavailableText(stat.value));
            const Icon: LucideIcon = resolveResponseIcon(stat.icon);
            return (
              <div key={i} className="glass-card rounded-xl px-3.5 py-3">
                <div className="flex items-center gap-1.5 text-muted-foreground/70">
                  {stat.icon && <Icon size={13} />}
                  <p className="truncate text-[11px] uppercase tracking-wide" title={stat.hint}>
                    {stat.label}
                  </p>
                </div>
                <div className="mt-1.5 flex items-baseline gap-1.5">
                  {unavailable ? (
                    <UnavailableChip />
                  ) : (
                    <>
                      {stat.prefix && <span className="text-[15px] text-muted-foreground">{stat.prefix}</span>}
                      <span className="text-[30px] font-semibold leading-none tracking-tight tabular-nums text-foreground">
                        {typeof stat.value === 'number'
                          ? stat.value.toLocaleString()
                          : typeof stat.value === 'string'
                            ? stat.value
                            : ''}
                      </span>
                      {stat.unit && <span className="text-[13px] text-muted-foreground">{stat.unit}</span>}
                    </>
                  )}
                </div>
                <div className="mt-1.5 flex items-center justify-between gap-2">
                  {stat.delta != null && <DeltaBadge delta={stat.delta} tone={stat.deltaTone} />}
                  {stat.hint && (
                    <span className="truncate text-[10px] text-muted-foreground/50" title={stat.hint}>
                      {stat.hint}
                    </span>
                  )}
                </div>
                {stat.provenance && (stat.provenance.source || stat.provenance.asOf) && (
                  <p
                    className="mt-1 truncate text-[9.5px] text-muted-foreground/50"
                    title={stat.provenance.method ?? stat.provenance.source}
                  >
                    {stat.provenance.source}
                    {stat.provenance.source && stat.provenance.asOf ? ' · ' : ''}
                    {stat.provenance.asOf}
                  </p>
                )}
                {stat.provenance?.formula && (
                  <p
                    className="mt-0.5 truncate font-mono text-[9.5px] text-muted-foreground/60"
                    title={stat.provenance.formula}
                  >
                    {stat.provenance.formula}
                  </p>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Gauge / progress ────────────────────────────────────────────────────────────

export function GaugeBlock({ block }: { block: GaugeBlockType }) {
  const empty = block.unavailable === true || block.gauges.length === 0;
  return (
    <div className="w-full">
      {block.title && <h4 className="mb-1 text-sm font-semibold text-foreground">{block.title}</h4>}
      {block.description && <p className="mb-2 text-[12px] text-muted-foreground">{block.description}</p>}
      {empty ? (
        <UnavailableFigure note={block.caption ?? block.description} />
      ) : (
        <div className="space-y-2.5">
          {block.gauges.map((gauge, i) => {
            const pct = Math.max(0, Math.min(100, (gauge.value / gauge.max) * 100));
            return (
              <div key={i} className="glass-card-subtle rounded-xl px-3 py-2.5">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-[12px] font-medium text-foreground" title={gauge.hint ?? gauge.label}>
                    {gauge.label}
                  </span>
                  <span className="shrink-0 text-[12px] tabular-nums text-muted-foreground">
                    <span className="text-foreground">{gauge.value.toLocaleString()}</span>
                    <span className="text-muted-foreground/60">
                      {' '}
                      / {gauge.max.toLocaleString()}
                      {gauge.unit ? ` ${gauge.unit}` : ''}
                    </span>
                  </span>
                </div>
                <div
                  className="mt-1.5 h-2 w-full overflow-hidden rounded-full bg-accent/40"
                  role="progressbar"
                  aria-valuenow={gauge.value}
                  aria-valuemin={0}
                  aria-valuemax={gauge.max}
                  aria-label={gauge.label}
                >
                  <div className={cn('h-full rounded-full transition-[width] duration-300', TONE_FILL[gauge.tone])} style={{ width: `${pct}%` }} />
                </div>
                {gauge.hint && <p className="mt-1 text-[10px] text-muted-foreground/60">{gauge.hint}</p>}
              </div>
            );
          })}
        </div>
      )}
      {block.caption && !empty && <p className="mt-1 text-[10px] text-muted-foreground/60">{block.caption}</p>}
    </div>
  );
}

// ── Comparison grid ─────────────────────────────────────────────────────────────

function ComparisonCell({ value }: { value: boolean | string | number | null }) {
  if (value === true) return <Check size={15} className="mx-auto text-emerald-400" aria-label="yes" />;
  if (value === false) return <X size={15} className="mx-auto text-muted-foreground/40" aria-label="no" />;
  if (value == null) return <span className="text-muted-foreground/30">—</span>;
  return <span className="text-[12.5px] text-foreground/90">{String(value)}</span>;
}

export function ComparisonGridBlock({ block }: { block: ComparisonGridBlockType }) {
  const empty = block.unavailable === true || block.columns.length === 0 || block.rows.length === 0;
  return (
    <div className="w-full">
      {block.title && <h4 className="mb-1.5 text-sm font-semibold text-foreground">{block.title}</h4>}
      {empty ? (
        <UnavailableFigure note={block.caption} />
      ) : (
        <div className="glass-card-subtle overflow-x-auto rounded-xl">
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-white/10 bg-black/[0.03] dark:bg-white/[0.04]">
                <th className="px-3 py-2.5 text-[11px] font-medium uppercase tracking-wide text-muted-foreground/50" />
                {block.columns.map((col, i) => (
                  <th
                    key={i}
                    className={cn(
                      'px-3 py-2.5 text-center text-[12.5px] font-semibold tracking-tight',
                      col.highlight
                        ? 'border-t-2 border-primary/60 bg-primary/10 text-primary'
                        : 'text-foreground/85',
                    )}
                  >
                    {col.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, r) => (
                <tr key={r} className="border-b border-white/[0.06] last:border-0">
                  <th
                    scope="row"
                    className="px-3 py-2 text-left text-[12.5px] font-medium text-muted-foreground"
                    title={row.hint}
                  >
                    {row.label}
                  </th>
                  {block.columns.map((col, c) => (
                    <td key={c} className={cn('px-3 py-2 text-center align-middle', col.highlight && 'bg-primary/[0.05]')}>
                      <ComparisonCell value={row.values[c] ?? null} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {block.caption && !empty && <p className="mt-1 text-[10px] text-muted-foreground/60">{block.caption}</p>}
    </div>
  );
}

// ── Ranked list ─────────────────────────────────────────────────────────────────

export function RankedListBlock({ block }: { block: RankedListBlockType }) {
  const maxAbs = block.items.reduce((m, item) => Math.max(m, Math.abs(item.value)), 0) || 1;
  const empty = block.unavailable === true || block.items.length === 0;
  return (
    <div className="w-full">
      <div className="mb-1.5 flex flex-wrap items-baseline justify-between gap-2">
        {block.title && <h4 className="text-sm font-semibold text-foreground">{block.title}</h4>}
        {block.valueLabel && <span className="text-[10px] uppercase tracking-wide text-muted-foreground/60">{block.valueLabel}</span>}
      </div>
      {block.description && <p className="mb-2 text-[12px] text-muted-foreground">{block.description}</p>}
      {empty ? (
        <UnavailableFigure note={block.caption} />
      ) : (
        <ol className="space-y-1.5">
          {block.items.map((item, i) => {
            const Icon: LucideIcon = resolveResponseIcon(item.icon);
            const pct = Math.max(2, (Math.abs(item.value) / maxAbs) * 100);
            return (
              <li key={i} className="glass-card-subtle flex items-center gap-2.5 rounded-lg px-2.5 py-1.5">
                <span className="w-5 shrink-0 text-right font-mono text-[11px] tabular-nums text-muted-foreground/60">{i + 1}</span>
                {item.icon && (
                  <span className={cn('shrink-0', TONE_TEXT[item.tone])}>
                    <Icon size={14} />
                  </span>
                )}
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="truncate text-[12.5px] font-medium text-foreground" title={item.label}>
                      {item.label}
                    </span>
                    <span className="shrink-0 text-[12px] tabular-nums text-foreground/90">
                      {item.display ?? item.value.toLocaleString()}
                      {item.unit && <span className="ml-0.5 text-[10px] text-muted-foreground">{item.unit}</span>}
                    </span>
                  </div>
                  <div className="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-accent/40">
                    <div className={cn('h-full rounded-full', TONE_FILL[item.tone])} style={{ width: `${pct}%` }} />
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {block.caption && !empty && <p className="mt-1 text-[10px] text-muted-foreground/60">{block.caption}</p>}
    </div>
  );
}

// ── Badge row ───────────────────────────────────────────────────────────────────

export function BadgeRowBlock({ block }: { block: BadgeRowBlockType }) {
  const empty = block.unavailable === true || block.badges.length === 0;
  return (
    <div className="w-full">
      {block.title && <h4 className="mb-1 text-sm font-semibold text-foreground">{block.title}</h4>}
      {block.description && <p className="mb-1.5 text-[12px] text-muted-foreground">{block.description}</p>}
      {empty ? (
        <UnavailableFigure note={block.caption} />
      ) : (
        <div className="flex flex-wrap gap-1.5">
          {block.badges.map((badge, i) => {
            const Icon: LucideIcon = resolveResponseIcon(badge.icon);
            return (
              <span
                key={i}
                className={cn(
                  'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-[11.5px] font-medium',
                  TONE_PILL[badge.tone],
                )}
              >
                {badge.icon && <Icon size={11} />}
                {badge.label}
              </span>
            );
          })}
        </div>
      )}
      {block.caption && !empty && <p className="mt-1 text-[10px] text-muted-foreground/60">{block.caption}</p>}
    </div>
  );
}

// ── Carousel ────────────────────────────────────────────────────────────────────

/**
 * A slide carousel over nested blocks. One slide is visible at a time, with
 * prev/next buttons and dot navigation (keyboard-reachable; each dot is a real
 * button). Nested blocks were validated recursively by the parser. A single
 * slide renders without any navigation chrome.
 */
export function CarouselBlock({
  block,
  renderBlocks,
}: {
  block: CarouselBlockType;
  renderBlocks: (blocks: ValidatedBlock[]) => ReactNode;
}) {
  const [index, setIndex] = useState(0);
  const count = block.slides.length;
  const current = block.slides[Math.min(index, count - 1)];
  const many = count > 1;
  const go = (next: number) => setIndex(((next % count) + count) % count);

  const navBtn =
    'inline-flex h-7 w-7 items-center justify-center rounded-full border border-border/50 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground';

  return (
    <div className="w-full">
      {block.title && <h4 className="mb-1 text-sm font-semibold text-foreground">{block.title}</h4>}
      {block.description && <p className="mb-2 text-[12px] text-muted-foreground">{block.description}</p>}
      <div className="glass-card rounded-xl p-3" role="group" aria-roledescription="carousel" aria-label={block.title ?? 'Carousel'}>
        {many && (
          <div className="mb-2 flex items-center justify-between gap-2">
            <span className="min-w-0 truncate text-[12px] font-medium text-foreground">
              {current?.label ?? current?.title ?? `Slide ${index + 1}`}
            </span>
            <div className="flex shrink-0 items-center gap-1.5">
              <button type="button" className={navBtn} onClick={() => go(index - 1)} aria-label="Previous slide">
                <ChevronLeft size={14} />
              </button>
              <span className="font-mono text-[10px] tabular-nums text-muted-foreground/70">
                {index + 1}/{count}
              </span>
              <button type="button" className={navBtn} onClick={() => go(index + 1)} aria-label="Next slide">
                <ChevronRight size={14} />
              </button>
            </div>
          </div>
        )}
        {current?.title && current.title !== (current.label ?? '') && (
          <h5 className="mb-1.5 text-[13px] font-semibold text-foreground">{current.title}</h5>
        )}
        <div key={index}>{current ? renderBlocks(current.blocks as ValidatedBlock[]) : null}</div>
        {many && (
          <div className="mt-3 flex flex-wrap items-center justify-center gap-1.5">
            {block.slides.map((slide, i) => (
              <button
                key={i}
                type="button"
                onClick={() => setIndex(i)}
                aria-label={`Go to slide ${i + 1}${slide.label ? `: ${slide.label}` : ''}`}
                aria-current={i === index}
                className={cn(
                  'h-1.5 rounded-full transition-all',
                  i === index ? 'w-5 bg-primary' : 'w-1.5 bg-muted-foreground/30 hover:bg-muted-foreground/60',
                )}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
