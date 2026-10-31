// ── Run input ───────────────────────────────────────────────────────────────
// A manual run (and a webhook call) may carry one JSON value that the trigger
// emits as Start. It is bounded and validated on BOTH sides of the wire: the
// editor parses the text before sending, the route re-checks the parsed value.
// Run input is a property of ONE run — it is never written back into the
// workflow, so a saved graph can never contain a fabricated market value.

/** Hard cap for a run payload (64 KiB of UTF-8). */
export const MAX_RUN_INPUT_BYTES = 64 * 1024;

export type RunInputResult =
  | { ok: true; value: unknown }
  | { ok: false; error: string };

const encoder = new TextEncoder();

/** Validate an already-parsed JSON value and enforce the shared size cap.
 *  `label` is the word used in the error ("Run input", "config", "inputs"). */
export function validateBoundedJson(value: unknown, label = 'Run input'): RunInputResult {
  if (value === undefined) return { ok: true, value: undefined };
  let serialized: string;
  try {
    serialized = JSON.stringify(value) ?? '';
  } catch {
    return { ok: false, error: `${label} is not JSON-serializable.` };
  }
  const bytes = encoder.encode(serialized).length;
  if (bytes > MAX_RUN_INPUT_BYTES) {
    return { ok: false, error: `${label} must be ${MAX_RUN_INPUT_BYTES} bytes or fewer (got ${bytes}).` };
  }
  return { ok: true, value };
}

/** Validate an already-parsed run input (a route body, a webhook body, or the
 *  editor's parsed text). `undefined` means "no input" and is valid. */
export function validateRunInput(value: unknown): RunInputResult {
  return validateBoundedJson(value, 'Run input');
}

/** Parse the editor's textarea. Empty text is "no input", not an error. */
export function parseRunInputText(text: string): RunInputResult {
  const trimmed = text.trim();
  if (!trimmed) return { ok: true, value: undefined };
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return { ok: false, error: 'Run input must be valid JSON.' };
  }
  return validateRunInput(parsed);
}

/** A compact one-line label for the UI ("custom" vs "configured"). */
export function describeRunInput(value: unknown): string {
  if (value === undefined) return 'configured payload';
  const serialized = JSON.stringify(value) ?? '';
  return serialized.length > 60 ? `${serialized.slice(0, 60)}…` : serialized;
}
