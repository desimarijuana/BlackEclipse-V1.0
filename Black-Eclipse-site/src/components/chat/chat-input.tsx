'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';
import { Plus, Mic, ArrowUp, Pause, Loader2, Sparkles, FileText, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { getAgentProvider } from '@/lib/agent/registry';

// Grow the composer to roughly four lines, then scroll instead of growing.
const MAX_HEIGHT = 120;

/** One attached file shown as a chip above the composer. */
export interface AttachmentChip {
  name: string;
  /** True while the upload is still in flight (for a pending attachment). */
  uploading?: boolean;
}

interface ChatInputProps {
  query: string;
  setQuery: (val: string) => void;
  onSend: (e: React.FormEvent) => void;
  placeholder?: string;
  autoFocus?: boolean;
  /** Show the real configured provider label as a quiet pill. */
  showProvider?: boolean;
  /** The assistant is working: submit becomes a pause (cancel) button. */
  busy?: boolean;
  /** Called when the user clicks pause. */
  onCancel?: () => void;
  /** Opens the file picker — the "+" is the attach-documents affordance. */
  onAttach?: () => void;
  /** Shows a spinner on the "+" while documents upload. */
  attaching?: boolean;
  /**
   * Attached documents rendered as visible chips above the composer, so an
   * attachment is obviously present without expanding anything. Removing a chip
   * calls `onRemoveAttachment` with its name.
   */
  attachments?: AttachmentChip[];
  onRemoveAttachment?: (name: string) => void;
  /**
   * A short "context used" label (e.g. `4.2k / 60k`). Rendered quietly under
   * the composer; omitted when there is nothing to report.
   */
  contextLabel?: string;
  /** 0–1 fraction for the small usage meter. */
  contextFraction?: number;
}

export function ChatInput({ 
  query, 
  setQuery, 
  onSend, 
  placeholder = "Ask about a stock, sector, or market trend...", 
  autoFocus,
  showProvider = true,
  busy = false,
  onCancel,
  onAttach,
  attaching = false,
  attachments,
  onRemoveAttachment,
  contextLabel,
  contextFraction,
  }: ChatInputProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // The REAL configured provider, never a fabricated model list.
  const providerLabel = useMemo(() => getAgentProvider().label, []);

  // Auto-grow the composer with its content up to a cap, then scroll. A long
  // prompt no longer stays clipped on one line.
  const resize = useCallback(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = 'auto';
    const needed = el.scrollHeight;
    el.style.height = `${Math.min(needed, MAX_HEIGHT)}px`;
    // Only show a scrollbar once the content truly exceeds the cap; otherwise a
    // 1px rounding gap would render a full-height thumb next to the buttons.
    el.style.overflowY = needed > MAX_HEIGHT ? 'auto' : 'hidden';
  }, []);

  useEffect(() => { resize(); }, [query, resize]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends; Shift+Enter inserts a newline. Ignore IME composition.
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      if (!busy) onSend(e);
    }
  };

  const filled = Math.max(0, Math.min(1, contextFraction ?? 0));

  return (
    <div className="w-full">
      {attachments && attachments.length > 0 && (
        <div className="mb-2 flex flex-wrap items-center gap-1.5" aria-label="Attached documents">
          {attachments.map((file) => (
            <span
              key={file.name}
              className="group inline-flex max-w-[240px] items-center gap-1.5 rounded-full border border-primary/30 bg-primary/10 py-1 pl-2 pr-1 text-[11px] text-foreground/90"
              title={file.name}
            >
              {file.uploading ? (
                <Loader2 size={12} className="shrink-0 animate-spin text-primary" />
              ) : (
                <FileText size={12} className="shrink-0 text-primary" />
              )}
              <span className="min-w-0 truncate">{file.name}</span>
              {onRemoveAttachment && (
                <button
                  type="button"
                  onClick={() => onRemoveAttachment(file.name)}
                  title="Remove attachment"
                  aria-label={`Remove ${file.name}`}
                  className="shrink-0 rounded-full p-0.5 text-muted-foreground/70 hover:bg-white/10 hover:text-foreground"
                >
                  <X size={11} />
                </button>
              )}
            </span>
          ))}
        </div>
      )}
      <form onSubmit={onSend} aria-busy={busy} className="relative flex items-end w-full glass-card border border-white/10 dark:border-white/5 rounded-3xl px-1.5 sm:px-3 py-1 shadow-lg shadow-black/20 focus-within:border-primary focus-within:glass-card transition-colors overflow-hidden">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onAttach}
          disabled={attaching}
          title="Add documents as context"
          aria-label="Add documents as context"
          className="flex text-muted-foreground hover:text-foreground rounded-full hover:bg-accent shrink-0 h-8 w-8 mb-0.5 focus-visible:ring-0 focus-visible:outline-none"
        >
          {attaching ? <Loader2 size={17} className="animate-spin" /> : <Plus size={17} />}
        </Button>
        
        <textarea 
          ref={textareaRef}
          rows={1}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={placeholder}
          autoFocus={autoFocus}
          aria-label="Message Eclipse"
          className="chat-composer-scroll flex-1 self-center bg-transparent border-0 outline-none resize-none overflow-y-hidden placeholder:text-muted-foreground text-foreground pl-3 sm:pl-4 pr-4 sm:pr-5 py-2 text-sm leading-relaxed min-w-0 w-full focus:outline-none focus:ring-0"
        />
        
        <div className="flex items-center gap-1 sm:gap-2 shrink-0 mb-0.5">
          {showProvider && (
            /* The real configured provider — not a fabricated model picker. */
            <span
              className="hidden min-[400px]:inline-flex items-center gap-1.5 px-3 py-1 h-7 rounded-full bg-accent/25 border border-border/25 text-muted-foreground text-xs font-medium whitespace-nowrap"
              title={`Chat provider: ${providerLabel}`}
            >
              <Sparkles size={12} className="text-primary" />
              {providerLabel}
            </span>
          )}
          <Button 
            type="button" 
            variant="ghost" 
            size="icon" 
            className="p-1.5 text-muted-foreground hover:text-foreground rounded-full hover:bg-accent shrink-0 h-8 w-8 focus-visible:ring-0 focus-visible:outline-none"
          >
            <Mic size={16} />
          </Button>
          {busy ? (
            <Button
              type="button"
              size="icon"
              onClick={onCancel}
              title="Stop generating"
              aria-label="Stop generating"
              className="p-1.5 bg-foreground/90 text-background hover:bg-foreground rounded-full shrink-0 h-8 w-8 cursor-pointer transition-colors flex items-center justify-center focus-visible:ring-0 focus-visible:outline-none"
            >
              <Pause size={15} fill="currentColor" />
            </Button>
          ) : (
            <Button 
              type="submit" 
              size="icon" 
              disabled={!query.trim()}
              className="p-1.5 bg-primary text-primary-foreground hover:bg-primary/90 rounded-full shrink-0 h-8 w-8 cursor-pointer disabled:opacity-40 disabled:hover:bg-primary transition-opacity flex items-center justify-center focus-visible:ring-0 focus-visible:outline-none"
            >
              <ArrowUp size={17} />
            </Button>
          )}
        </div>
      </form>

      {contextLabel && (
        <div className="mt-1.5 flex items-center justify-center gap-2 text-[11px] text-muted-foreground/70">
          <span className="tabular-nums">Context {contextLabel}</span>
          <span className="h-1 w-16 overflow-hidden rounded-full bg-accent/50">
            <span
              className={cn(
                'block h-full rounded-full transition-all',
                filled >= 0.9 ? 'bg-amber-400/80' : 'bg-primary/60',
              )}
              style={{ width: `${Math.max(2, filled * 100)}%` }}
            />
          </span>
        </div>
      )}
    </div>
  );
}
