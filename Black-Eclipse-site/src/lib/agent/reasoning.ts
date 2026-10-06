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
}

/**
 * The picker stops, in order. Auto is first so "no override" is the visible
 * default; the runtime's task profiles keep choosing per task unless the
 * operator pins one.
 */
export const REASONING_OPTIONS: readonly ReasoningOption[] = [
  { value: undefined, label: "Auto", hint: "Let Eclipse pick per task — the default." },
  { value: "low", label: "Minimal", hint: "Fastest, lightest — best for quick lookups." },
  { value: "medium", label: "Standard", hint: "A balanced default for everyday questions." },
  { value: "high", label: "High", hint: "Deeper reasoning for analysis and research." },
  { value: "very_high", label: "Ultra", hint: "Maximum depth — slowest and most costly." },
];

export function isReasoningLevel(value: unknown): value is ReasoningLevel {
  return typeof value === "string" && (REASONING_LEVELS as readonly string[]).includes(value);
}

/** The stored value for an option (undefined = Auto, so it never persists). */
export function levelForOption(option: ReasoningOption): ReasoningLevel | undefined {
  return option.value;
}
