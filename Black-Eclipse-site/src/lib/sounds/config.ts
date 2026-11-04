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
//   taskdone     — a background task / agent run finished while away

export type SoundName =
  | 'click'
  | 'tick'
  | 'toggle'
  | 'success'
  | 'error'
  | 'notification'
  | 'message'
  | 'taskdone';

export const SOUND_NAMES: readonly SoundName[] = [
  'click', 'tick', 'toggle', 'success', 'error', 'notification', 'message', 'taskdone',
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
  /**
   * Minimum effective master volume (0–1). Critical attention cues stay
   * audible even when the global volume slider sits low; the per-cue mute,
   * per-cue volume and the master on/off switch still apply.
   */
  gainFloor?: number;
  /**
   * Event-notification cue (AI result, alert, background-task completion).
   * These play independently of the "UI sounds" master switch and of the
   * essential-only mode, because they announce something happening outside
   * the current view — the whole point of a notification. The per-cue mute
   * is the explicit opt-out and is what keeps them off for anyone who does
   * not want them.
   *
   * Direct-interaction cues (click/tick/toggle) remain opt-in: `enabled`
   * defaults to false, so nothing "haptic" fires until the user turns it on.
   */
  notification?: boolean;
}

export const SOUND_DEFINITIONS: Record<SoundName, SoundDefinition> = {
  click: { label: 'Click', hint: 'Buttons and actions', volume: 1, throttleMs: 40, essential: true },
  tick: { label: 'Tick', hint: 'Tabs, navigation, selection', volume: 0.85, throttleMs: 30, essential: true },
  toggle: { label: 'Toggle', hint: 'Switches and checkboxes', volume: 0.9, throttleMs: 60, essential: true },
  success: { label: 'Success', hint: 'Completed actions', volume: 1, throttleMs: 120, essential: false },
  error: { label: 'Error', hint: 'Failed actions', volume: 1, throttleMs: 120, essential: false },
  notification: { label: 'Alert', hint: 'A price or news alert fired, or an approval is waiting', volume: 1, throttleMs: 400, essential: false, notification: true, gainFloor: 0.5 },
  message: { label: 'AI result', hint: 'An Eclipse reply or AI run has finished', volume: 1, throttleMs: 300, essential: false, notification: true, gainFloor: 0.5 },
  // The completion alarm for a background task or automation. It is an event
  // notification (not interaction feedback), so it stays audible while UI
  // sounds are off — but it is not "always audible at full blast": it uses the
  // same quiet gain floor as the other notification cues, and muting it in
  // Settings › Sound is the explicit opt-out.
  taskdone: { label: 'Task done', hint: 'A background task or automation has finished', volume: 1, throttleMs: 2500, essential: true, notification: true, gainFloor: 0.5 },
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

// ── AI-result message voices ────────────────────────────────────────────────
// The message cue announces an Eclipse reply, so it is deliberately independent
// of the interaction voice pack: a pack's tick can be crisp while the reply
// sound stays a soft chime. Assets live under `public/sounds/message/` and are
// generated by `scripts/generate-message-cues.py`.

export type MessageVariant = 'chime' | 'marimba' | 'glass' | 'blip';

export interface MessageVariantOption {
  id: MessageVariant;
  label: string;
  description: string;
}

export const MESSAGE_VARIANTS: readonly MessageVariantOption[] = [
  { id: 'chime', label: 'Soft chime', description: 'Two-note rising fifth — warm and unobtrusive (recommended)' },
  { id: 'marimba', label: 'Marimba', description: 'Wooden mallet two-note — organic, low attack' },
  { id: 'glass', label: 'Glass', description: 'Bright bell with a gentle shimmer — more noticeable' },
  { id: 'blip', label: 'Minimal blip', description: 'Very short low blip — the quietest option' },
] as const;

export const DEFAULT_MESSAGE_VARIANT: MessageVariant = 'chime';

export function isMessageVariant(value: unknown): value is MessageVariant {
  return typeof value === 'string' && MESSAGE_VARIANTS.some((v) => v.id === value);
}

/** Resolve the shared AI-result cue asset (not tied to the interaction pack). */
export function messageVariantSrc(variant: MessageVariant): string {
  return `/sounds/message/${variant}.wav`;
}

/** Resolve the bundled asset path for a cue in a given pack. */
export function packSoundSrc(pack: SoundPackId, name: SoundName): string {
  return `/sounds/${pack}/${name}.wav`;
}

export function isSoundName(value: unknown): value is SoundName {
  return typeof value === 'string' && (SOUND_NAMES as readonly string[]).includes(value);
}
