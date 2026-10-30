'use client';

// ── TtsButton — one "Read aloud / Stop" control ─────────────────────────────
// Shared by the chat transcript footer, structured-response header and bot
// messages. It hides itself when the browser exposes no Web Speech API or the
// reply has nothing speakable, so it never offers an action that cannot work.

import { useId, useMemo } from 'react';
import { Square, Volume2 } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { toSpeakableText, useTts } from '@/lib/tts';
import { hasResponseFence } from '@/lib/response/fence-check';

export interface TtsButtonProps {
  /** Raw reply content (Markdown, possibly an `eclipse-response` fence). */
  content: string;
  /** Stable id for the Stop state; defaults to this instance's React id. */
  speakKey?: string;
  variant?: 'icon' | 'pill';
  className?: string;
  label?: string;
  stopLabel?: string;
}

export function TtsButton({
  content,
  speakKey,
  variant = 'icon',
  className,
  label = 'Read aloud',
  stopLabel = 'Stop reading',
}: TtsButtonProps) {
  const { available, speakingKey, prefs, speak, stop } = useTts();
  const generatedKey = useId();
  const key = speakKey ?? generatedKey;
  const speaking = speakingKey === key;
  const structured = hasResponseFence(content);
  // Plain replies are cheap to project up front; a reply that is only code has
  // nothing to say, so the control is not offered at all.
  const speakable = useMemo(
    () => (structured ? '' : toSpeakableText(content)),
    [content, structured],
  );

  if (!available || !prefs.enabled || !content.trim()) return null;
  if (!structured && !speakable) return null;

  const onClick = () => {
    if (speaking) stop();
    else speak(key, content);
  };

  const title = speaking ? stopLabel : label;

  if (variant === 'pill') {
    return (
      <button
        type="button"
        onClick={onClick}
        title={title}
        aria-label={title}
        aria-pressed={speaking}
        className={cn(
          'inline-flex items-center gap-1 rounded-full border border-border/50 px-2 py-1 text-[11px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground',
          speaking && 'border-primary/40 text-primary',
          className,
        )}
      >
        {speaking ? <Square size={11} /> : <Volume2 size={11} />}
        {speaking ? stopLabel : label}
      </button>
    );
  }

  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      aria-label={title}
      aria-pressed={speaking}
      className={cn(
        'flex items-center rounded-full p-1.5 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground cursor-pointer',
        speaking && 'text-primary',
        className,
      )}
    >
      {speaking ? <Square size={11} /> : <Volume2 size={11} />}
    </button>
  );
}

export default TtsButton;
