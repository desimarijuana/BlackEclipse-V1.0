'use client';

import { ChatInput } from './chat-input';
import { cn } from '@/lib/utils';

interface EmptyStateProps {
  query: string;
  setQuery: (val: string) => void;
  onSend: (e: React.FormEvent) => void;
  /** Retained for call-site compatibility; the landing shows only the composer. */
  onViewMarketOverview?: () => void;
  /** Opens the document picker — the composer "+" attaches context. */
  onAttach?: () => void;
  /** The assistant is working (rare here, but keeps the composer consistent). */
  busy?: boolean;
  onCancel?: () => void;
  /** Focus mode — narrower centered column; composer stays pinned to the bottom. */
  focus?: boolean;
}

/**
 * The chat landing surface: nothing but the composer, full width. The eclipse
 * background is painted by the chat tab container, so this stays transparent.
 */
export function EmptyState({ query, setQuery, onSend, onAttach, busy, onCancel, focus }: EmptyStateProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-end w-full px-4 md:px-6 pb-2 z-10 relative">
      <div
        className={cn(
          'animate-fade-in-up w-full mx-auto transition-[max-width] duration-500 ease-out',
          focus ? 'max-w-[860px]' : 'max-w-[1400px]',
        )}
        data-chat-composer
      >
        <ChatInput
          query={query}
          setQuery={setQuery}
          onSend={onSend}
          onAttach={onAttach}
          busy={busy}
          onCancel={onCancel}
        />
      </div>
    </div>
  );
}
