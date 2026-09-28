// ── UI sound definitions ────────────────────────────────────────────────────
// The canonical catalogue of interface cues and the selectable voice packs.
// Assets live under `public/sounds/<pack>/<cue>.wav`. The user's active pack,
// per-cue volume, mutes and custom uploads live in `./store.ts`.
//
// Cue intent:
//   click        — buttons / actions
//   tick         — tabs, navigation, selection
//   toggle       — switches / checkboxes
//   success      — completed actions
//   error        — failed actions
//   notification — important system events / alerts
//   message      — an incoming chat reply has finished

export type SoundName =
  | 'click'
  | 'tick'
  | 'toggle'
  | 'success'
  | 'error'
  | 'notification'
  | 'message';

export const SOUND_NAMES: readonly SoundName[] = [
  'click', 'tick', 'toggle', 'success', 'error', 'notification', 'message',
] as const;

export interface SoundDefinition {
  /** Human label for the settings UI. */
  label: string;
  /** What triggers this cue. */
  hint: string;
  /** Default gain multiplier (0–1) applied over the master volume. */
  volume: number;
  /** Minimum milliseconds between two plays of this same cue. */
  throttleMs: number;
  /**
   * Direct-interaction cue. Played in every mode; non-essential cues
   * (confirmations, alerts) are muted in the `essential` sound mode.
   */
  essential: boolean;
}

export const SOUND_DEFINITIONS: Record<SoundName, SoundDefinition> = {
  click: { label: 'Click', hint: 'Buttons and actions', volume: 1, throttleMs: 40, essential: true },
  tick: { label: 'Tick', hint: 'Tabs, navigation, selection', volume: 0.85, throttleMs: 30, essential: true },
  toggle: { label: 'Toggle', hint: 'Switches and checkboxes', volume: 0.9, throttleMs: 60, essential: true },
  success: { label: 'Success', hint: 'Completed actions', volume: 1, throttleMs: 120, essential: false },
  error: { label: 'Error', hint: 'Failed actions', volume: 1, throttleMs: 120, essential: false },
  notification: { label: 'Notification', hint: 'Alerts and system events', volume: 1, throttleMs: 400, essential: false },
  message: { label: 'Message', hint: 'An incoming chat reply has finished', volume: 1, throttleMs: 300, essential: false },
};

// ── Voice packs ─────────────────────────────────────────────────────────────

export type SoundPackId =
  | 'eclipse' | 'mechanical' | 'soft' | 'glass' | 'retro'
  | 'marimba' | 'typewriter' | 'digital' | 'crisp';

export interface SoundPack {
  id: SoundPackId;
  label: string;
  description: string;
}

export const SOUND_PACKS: readonly SoundPack[] = [
  { id: 'eclipse', label: 'Eclipse', description: 'Organic wooden ticks — the default terminal voice' },
  { id: 'mechanical', label: 'Mechanical', description: 'Crisp keyboard-switch clicks' },
  { id: 'crisp', label: 'Crisp', description: 'Ultra-short dry ticks — the quietest voice' },
  { id: 'typewriter', label: 'Typewriter', description: 'Heavy key thocks with a bright return' },
  { id: 'soft', label: 'Soft', description: 'Mellow, low-key taps for quiet workspaces' },
  { id: 'marimba', label: 'Marimba', description: 'Warm wooden mallet notes' },
  { id: 'glass', label: 'Glass', description: 'Bright crystalline chimes' },
  { id: 'digital', label: 'Digital', description: 'Clean, minimal electronic blips' },
  { id: 'retro', label: 'Retro', description: 'Chiptune blips for a classic feel' },
] as const;

export const DEFAULT_PACK: SoundPackId = 'eclipse';

export function isSoundPackId(value: unknown): value is SoundPackId {
  return typeof value === 'string' && SOUND_PACKS.some((p) => p.id === value);
}

/** Resolve the bundled asset path for a cue in a given pack. */
export function packSoundSrc(pack: SoundPackId, name: SoundName): string {
  return `/sounds/${pack}/${name}.wav`;
}

export function isSoundName(value: unknown): value is SoundName {
  return typeof value === 'string' && (SOUND_NAMES as readonly string[]).includes(value);
}
