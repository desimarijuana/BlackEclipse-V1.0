// ── Reasoning effort (a.k.a. model "variant") ────────────────────────────────
// One vocabulary shared by the Settings UI, the settings vault and the run
// front door, so the stored value, the picker label and the runtime override can
// never drift. The runtime's own scale is `none/low/medium/high/very_high/max`
// (see `python/harness/model_runtime/catalog.py` `REASONING_LEVELS`); the UI
// presents the four useful stops as friendlier words and maps them 1:1.
//
// "Auto" (undefined) sends no override, so the runtime's task profile picks the
// effort — exactly as it did before this control existed.

/** The runtime reasoning levels this control can set. `none`/`max` are omitted:
 *  a chat/agent run never wants zero reasoning, and `max` is a task-profile
 *  decision, not a per-run knob. */
export const REASONING_LEVELS = ["low", "medium", "high", "very_high"] as const;

export type ReasoningLevel = (typeof REASONING_LEVELS)[number];

/** A persisted effort, or `undefined`/`null` for Auto (no override). */
export type ReasoningEffort = ReasoningLevel;

export interface ReasoningOption {
  /** Persisted value, or `undefined` for Auto. */
  value: ReasoningLevel | undefined;
  /** Short label shown in the picker. */
  label: string;
  /** One-line explanation shown under the control. */
  hint: string;
  /**
   * The caption the composer slider shows UNDER the track. Deliberately not
   * `hint`: "Recommended" is a judgement, the hint is the mechanism, and the
   * two surfaces may word them differently.
   */
  caption: string;
  /**
   * Visual "skin" for the composer slider. `muted` = a restrained track (Auto,
   * and the low/medium stops), `violet` = the deeper mid/high stops, `aurora` =
   * the top stop, rendered with a bright glow so "Ultra" visibly reads as the
   * extreme end of the scale.
   */
  skin: "muted" | "violet" | "aurora";
}

/**
 * The picker stops, in order. Auto is first so "no override" is the visible
 * default; the runtime's task profiles keep choosing per task unless the
 * operator pins one.
 */
export const REASONING_OPTIONS: readonly ReasoningOption[] = [
  { value: undefined, label: "Auto", hint: "Let Eclipse pick per task — the default.", caption: "Recommended", skin: "muted" },
  { value: "low", label: "Minimal", hint: "Fastest, lightest — best for quick lookups.", caption: "Fastest — lightest thinking.", skin: "muted" },
  { value: "medium", label: "Standard", hint: "A balanced default for everyday questions.", caption: "Recommended — a balanced default.", skin: "violet" },
  { value: "high", label: "High", hint: "Deeper reasoning for analysis and research.", caption: "Deeper — for analysis and research.", skin: "violet" },
  { value: "very_high", label: "Ultra", hint: "Maximum depth — slowest and most costly.", caption: "Maximum depth — slowest, most costly.", skin: "aurora" },
];

export function isReasoningLevel(value: unknown): value is ReasoningLevel {
  return typeof value === "string" && (REASONING_LEVELS as readonly string[]).includes(value);
}

/** The stored value for an option (undefined = Auto, so it never persists). */
export function levelForOption(option: ReasoningOption): ReasoningLevel | undefined {
  return option.value;
}

/** The composer slider's stops, in order (Auto first). Kept as an alias so the
 *  control and the Settings picker can never disagree about the vocabulary. */
export const EFFORT_STOPS: readonly ReasoningOption[] = REASONING_OPTIONS;

/** The default slider index (Auto) — where the thumb rests with no override. */
export const DEFAULT_EFFORT_INDEX = 0;

/** Index of a value within `EFFORT_STOPS` (0 when Auto / unknown). */
export function effortIndex(value: ReasoningLevel | undefined | null): number {
  const idx = EFFORT_STOPS.findIndex((o) => o.value === (value ?? undefined));
  return idx >= 0 ? idx : DEFAULT_EFFORT_INDEX;
}

/** The option at a slider index, clamped to the valid range. */
export function effortAt(index: number): ReasoningOption {
  const clamped = Math.max(0, Math.min(EFFORT_STOPS.length - 1, Math.round(index)));
  return EFFORT_STOPS[clamped];
}

