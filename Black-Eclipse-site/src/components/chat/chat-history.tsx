import { memo, useCallback, useEffect, useRef, useState } from 'react';
import { AlertTriangle, Sparkles, Pencil, RotateCcw, Check, X, Copy, ThumbsUp, ThumbsDown } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Message } from '@/types/chat';
import { Markdown } from './markdown';
import { ResponseStatusLine } from './response-status';
import { ActivityFeed } from './activity-feed';

interface ChatHistoryProps {
  messages: Message[];
  /**
   * `false` (default) is the full-page ChatBot layout (centered wide column,
   * user bubbles only — assistant text renders wide like a code agent).
   * `true` fills a narrow container (e.g. the floating ChatDock) edge-to-edge.
   */
  compact?: boolean;
  /**
   * Called when the user edits a previously-sent prompt. The caller decides
   * what "editing" means (typically: truncate the thread at that message and
   * re-send) — the component only reports the new text.
   */
  onEditMessage?: (id: string, content: string) => void;
  /** Retry a failed assistant turn (re-runs its preceding user prompt). */
  onRetryMessage?: (id: string) => void;
  /** Rate an assistant turn. The caller persists the choice on the message. */
  onFeedback?: (id: string, feedback: 'up' | 'down') => void;
}

/** How close to the bottom counts as "following the stream". */
const NEAR_BOTTOM_PX = 96;

/**
 * Assistant prose is the expensive part to render (full Markdown parse). It only
 * changes when its text does, so memoizing it stops a streaming turn from
 * re-parsing every *other* turn in the transcript.
 */
const AssistantContent = memo(function AssistantContent({
  content,
  compact,
}: {
  content: string;
  compact: boolean;
}) {
  return <Markdown content={content} compact={compact} className="w-full" />;
});

export function ChatHistory({ messages, compact = false, onEditMessage, onRetryMessage, onFeedback }: ChatHistoryProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);

  // Auto-scroll only while the user is already near the bottom. Scrolling up to
  // read while a reply streams must not yank the viewport back down every token.
  const atBottomRef = useRef(true);
  const onScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    atBottomRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < NEAR_BOTTOM_PX;
  }, []);

  useEffect(() => {
    if (!atBottomRef.current) return;
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = el.scrollHeight;
  }, [messages]);

  const startEdit = (msg: Message) => {
    setEditingId(msg.id);
    setDraft(msg.content);
  };

  const commitEdit = () => {
    if (editingId && draft.trim()) onEditMessage?.(editingId, draft.trim());
    setEditingId(null);
  };

  const copyMessage = async (msg: Message) => {
    try {
      await navigator.clipboard.writeText(msg.content);
      setCopiedId(msg.id);
      setTimeout(() => setCopiedId((c) => (c === msg.id ? null : c)), 1500);
    } catch {
      // Clipboard unavailable — leave the button unchanged.
    }
  };

  return (
    <div
      ref={scrollRef}
      onScroll={onScroll}
      className={cn(
        'flex-1 w-full overflow-y-auto scrollbar-hide min-h-0',
        compact ? 'space-y-3 p-3' : 'px-4 md:px-6 space-y-6 pb-6',
      )}
    >
      <div className={compact ? 'space-y-3' : 'space-y-6'}>
        {messages.map((msg) => {
          const working = msg.role === 'assistant' && msg.status != null && msg.status !== 'completed';
          return (
            <div
              key={msg.id}
              className={`group animate-fade-in-up flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
            >
              {msg.role === 'assistant' && !compact && (
                <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary mb-2 border border-primary/20">
                  <Sparkles size={14} />
                </div>
              )}

              {msg.role === 'assistant' && msg.status != null && !(msg.activities && msg.activities.length > 0) && (
                <div className={cn(msg.content ? 'mb-2' : '')}>
                  <ResponseStatusLine status={msg.status} activities={msg.activities} compact={compact} />
                </div>
              )}

              {msg.role === 'assistant' && msg.activities && msg.activities.length > 0 && (
                <ActivityFeed activities={msg.activities} status={msg.status} compact={compact} />
              )}

              {msg.role === 'assistant' ? (
                <>
                  {msg.error && (
                    <div
                      role="alert"
                      className="w-full rounded-xl border border-rose-500/30 bg-rose-500/[0.06] px-3 py-2.5 text-[13px] text-rose-200/90"
                    >
                      <div className="flex items-start gap-2">
                        <AlertTriangle size={14} className="mt-0.5 shrink-0 text-rose-400" />
                        <div className="min-w-0 flex-1">
                          <p className="break-words">{msg.error.message}</p>
                          {onRetryMessage && (
                            <button
                              type="button"
                              onClick={() => onRetryMessage(msg.id)}
                              className="mt-2 inline-flex items-center gap-1 rounded-full border border-rose-500/30 px-2.5 py-1 text-[11px] font-medium text-rose-200 transition-colors hover:bg-rose-500/10 cursor-pointer"
                            >
                              <RotateCcw size={11} /> Retry
                            </button>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                  {msg.content && <AssistantContent content={msg.content} compact={compact} />}
                  {!working && msg.content && (
                    <div className="hover-reveal mt-1 flex flex-wrap items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                      <button
                        type="button"
                        onClick={() => void copyMessage(msg)}
                        className="flex items-center gap-1 rounded-full px-2 py-1 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground transition-colors cursor-pointer"
                        title="Copy response"
                        aria-label="Copy response"
                      >
                        {copiedId === msg.id ? <Check size={11} /> : <Copy size={11} />}
                        {copiedId === msg.id ? 'Copied' : 'Copy'}
                      </button>
                      {onRetryMessage && (
                        <button
                          type="button"
                          onClick={() => onRetryMessage(msg.id)}
                          className="flex items-center gap-1 rounded-full px-2 py-1 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground transition-colors cursor-pointer"
                          title="Regenerate response"
                          aria-label="Regenerate response"
                        >
                          <RotateCcw size={11} /> Regenerate
                        </button>
                      )}
                      {onFeedback && (
                        <span className="ml-0.5 flex items-center gap-0.5 border-l border-border/40 pl-1.5">
                          <button
                            type="button"
                            onClick={() => onFeedback(msg.id, 'up')}
                            aria-pressed={msg.feedback === 'up'}
                            className={cn(
                              'rounded-full p-1.5 transition-colors cursor-pointer hover:bg-accent',
                              msg.feedback === 'up' ? 'text-primary' : 'text-muted-foreground hover:text-foreground',
                            )}
                            title="Good response"
                            aria-label="Good response"
                          >
                            <ThumbsUp size={11} />
                          </button>
                          <button
                            type="button"
                            onClick={() => onFeedback(msg.id, 'down')}
                            aria-pressed={msg.feedback === 'down'}
                            className={cn(
                              'rounded-full p-1.5 transition-colors cursor-pointer hover:bg-accent',
                              msg.feedback === 'down' ? 'text-rose-400' : 'text-muted-foreground hover:text-foreground',
                            )}
                            title="Bad response"
                            aria-label="Bad response"
                          >
                            <ThumbsDown size={11} />
                          </button>
                        </span>
                      )}
                    </div>
                  )}
                </>
              ) : editingId === msg.id ? (
                <div className="w-full flex flex-col gap-2">
                  <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Escape') setEditingId(null);
                      if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) commitEdit();
                    }}
                    autoFocus
                    rows={Math.min(8, Math.max(2, draft.split('\n').length))}
                    className="w-full resize-none rounded-2xl border border-primary/40 bg-card px-4 py-3 text-[14px] md:text-[15px] leading-relaxed text-foreground outline-none focus:ring-1 focus:ring-primary"
                  />
                  <div className="flex items-center justify-end gap-2">
                    <button
                      type="button"
                      onClick={() => setEditingId(null)}
                      className="flex items-center gap-1 rounded-full px-3 py-1.5 text-xs text-muted-foreground hover:bg-accent hover:text-foreground transition-colors cursor-pointer"
                    >
                      <X size={13} /> Cancel
                    </button>
                    <button
                      type="button"
                      onClick={commitEdit}
                      disabled={!draft.trim()}
                      className="flex items-center gap-1 rounded-full bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-40 transition-colors cursor-pointer"
                    >
                      <Check size={13} /> Resend
                    </button>
                  </div>
                </div>
              ) : (
                <div className={cn('group flex flex-col', 'items-end', 'w-full')}>
                  <div className={cn(
                    'leading-relaxed break-words whitespace-pre-wrap bg-card text-foreground border border-border',
                    compact
                      ? 'px-3 py-2 max-w-[90%] text-[13px] rounded-2xl'
                      // Grow with the text up to the full column width: short
                      // prompts stay a compact pill, long ones use every pixel
                      // instead of wrapping early inside a fixed-size bubble.
                      : 'w-fit max-w-full px-4 py-3 md:px-5 md:py-3.5 text-[14px] md:text-[15px] rounded-2xl md:rounded-3xl',
                  )}>
                    {msg.content}
                  </div>
                  {onEditMessage && (
                    <button
                      type="button"
                      onClick={() => startEdit(msg)}
                      className="hover-reveal mt-1 flex items-center gap-1 rounded-full px-2 py-1 text-[11px] text-muted-foreground opacity-0 transition-opacity hover:text-foreground hover:bg-accent group-hover:opacity-100 focus-within:opacity-100 cursor-pointer"
                      title="Edit prompt"
                    >
                      <Pencil size={11} /> Edit
                    </button>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
