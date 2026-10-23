'use client';

import { FileText } from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { MessageAttachment } from '@/types/chat';

/**
 * The context documents a user turn carried, shown INSIDE its bubble. A large
 * paste is a document, not a wall of text — but it must still be visible in the
 * transcript, so every turn that used one gets a compact, openable card.
 */
export function MessageAttachments({
  attachments,
  onOpen,
}: {
  attachments?: MessageAttachment[];
  onOpen?: (name: string) => void;
}) {
  if (!attachments || attachments.length === 0) return null;
  return (
    <div className="mt-2 flex w-full flex-col gap-1.5">
      {attachments.map((att, i) => (
        <button
          key={`${att.name}-${i}`}
          type="button"
          disabled={!onOpen}
          onClick={() => onOpen?.(att.name)}
          title={onOpen ? `Open ${att.name}` : att.name}
          className={cn(
            'group/attachment flex w-full items-start gap-2 rounded-xl border border-border/40 px-2 py-1.5 text-left transition-colors glass-card-subtle',
            onOpen ? 'cursor-pointer hover:border-primary/40 hover:bg-accent/30' : 'cursor-default',
          )}
        >
          <span className="mt-px flex h-6 w-6 shrink-0 items-center justify-center rounded-md bg-primary/10 text-primary/80">
            <FileText size={12} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
              <span className="truncate text-[11px] font-semibold text-foreground">
                {att.pasted ? 'Pasted text' : att.name}
              </span>
              {att.pasted && (
                <span className="rounded-full border border-border/50 px-1 py-px text-[8.5px] font-medium uppercase tracking-wide text-muted-foreground">
                  pasted
                </span>
              )}
              {att.chars != null && (
                <span className="font-mono text-[9.5px] text-muted-foreground">
                  {att.chars.toLocaleString()} chars
                </span>
              )}
            </span>
            {att.pasted && (
              <span className="block truncate font-mono text-[9.5px] text-muted-foreground/60">
                {att.name}
              </span>
            )}
            {att.preview && (
              <span className="mt-0.5 line-clamp-2 whitespace-pre-wrap break-words text-[10px] leading-snug text-muted-foreground/75">
                {att.preview}
              </span>
            )}
          </span>
          {onOpen && (
            <span className="shrink-0 self-center text-[9.5px] text-muted-foreground/60 group-hover/attachment:text-foreground">
              Open
            </span>
          )}
        </button>
      ))}
    </div>
  );
}
