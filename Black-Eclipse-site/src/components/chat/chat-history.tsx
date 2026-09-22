import { useEffect, useRef, useState } from 'react';
import { Sparkles, Pencil, Check, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { Message } from '@/types/chat';
import { Markdown } from './markdown';

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
  /**
   * Live agent status while a run is in flight (e.g. "Thinking…",
   * "Using market_get_quote…"). Rendered as a header on the assistant turn
   * being written, so it reads as "the agent is working on THIS reply" rather
   * than a detached line under the composer.
   */
  status?: string;
}

export function ChatHistory({ messages, compact = false, onEditMessage, status }: ChatHistoryProps) {
  const bottomRef = useRef<HTMLDivElement>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState('');

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const startEdit = (msg: Message) => {
    setEditingId(msg.id);
    setDraft(msg.content);
  };

  const commitEdit = () => {
    if (editingId && draft.trim()) onEditMessage?.(editingId, draft.trim());
    setEditingId(null);
  };

  // The status belongs on the assistant turn currently being written — the
  // last message when it is an assistant turn. It shows above that turn's text
  // (a "thinking header"), and while the answer is still empty it IS the turn.
  const statusIndex = (() => {
    if (!status) return -1;
    for (let i = messages.length - 1; i >= 0; i--) {
      if (messages[i].role === 'assistant') return i;
    }
    return -1;
  })();

  const StatusLine = () => (
    <span className="flex items-center gap-1.5 text-[10px] font-mono text-muted-foreground/80">
      <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-primary" />
      {status}
    </span>
  );

  return (
    <div className={cn(
      'flex-1 w-full overflow-y-auto scrollbar-hide min-h-0',
      compact ? 'space-y-3 p-3' : 'px-4 md:px-6 space-y-6 pb-6',
    )}>
      <div className={compact ? 'space-y-3' : 'space-y-6'}>
        {messages.map((msg, i) => (
          <div 
            key={msg.id}
            className={`animate-fade-in-up flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}
          >
            {msg.role === 'assistant' && !compact && (
              <div className="w-8 h-8 rounded-full bg-primary/20 flex items-center justify-center text-primary mb-2 border border-primary/20">
                <Sparkles size={14} />
              </div>
            )}
            {msg.role === 'assistant' && i === statusIndex && (
              <div className={msg.content ? 'mb-2' : ''}>
                <StatusLine />
              </div>
            )}
            {msg.role === 'assistant' ? (
              msg.content ? (
                <Markdown content={msg.content} compact={compact} className="w-full" />
              ) : null
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
              <div className={cn('group flex flex-col', msg.role === 'user' ? 'items-end' : 'items-start', 'w-full')}>
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
                    className="mt-1 hidden items-center gap-1 rounded-full px-2 py-1 text-[11px] text-muted-foreground hover:text-foreground hover:bg-accent group-hover:flex transition-colors cursor-pointer"
                    title="Edit prompt"
                  >
                    <Pencil size={11} /> Edit
                  </button>
                )}
              </div>
            )}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
