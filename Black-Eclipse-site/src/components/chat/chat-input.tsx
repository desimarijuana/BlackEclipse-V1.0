'use client';

import { useCallback, useEffect, useMemo, useRef } from 'react';
import { Plus, Mic, ArrowUp, Pause, Loader2, Sparkles } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { getAgentProvider } from '@/lib/agent/registry';

// Grow the composer to roughly six lines, then scroll instead of growing.
const MAX_HEIGHT = 176;

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
      <form onSubmit={onSend} aria-busy={busy} className="relative flex items-end w-full glass-card border border-white/10 dark:border-white/5 rounded-3xl px-2 sm:px-4 py-1.5 shadow-lg shadow-black/20 focus-within:border-primary focus-within:glass-card transition-colors overflow-hidden">
        <Button
          type="button"
          variant="ghost"
          size="icon"
          onClick={onAttach}
          disabled={attaching}
          title="Add documents as context"
          aria-label="Add documents as context"
          className="flex text-muted-foreground hover:text-foreground rounded-full hover:bg-accent shrink-0 h-10 w-10 mb-1 focus-visible:ring-0 focus-visible:outline-none"
        >
          {attaching ? <Loader2 size={20} className="animate-spin" /> : <Plus size={20} />}
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
          className="chat-composer-scroll flex-1 self-center bg-transparent border-0 outline-none resize-none overflow-y-hidden placeholder:text-muted-foreground text-foreground pl-3 sm:pl-4 pr-4 sm:pr-5 py-3 text-base sm:text-lg leading-relaxed min-w-0 w-full focus:outline-none focus:ring-0"
        />
        
        <div className="flex items-center gap-1 sm:gap-2 shrink-0 mb-1">
          {showProvider && (
            /* The real configured provider — not a fabricated model picker. */
            <span
              className="hidden min-[400px]:inline-flex items-center gap-1.5 px-3 py-1.5 h-8 rounded-full bg-accent/25 border border-border/25 text-muted-foreground text-xs sm:text-sm font-medium whitespace-nowrap"
              title={`Chat provider: ${providerLabel}`}
            >
              <Sparkles size={13} className="text-primary" />
              {providerLabel}
            </span>
          )}
          <Button 
            type="button" 
            variant="ghost" 
            size="icon" 
            className="p-2 text-muted-foreground hover:text-foreground rounded-full hover:bg-accent shrink-0 h-9 w-9 focus-visible:ring-0 focus-visible:outline-none"
          >
            <Mic size={18} className="sm:size-5" />
          </Button>
          {busy ? (
            <Button
              type="button"
              size="icon"
              onClick={onCancel}
              title="Stop generating"
              aria-label="Stop generating"
              className="p-2 bg-foreground/90 text-background hover:bg-foreground rounded-full shrink-0 h-9 w-9 cursor-pointer transition-colors flex items-center justify-center focus-visible:ring-0 focus-visible:outline-none"
            >
              <Pause size={16} className="sm:size-[18px]" fill="currentColor" />
            </Button>
          ) : (
            <Button 
              type="submit" 
              size="icon" 
              disabled={!query.trim()}
              className="p-2 bg-primary text-primary-foreground hover:bg-primary/90 rounded-full shrink-0 h-9 w-9 cursor-pointer disabled:opacity-40 disabled:hover:bg-primary transition-opacity flex items-center justify-center focus-visible:ring-0 focus-visible:outline-none"
            >
              <ArrowUp size={18} className="sm:size-5" />
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
