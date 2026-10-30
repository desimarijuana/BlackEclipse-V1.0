// ── Transcript insertion ────────────────────────────────────────────────────
// Pure, cursor-aware insertion used by both composers. A dictation must never
// replace text the operator already typed: it lands at the selection (or the
// caret), with a single separating space and the caret moved after it.

export interface TextSelection {
  start: number;
  end: number;
}

export interface InsertResult {
  value: string;
  caret: number;
}

/** Collapse dictation whitespace; keep the words. */
export function normalizeTranscript(text: string): string {
  return text.replace(/\s+/g, ' ').trim();
}

/**
 * Insert `transcript` into `value` at `selection`.
 *
 * - an empty transcript returns the value untouched;
 * - a selection is replaced (a normal text-editing expectation);
 * - spaces are added only where they are needed;
 * - `caret` is the position after the inserted text, ready for the caller to
 *   restore focus without scrolling to the end.
 */
export function insertTranscript(
  value: string,
  transcript: string,
  selection?: TextSelection,
): InsertResult {
  const text = normalizeTranscript(transcript);
  if (!text) return { value, caret: selection?.end ?? value.length };

  const start = Math.min(Math.max(selection?.start ?? value.length, 0), value.length);
  const end = Math.min(Math.max(selection?.end ?? start, start), value.length);

  const before = value.slice(0, start);
  const after = value.slice(end);

  const leading = before.length > 0 && !/\s$/.test(before) ? ' ' : '';
  const trailing = after.length > 0 && !/^[\s.,!?;:)\]}]/.test(after) ? ' ' : '';

  const inserted = `${leading}${text}${trailing}`;
  return {
    value: `${before}${inserted}${after}`,
    caret: before.length + inserted.length,
  };
}
