'use client';

// ── Layout primitives ─────────────────────────────────────────────────────────
// A container a producer composes structure with. Styling is driven ONLY by the
// closed token vocabularies in `lib/response/tokens.ts` (spacing / radius / tone)
// — there is no path from model output to raw CSS or arbitrary classes.

import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import type { DividerBlock as DividerBlockType, LayoutBlock as LayoutBlockType, ValidatedBlock } from '@/lib/response/contract';
import { ALIGN_CLASS, GAP_CLASS, PAD_CLASS, RADIUS_CLASS, TONE_SURFACE } from '@/lib/response/tokens';

const GRID_COLS: Record<number, string> = {
  1: 'grid-cols-1',
  2: 'grid-cols-1 sm:grid-cols-2',
  3: 'grid-cols-1 sm:grid-cols-2 md:grid-cols-3',
  4: 'grid-cols-2 md:grid-cols-4',
};

export function LayoutBlock({
  block,
  renderBlocks,
}: {
  block: LayoutBlockType;
  renderBlocks: (blocks: ValidatedBlock[]) => ReactNode;
}) {
  const tone = TONE_SURFACE[block.tone];
  const spacing = [block.pad ? PAD_CLASS[block.pad] : '', block.radius ? RADIUS_CLASS[block.radius] : '']
    .filter(Boolean)
    .join(' ');

  let container: string;
  if (block.layout === 'grid') {
    container = cn('grid', GRID_COLS[block.columns ?? 2] ?? GRID_COLS[2], GAP_CLASS[block.gap]);
  } else if (block.layout === 'row' || block.layout === 'column') {
    container = cn(
      'flex',
      block.layout === 'row' ? 'flex-row' : 'flex-col',
      block.wrap ? 'flex-wrap' : 'flex-nowrap',
      GAP_CLASS[block.gap],
      block.align ? ALIGN_CLASS[block.align] : '',
    );
  } else {
    container = cn('flex flex-col', GAP_CLASS[block.gap]);
  }

  return (
    <div className="w-full">
      {block.title && <h4 className="mb-1.5 text-sm font-semibold text-foreground">{block.title}</h4>}
      <div className={cn(container, spacing, tone)}>{renderBlocks(block.blocks as ValidatedBlock[])}</div>
    </div>
  );
}

const DIVIDER_TONE: Record<string, string> = {
  neutral: 'border-border/40',
  info: 'border-sky-500/30',
  success: 'border-emerald-500/30',
  warning: 'border-amber-500/30',
  danger: 'border-rose-500/30',
};

export function DividerBlock({ block }: { block: DividerBlockType }) {
  const toneClass = DIVIDER_TONE[block.tone] ?? DIVIDER_TONE.neutral;
  if (!block.label) {
    return <hr className={cn('my-1 border-t', toneClass)} />;
  }
  return (
    <div className="my-1 flex items-center gap-3" role="separator" aria-label={block.label}>
      <span className={cn('h-px flex-1 border-t', toneClass)} />
      <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground/70">{block.label}</span>
      <span className={cn('h-px flex-1 border-t', toneClass)} />
    </div>
  );
}
