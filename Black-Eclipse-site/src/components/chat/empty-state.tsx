'use client';

import { ChatInput, type AttachmentChip } from './chat-input';
import { cn } from '@/lib/utils';
import type { ChatModelState } from '@/lib/agent/use-chat-model';
import type { ReasoningEffortState } from '@/lib/agent/use-reasoning-effort';
import type { MentionTarget } from '@/lib/bots/mentions';

interface EmptyStateProps {
  query: string;
  setQuery: (val: string) => void;
  onSend: (e: React.FormEvent) => void;
  /** Retained for call-site compatibility; the landing shows only the composer. */
  onViewMarketOverview?: () => void;
  /** Opens the document picker — the composer "+" attaches context. */
  onAttach?: () => void;
  /** Attached documents shown as visible chips above the composer. */
  attachments?: AttachmentChip[];
  onRemoveAttachment?: (name: string) => void;
  /** The assistant is working (rare here, but keeps the composer consistent). */
  busy?: boolean;
  onCancel?: () => void;
  /** Focus mode — full-width column; composer stays pinned to the bottom. */
  focus?: boolean;
  /** The composer's real model selector state. */
  modelState?: ChatModelState;
  /** The composer's per-question reasoning-effort state. */
  effortState?: ReasoningEffortState;
  /** Bots + group chats the user can `@`-mention from the composer. */
  mentionTargets?: MentionTarget[];
}

/**
 * The chat landing surface: nothing but the composer, full width. The eclipse
 * background is painted by the chat tab container, so this stays transparent.
 */
export function EmptyState({ query, setQuery, onSend, onAttach, attachments, onRemoveAttachment, busy, onCancel, focus, modelState, effortState, mentionTargets }: EmptyStateProps) {
  return (
    <div className="flex-1 flex flex-col items-center justify-end w-full px-4 md:px-6 pb-2 z-10 relative">
      <div
        className={cn(
          'animate-fade-in-up w-full mx-auto transition-[max-width] duration-500 ease-out',
          focus ? 'max-w-none' : 'max-w-[1400px]',
        )}
        data-chat-composer
      >
        <ChatInput
          query={query}
          setQuery={setQuery}
          onSend={onSend}
          onAttach={onAttach}
          attachments={attachments}
          onRemoveAttachment={onRemoveAttachment}
          busy={busy}
          onCancel={onCancel}
          modelState={modelState}
          effortState={effortState}
          mentionTargets={mentionTargets}
        />
      </div>
    </div>
  );
}
