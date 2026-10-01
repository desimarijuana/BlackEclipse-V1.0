'use client';

// ── ChatBot wordmark ─────────────────────────────────────────────────────────
// The giant display-type wordmark painted behind the ChatBot landing — e.g.
// "ECLIPSE AGENT" in a high-contrast serif. Authored in Settings › General ›
// Background (text, font, size, strength, alignment, vertical position) and
// stored on the background store; this component is purely presentational.
//
// Rendered as a sibling ABOVE the wallpaper layer but BELOW the transcript and
// composer (`z-0`, pointer-events none), and only on the empty landing — a live
// conversation is never obscured. Empty/whitespace text renders nothing.

import { useBackgroundStore } from '@/lib/backgrounds';
import { cn } from '@/lib/utils';

export function ChatWordmark() {
  const mode = useBackgroundStore((s) => s.prefs.mode);
  const text = useBackgroundStore((s) => s.prefs.text);
  const textFont = useBackgroundStore((s) => s.prefs.textFont);
  const textScale = useBackgroundStore((s) => s.prefs.textScale);
  const textOpacity = useBackgroundStore((s) => s.prefs.textOpacity);
  const textPositionY = useBackgroundStore((s) => s.prefs.textPositionY);
  const textAlign = useBackgroundStore((s) => s.prefs.textAlign);

  const word = text.trim();
  if (mode === 'none' || !word) return null;

  return (
    <div aria-hidden className="chat-wordmark">
      <span
        className={cn('chat-wordmark__text')}
        style={{
          fontFamily: textFont,
          fontSize: `${textScale}vw`,
          opacity: Math.min(1, Math.max(0, textOpacity / 100)),
          top: `${textPositionY}%`,
          textAlign,
        }}
      >
        {word}
      </span>
    </div>
  );
}
