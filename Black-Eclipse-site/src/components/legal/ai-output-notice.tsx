'use client';

// ── AiOutputNotice — the point-of-use risk notice ───────────────────────────
// Two placements, one source of truth:
//   output   — a compact row under every settled AI answer: the label plus ONE
//              short responsibility clause, expandable to the full notice.
//   composer — the persistent one-liner near the chat input.
//
// The full paragraph is never repeated inline: repetition causes banner
// blindness, which weakens the conspicuousness the notice is meant to create
// (docs/legal/disclosures.md).

import { Info } from '@/lib/icons';
import { cn } from '@/lib/utils';
import {
  AI_COMPOSER_NOTICE,
  AI_OUTPUT_INLINE,
  AI_OUTPUT_LABEL,
  RISK_DISCLOSURE_FULL,
} from '@/lib/legal/disclosure';

export function AiOutputNotice({
  variant = 'output',
  className,
}: {
  variant?: 'output' | 'composer';
  className?: string;
}) {
  const composer = variant === 'composer';

  return (
    <div
      role="note"
      aria-label="AI output disclaimer"
      className={cn(
        'text-muted-foreground/70',
        composer
          ? 'flex flex-wrap items-center justify-center gap-x-1.5 px-2 text-center text-[10px] leading-snug'
          : 'mt-1.5 flex flex-wrap items-center gap-x-1.5 rounded-lg border border-border/35 bg-muted/20 px-2.5 py-1.5 text-[10.5px] leading-snug',
        className,
      )}
    >
      <span className="inline-flex items-center gap-1.5">
        <Info size={11} aria-hidden className="shrink-0" />
        <span className="font-medium text-muted-foreground">{AI_OUTPUT_LABEL}</span>
        <span aria-hidden>·</span>
        <span>{composer ? AI_COMPOSER_NOTICE : AI_OUTPUT_INLINE}</span>
      </span>
      <details className="group inline-block align-baseline">
        <summary className="cursor-pointer list-none text-[10px] text-muted-foreground/60 underline decoration-dotted underline-offset-2 hover:text-foreground">
          {composer ? 'Notice' : 'Full notice'}
        </summary>
        <p className="mt-1 max-w-prose text-left text-[10px] leading-relaxed text-muted-foreground/65">
          {RISK_DISCLOSURE_FULL}
        </p>
      </details>
    </div>
  );
}
