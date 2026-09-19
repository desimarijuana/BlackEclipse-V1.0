// ── UI sound definitions ────────────────────────────────────────────────────
// The canonical catalogue of interface sounds. Each entry points at a local
// asset under `public/sounds/` and declares its relative gain and throttle.
// `volume` is a per-sound multiplier (0–1) applied on top of the user's master
// volume so individual cues stay balanced without per-callsite tuning.

export type SoundName =
  | 'click'
  | 'tick'
  | 'toggle'
  | 'success'
  | 'error'
  | 'notification';

export interface SoundDefinition {
  /** Public path to the audio asset. */
  src: string;
  /** Per-sound gain multiplier (0–1), applied over the master volume. */
  volume: number;
  /** Minimum milliseconds between two plays of this same cue. */
  throttleMs: number;
}

export const SOUND_DEFINITIONS: Record<SoundName, SoundDefinition> = {
  click: { src: '/sounds/click.wav', volume: 1, throttleMs: 40 },
  tick: { src: '/sounds/tick.wav', volume: 0.85, throttleMs: 30 },
  toggle: { src: '/sounds/toggle.wav', volume: 0.9, throttleMs: 60 },
  success: { src: '/sounds/success.wav', volume: 1, throttleMs: 120 },
  error: { src: '/sounds/error.wav', volume: 1, throttleMs: 120 },
  notification: { src: '/sounds/notification.wav', volume: 1, throttleMs: 400 },
};

export const SOUND_NAMES = Object.keys(SOUND_DEFINITIONS) as SoundName[];

export function isSoundName(value: unknown): value is SoundName {
  return typeof value === 'string' && value in SOUND_DEFINITIONS;
}
