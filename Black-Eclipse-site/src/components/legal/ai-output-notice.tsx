'use client';

// ── AiOutputNotice — the point-of-use risk notice ───────────────────────────
// Two placements, one source of truth:
//   output   — a compact row under every settled AI answer, expandable to the
//              full notice (docs/legal/disclosures.md).
//   composer — the persistent one-liner near the chat input, so a user who
//              never reads a full answer still sees that the output is AI and
//              not advice.
//
// Deliberately NOT dismissible: the short form always remains. This is the
// "point-of-use label" layer of the layered disclosure model, not the Terms.

import { Info } from '@/lib/icons';
import { cn } from '@/lib/utils';
import {
  AI_COMPOSER_NOTICE,
  AI_OUTPUT_LABEL,
  AI_OUTPUT_SHORT,
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
  // The repeated notice under every settled answer was distracting. The
  // persistent composer one-liner (and the first-run acknowledgement) still
  // carry the disclosure; the output placement is intentionally removed.
  if (!composer) return null;

  return (
    <div
      role="note"
      aria-label="AI output disclaimer"
      className={cn(
        'text-muted-foreground/70',
        composer
          ? 'flex flex-wrap items-center justify-center gap-x-1.5 px-2 text-center text-[10px] leading-snug'
          : 'mt-1.5 rounded-lg border border-border/35 bg-muted/20 px-2.5 py-1.5 text-[10.5px] leading-snug',
        className,
      )}
    >
      <span className="inline-flex items-center gap-1.5">
        <Info size={11} aria-hidden className="shrink-0" />
        <span className="font-medium text-muted-foreground">{AI_OUTPUT_LABEL}</span>
        <span aria-hidden>·</span>
        <span>{composer ? AI_COMPOSER_NOTICE : AI_OUTPUT_SHORT}</span>
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
