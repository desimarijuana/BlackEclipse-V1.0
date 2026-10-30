'use client';

// ── VoiceInputButton — one dictation control for both composers ─────────────
// Idle: microphone. Recording: stop + elapsed timer. Transcribing: spinner.
// Errors surface in a small glass pill above the button (and in `title`) so a
// blocked permission or missing provider is never a silent no-op.

import { useEffect, useState } from 'react';
import { Loader2, Mic, Square } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useVoiceInput } from '@/hooks/use-voice-input';

export interface VoiceInputButtonProps {
  onTranscript: (text: string) => void;
  /** Called before the microphone/recognition starts (capture the caret here). */
  onStart?: () => void;
  /** Extra classes for the button (sizing differs between the two composers). */
  className?: string;
  iconSize?: number;
  align?: 'left' | 'right';
}

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

export function VoiceInputButton({
  onTranscript,
  onStart,
  className,
  iconSize = 16,
  align = 'right',
}: VoiceInputButtonProps) {
  const voice = useVoiceInput(onTranscript);
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const recording = voice.state === 'recording';
  const busy = voice.state === 'starting' || voice.state === 'transcribing';

  const engineLabel =
    voice.engine === 'browser'
      ? 'browser dictation'
      : voice.engine === 'whisper'
        ? `${voice.config?.provider ?? 'Whisper'} Whisper`
        : voice.config === null
          ? 'checking transcription…'
          : 'no engine configured';

  // The server cannot know which engines exist, so keep the SSR title stable
  // and only add the engine detail after mount (avoids a hydration mismatch on
  // an attribute React will not patch).
  const title = !mounted
    ? 'Voice input'
    : recording
      ? `Stop and transcribe — ${formatElapsed(voice.elapsedMs)}`
      : voice.state === 'transcribing'
        ? 'Transcribing…'
        : voice.state === 'starting'
          ? 'Starting microphone…'
          : `Voice input · ${engineLabel}`;

  return (
    <span className="relative inline-flex shrink-0">
      {voice.error && (
        <span
          role="status"
          className={cn(
            'absolute bottom-full z-[130] mb-2 w-60 rounded-xl border border-amber-500/25 glass-card px-2.5 py-2 text-[10px] leading-relaxed text-amber-100 shadow-lg',
            align === 'right' ? 'right-0' : 'left-0',
          )}
        >
          {voice.error}
        </span>
      )}
      <button
        type="button"
        onClick={() => {
          if (recording) voice.stop();
          else if (voice.state === 'idle') {
            onStart?.();
            voice.start();
          }
        }}
        onContextMenu={(event) => {
          if (recording) {
            event.preventDefault();
            voice.cancel();
          }
        }}
        disabled={busy}
        title={title}
        aria-label={title}
        aria-pressed={recording}
        className={cn(
          'flex items-center justify-center rounded-full text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-70',
          recording && 'w-auto bg-rose-500/15 px-2 text-rose-300 hover:bg-rose-500/25 hover:text-rose-200',
          className,
        )}
      >
        {busy ? (
          <Loader2 size={iconSize} className="animate-spin" />
        ) : recording ? (
          <Square size={iconSize - 3} />
        ) : (
          <Mic size={iconSize} />
        )}
        {recording && (
          <span className="ml-1 font-mono text-[10px] tabular-nums">
            {formatElapsed(voice.elapsedMs)}
          </span>
        )}
      </button>
    </span>
  );
}

export default VoiceInputButton;
