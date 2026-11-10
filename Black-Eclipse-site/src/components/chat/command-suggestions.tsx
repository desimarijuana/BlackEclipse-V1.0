'use client';

import { createPortal } from 'react-dom';
import type { RefObject } from 'react';
import { Sparkles } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useT } from '@/lib/i18n/use-t';
import type {
  CommandSuggestion,
  SuggestionContext,
} from '@/lib/harness/command-suggest';
import type { CommandPaletteAnchor } from './command-palette';

export interface CommandSuggestionsProps {
  anchor: CommandPaletteAnchor | null;
  open: boolean;
  context: SuggestionContext | null;
  candidates: readonly CommandSuggestion[];
  loading: boolean;
  highlight: number;
  onHighlight: (index: number) => void;
  onSelect: (value: string) => void;
  listRef: RefObject<HTMLDivElement | null>;
}

/** Argument hints for the command currently being typed (skills, symbols, …). */
export function CommandSuggestions({
  anchor,
  open,
  context,
  candidates,
  loading,
  highlight,
  onHighlight,
  onSelect,
  listRef,
}: CommandSuggestionsProps) {
  const t = useT();
  if (!open || !anchor || !context || typeof document === 'undefined') return null;
  return createPortal(
    <div
      style={{ position: 'fixed', left: anchor.left, width: anchor.width, bottom: anchor.bottom }}
      className="z-[121] overflow-hidden rounded-2xl glass-command-popover shadow-lg"
    >
      <div className="flex items-center gap-1.5 px-3 pb-1 pt-2 text-[10px] uppercase tracking-wide text-muted-foreground/60">
        <Sparkles size={10} />
        {t('code.command.suggestions')} · {context.provider}
        {loading && <span className="ml-auto animate-pulse text-muted-foreground/40">…</span>}
      </div>
      <div ref={listRef} role="listbox" aria-label={t('code.command.suggestions')} className="max-h-[32vh] overflow-y-auto">
        {candidates.map((candidate, index) => (
          <button
            key={`${candidate.value}:${index}`}
            type="button"
            role="option"
            aria-selected={index === highlight}
            onMouseEnter={() => onHighlight(index)}
            onMouseDown={(e) => {
              e.preventDefault();
              onSelect(candidate.value);
            }}
            className={cn(
              'flex w-full items-center gap-2 px-3 py-1.5 text-left',
              index === highlight ? 'bg-accent/40' : 'hover:bg-accent/25',
            )}
          >
            <span className="min-w-0 flex-1 truncate text-xs text-foreground">{candidate.label}</span>
            {candidate.subtitle && (
              <span className="hidden min-w-0 max-w-[50%] truncate text-[10px] text-muted-foreground/60 sm:inline">
                {candidate.subtitle}
              </span>
            )}
            <span className="shrink-0 font-mono text-[10px] text-muted-foreground/40">{candidate.value}</span>
          </button>
        ))}
      </div>
    </div>,
    document.body,
  );
}
