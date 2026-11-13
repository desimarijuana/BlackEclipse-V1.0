'use client';

// ── VoiceInputButton — one dictation control for both composers ─────────────
// Idle: microphone. Recording: stop + elapsed timer. Transcribing: spinner.
// Errors surface in a small glass pill above the button (and in `title`) so a
// blocked permission or missing provider is never a silent no-op.
//
// Two exports:
//   * `VoiceInputButton` — self-contained; owns the dictation session.
//   * `VoiceInputButtonView` — the same control wired to a session the COMPOSER
//     owns (`useVoiceInput`), which is what lets the composer morph into the
//     voice field on the same state.

import { useEffect, useState } from 'react';
import { Loader2, Mic, Square } from '@/lib/icons';
import { cn } from '@/lib/utils';
import { useVoiceInput, type UseVoiceInput } from '@/hooks/use-voice-input';

export interface VoiceInputButtonProps {
  onTranscript: (text: string) => void;
  /** Called before the microphone/recognition starts (capture the caret here). */
  onStart?: () => void;
  /** Extra classes for the button (sizing differs between the two composers). */
  className?: string;
  iconSize?: number;
  align?: 'left' | 'right';
}

export interface VoiceInputButtonViewProps extends Omit<VoiceInputButtonProps, 'onTranscript'> {
  voice: UseVoiceInput;
  /** Called instead of the default start (the composer captures the caret). */
  onStart?: () => void;
}

function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, '0')}`;
}

/**
 * Microphone consent is asked HERE, in the composer, not by the host.
 *
 * WebView2 draws its own consent dialog in the top-left corner of the window —
 * it cannot be themed, moved or anchored to the control that asked. The shell
 * therefore suppresses the native media dialog and the app takes responsibility
 * for consent: first press shows this card, and the choice is remembered per
 * device.
 */
const CONSENT_KEY = 'be_voice_consent_v1';

function hasVoiceConsent(): boolean {
  try {
    return localStorage.getItem(CONSENT_KEY) === '1';
  } catch {
    return true; // storage unavailable → never block dictation behind the card
  }
}

/** The presentational control. Pure: every behaviour comes from `voice`. */
export function VoiceInputButtonView({
  voice,
  onStart,
  className,
  iconSize = 16,
  align = 'right',
}: VoiceInputButtonViewProps) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => setMounted(true), []);
  const [consentOpen, setConsentOpen] = useState(false);
  const recording = voice.state === 'recording';
  const busy = voice.state === 'starting' || voice.state === 'transcribing';

  const begin = () => {
    onStart?.();
    voice.start();
  };

  const allowAndBegin = () => {
    try {
      localStorage.setItem(CONSENT_KEY, '1');
    } catch {
      /* private mode — ask next time rather than fail */
    }
    setConsentOpen(false);
    begin();
  };

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
      {consentOpen && (
        <div
          role="dialog"
          aria-label="Microphone access"
          aria-modal="false"
          className={cn(
            'absolute bottom-full z-[130] mb-2 w-64 rounded-xl border border-white/12 glass-card p-3 text-[11px] leading-relaxed text-foreground shadow-lg',
            align === 'right' ? 'right-0' : 'left-0',
          )}
        >
          <p className="text-[12px] font-medium">Eclipse needs your microphone</p>
          <p className="mt-1 text-muted-foreground/80">
            Speak your prompt and it is transcribed once, then discarded. Nothing is saved.
          </p>
          <div className="mt-2.5 flex items-center justify-end gap-2">
            <button
              type="button"
              onClick={() => setConsentOpen(false)}
              className="rounded-full px-2.5 py-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            >
              Not now
            </button>
            <button
              type="button"
              onClick={allowAndBegin}
              className="rounded-full bg-primary px-3 py-1 font-medium text-primary-foreground transition-colors hover:bg-primary/90"
            >
              Allow
            </button>
          </div>
        </div>
      )}
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
            // Only ask for consent when an engine can actually run; otherwise
            // start() surfaces the honest "configure a provider" message.
            if (voice.available && !hasVoiceConsent()) {
              setConsentOpen(true);
              return;
            }
            begin();
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
          recording && 'w-auto px-1.5 text-rose-300 hover:text-rose-200',
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

/** Backwards-compatible, self-contained control (used where the host has no
 *  interest in the session state, e.g. the floating dock today). */
export function VoiceInputButton({ onTranscript, onStart, ...rest }: VoiceInputButtonProps) {
  const voice = useVoiceInput(onTranscript);
  return <VoiceInputButtonView voice={voice} onStart={onStart} {...rest} />;
}

export default VoiceInputButton;
