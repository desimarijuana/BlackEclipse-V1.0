'use client';

// ── Queued prompts panel ─────────────────────────────────────────────────────
// Sits above the composer. While the agent is working, prompts typed into the
// composer are queued here instead of being dropped; they run in order when the
// current reply finishes. Every row can be edited, reordered, removed, or
// promoted to run next (which interrupts the in-flight reply first).

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ChevronDown, ChevronUp, ListChecks, Pause, Pencil, Play, Trash2, X } from '@/lib/icons';
import { cn } from '@/lib/utils';
import type { QueuedPrompt } from '@/lib/chat/message-queue';
import { isQueuePaused, setQueuePaused, subscribeQueueStore } from '@/lib/chat/queue-store';

interface MessageQueueProps {
  items: QueuedPrompt[];
  /** True while the current run is active — changes the header hint. */
  busy?: boolean;
  onEdit: (id: string, text: string) => void;
  onRemove: (id: string) => void;
  onMove: (id: string, direction: 'up' | 'down') => void;
  /** Promote to the front and stop the current run so it starts next. */
  onRunNow: (id: string) => void;
  onClear: () => void;
}

export function MessageQueue({
  items,
  busy = false,
  onEdit,
  onRemove,
  onMove,
  onRunNow,
  onClear,
}: MessageQueueProps) {
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const editRef = useRef<HTMLTextAreaElement>(null);
  // The panel is filtered to one chat, so the first item names the queue.
  const chatId = items[0]?.chatId ?? null;
  const [paused, setPaused] = useState(false);
  useEffect(() => {
    if (!chatId) return;
    const sync = () => setPaused(isQueuePaused(chatId));
    sync();
    return subscribeQueueStore(sync);
  }, [chatId]);

  useEffect(() => {
    if (editingId) requestAnimationFrame(() => editRef.current?.focus());
  }, [editingId]);

  if (items.length === 0) return null;

  const startEdit = (item: QueuedPrompt) => {
    setEditingId(item.id);
    setDraft(item.text);
  };

  const commitEdit = () => {
    if (!editingId) return;
    onEdit(editingId, draft);
    setEditingId(null);
  };

  return (
    <section
      aria-label="Queued prompts"
      className="mb-2 rounded-2xl border border-white/10 glass-card-subtle px-2.5 py-2"
    >
      <header className="flex items-center gap-1.5 pb-1.5">
        <ListChecks size={13} className="shrink-0 text-primary" />
        <span className="text-[11px] font-semibold text-foreground">
          Queued · {items.length}
        </span>
        <span className="min-w-0 flex-1 truncate text-[10px] text-muted-foreground/70">
          {paused
            ? 'Paused — press play to resume'
            : busy
              ? 'Runs in order after the current reply'
              : 'Ready to run'}
        </span>
        {chatId && (
          <button
            type="button"
            onClick={() => setQueuePaused(chatId, !paused)}
            className="shrink-0 rounded-full p-1 text-muted-foreground/70 transition-colors hover:bg-white/10 hover:text-foreground"
            title={paused ? 'Resume the queue' : 'Pause the queue'}
            aria-label={paused ? 'Resume the queue' : 'Pause the queue'}
          >
            {paused ? <Play size={12} /> : <Pause size={12} />}
          </button>
        )}
        <button
          type="button"
          onClick={onClear}
          className="shrink-0 rounded-full p-1 text-muted-foreground/70 transition-colors hover:bg-white/10 hover:text-rose-300"
          title="Clear the queue"
          aria-label="Clear the queue"
        >
          <X size={12} />
        </button>
      </header>

      <ul className="max-h-40 space-y-1 overflow-y-auto pr-0.5">
        {items.map((item, index) => {
          const editing = editingId === item.id;
          return (
            <li
              key={item.id}
              className="group flex items-start gap-1.5 rounded-lg bg-background/30 px-1.5 py-1"
            >
              <span
                className="mt-0.5 inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-primary/15 text-[9px] font-semibold tabular-nums text-primary"
                aria-hidden
              >
                {index + 1}
              </span>

              {editing ? (
                <textarea
                  ref={editRef}
                  rows={2}
                  value={draft}
                  onChange={(e) => setDraft(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                      e.preventDefault();
                      commitEdit();
                    }
                    if (e.key === 'Escape') {
                      e.preventDefault();
                      setEditingId(null);
                    }
                  }}
                  aria-label="Edit queued prompt"
                  className="min-w-0 flex-1 resize-none rounded-md bg-background/60 px-1.5 py-1 text-xs leading-relaxed text-foreground outline-none focus-visible:ring-1 focus-visible:ring-primary"
                />
              ) : (
                <button
                  type="button"
                  onClick={() => startEdit(item)}
                  title="Click to edit"
                  className="min-w-0 flex-1 truncate text-left text-xs leading-relaxed text-foreground/90 hover:text-foreground"
                >
                  {item.text}
                </button>
              )}

              <div className="flex shrink-0 items-center gap-0.5">
                {editing ? (
                  <>
                    <button
                      type="button"
                      onClick={commitEdit}
                      className="rounded-md px-1.5 py-0.5 text-[10px] font-medium text-primary hover:bg-white/10"
                    >
                      Save
                    </button>
                    <button
                      type="button"
                      onClick={() => setEditingId(null)}
                      className="rounded-md px-1.5 py-0.5 text-[10px] text-muted-foreground hover:bg-white/10"
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <>
                    <IconAction
                      label="Run this next"
                      onClick={() => onRunNow(item.id)}
                      className="hover:text-primary"
                    >
                      <Play size={11} />
                    </IconAction>
                    <IconAction
                      label="Move up"
                      disabled={index === 0}
                      onClick={() => onMove(item.id, 'up')}
                    >
                      <ChevronUp size={11} />
                    </IconAction>
                    <IconAction
                      label="Move down"
                      disabled={index === items.length - 1}
                      onClick={() => onMove(item.id, 'down')}
                    >
                      <ChevronDown size={11} />
                    </IconAction>
                    <IconAction label="Edit prompt" onClick={() => startEdit(item)}>
                      <Pencil size={11} />
                    </IconAction>
                    <IconAction
                      label="Remove prompt"
                      onClick={() => onRemove(item.id)}
                      className="hover:text-rose-300"
                    >
                      <Trash2 size={11} />
                    </IconAction>
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function IconAction({
  label,
  onClick,
  disabled,
  className,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={label}
      aria-label={label}
      className={cn(
        'flex h-5 w-5 items-center justify-center rounded-md text-muted-foreground/70 transition-colors hover:bg-white/10 hover:text-foreground disabled:cursor-default disabled:opacity-30 disabled:hover:bg-transparent',
        className,
      )}
    >
      {children}
    </button>
  );
}
