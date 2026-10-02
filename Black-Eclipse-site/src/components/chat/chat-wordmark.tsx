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

import { isWordmarkVisible, useBackgroundStore } from '@/lib/backgrounds';
import { cn } from '@/lib/utils';

export function ChatWordmark() {
  const prefs = useBackgroundStore((s) => s.prefs);
  const {
    text, textFont, textColor, textWeight, textLetterSpacing, textLineHeight,
    textWidth, textItalic, textUppercase, textScale, textOpacity, textPositionY, textAlign,
  } = prefs;

  if (!isWordmarkVisible(prefs)) return null;

  return (
    <div aria-hidden className="chat-wordmark">
      <span
        className={cn('chat-wordmark__text')}
        style={{
          fontFamily: textFont,
          fontSize: `${textScale}vw`,
          fontWeight: textWeight,
          letterSpacing: `${textLetterSpacing}em`,
          lineHeight: textLineHeight,
          fontStretch: `${textWidth}%`,
          fontStyle: textItalic ? 'italic' : 'normal',
          textTransform: textUppercase ? 'uppercase' : 'none',
          opacity: Math.min(1, Math.max(0, textOpacity / 100)),
          color: textColor.trim() || undefined,
          top: `${textPositionY}%`,
          textAlign,
        }}
      >
        {text.trim()}
      </span>
    </div>
  );
}
