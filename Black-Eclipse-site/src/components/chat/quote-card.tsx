'use client';

import { useState } from 'react';
import { MessageSquareText } from '@/lib/icons';
import { quoteSourceLabel } from '@/lib/chat/quote';
import type { MessageQuote } from '@/types/chat';
import { cn } from '@/lib/utils';

const PREVIEW_CHARS = 240;

/**
 * A quoted passage attached to a user turn. Rendered ABOVE the question so the
 * transcript shows exactly what the user pointed at, while `Message.content`
 * stays the question itself.
 */
export function QuoteCard({
  quote,
  onJump,
  compact = false,
}: {
  quote: MessageQuote;
  /** Scroll to (and flash) the source message, when it still exists. */
  onJump?: (messageId: string) => void;
  compact?: boolean;
}) {
  const [expanded, setExpanded] = useState(false);
  const long = quote.text.length > PREVIEW_CHARS;
  const shown = expanded || !long ? quote.text : `${quote.text.slice(0, PREVIEW_CHARS).trimEnd()}…`;
  const source = quoteSourceLabel(quote);

  return (
    <div
      className={cn(
        'mb-2 w-full rounded-xl border border-primary/25 bg-primary/[0.07] px-2.5 py-2 text-left',
        compact ? 'text-[11px]' : 'text-[12px]',
      )}
    >
      <div className="flex items-center gap-1.5 text-primary/90">
        <MessageSquareText size={compact ? 11 : 12} className="shrink-0" />
        <span className="font-semibold">Quoted · {source}</span>
        {onJump && (
          <button
            type="button"
            onClick={() => onJump(quote.messageId)}
            className="ml-auto shrink-0 rounded-full px-1.5 py-0.5 text-[10px] font-medium text-primary/80 transition-colors hover:bg-primary/10 hover:text-primary cursor-pointer"
            title="Jump to the source message"
          >
            Jump to
          </button>
        )}
      </div>
      <div className="mt-1 whitespace-pre-wrap break-words leading-relaxed text-foreground/80">
        {shown}
      </div>
      {long && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="mt-1 text-[10px] font-medium text-primary/80 underline-offset-2 hover:text-primary hover:underline cursor-pointer"
        >
          {expanded ? 'Show less' : 'Show more'}
        </button>
      )}
      {quote.truncated && (
        <p className="mt-1 text-[10px] text-muted-foreground/70">
          The selection was longer than 4,000 characters and was shortened.
        </p>
      )}
    </div>
  );
}
