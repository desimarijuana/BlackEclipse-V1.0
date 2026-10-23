// ── A long paste becomes an attachment, not a composer full of text ─────────
//
// Typing a sentence into the composer is the normal case; pasting a report, a
// filing, or a wall of logs into it is not. A multi-thousand-character blob in
// the textarea makes the composer unusable (it grows four lines then scrolls),
// and a message that large is really a DOCUMENT the user is handing over — the
// same thing as dragging the file in.
//
// So a paste above the threshold is intercepted and attached: it lands in the
// conversation's session folder as a context document and shows as a chip, the
// way ChatGPT shows "Pasted text". Nothing about the content changes: the
// document pipeline extracts it and injects it into the run.
//
// Pure (no DOM, no fs) so the rule and the naming are testable.

import type { Message } from "@/types/chat";

/** Characters above which a paste is treated as a document, not a message. */
export const PASTE_AS_ATTACHMENT_CHARS = 4_000;

export const PASTED_TEXT_PREFIX = "pasted-text";

/**
 * True when a pasted string is too big to belong in the composer.
 *
 * Measured on the trimmed text so a paste with trailing blank lines is not
 * treated differently from the same text without them.
 */
export function isLongPaste(text: string): boolean {
  return text.trim().length > PASTE_AS_ATTACHMENT_CHARS;
}

/**
 * A free attachment name for pasted text: `pasted-text.txt`, then
 * `pasted-text-2.txt`, … A name already taken by another attachment is never
 * reused (chips and session files are keyed by name).
 */
export function pastedTextName(taken: Iterable<string>): string {
  const used = new Set(taken);
  let name = `${PASTED_TEXT_PREFIX}.txt`;
  for (let n = 2; used.has(name); n += 1) name = `${PASTED_TEXT_PREFIX}-${n}.txt`;
  return name;
}

/**
 * Claim every paste not yet shown on a user turn. Claiming does NOT remove the
 * document — the run keeps reading it as context — it only marks which pastes
 * belong to the turn that is about to be sent.
 */
export function claimPastes(
  pastes: ReadonlyMap<string, string>,
  claimed: Set<string>,
): Array<{ name: string; text: string }> {
  const out: Array<{ name: string; text: string }> = [];
  for (const [name, text] of pastes) {
    if (claimed.has(name)) continue;
    claimed.add(name);
    out.push({ name, text });
  }
  return out;
}

/**
 * The user turn for a send. A paste-only send gets a readable prompt (the
 * document itself stays context); the claimed pastes become compact cards.
 * Returns null when there is nothing to send.
 */
export function buildUserTurn(
  typed: string,
  pasted: ReadonlyArray<{ name: string; chars: number; preview: string }>,
  hasAttachment: boolean,
): Message | null {
  const content = typed.trim() || (pasted.length || hasAttachment ? "Read the attached document." : "");
  if (!content) return null;
  return {
    id: Date.now().toString(),
    role: "user",
    content,
    attachments: pasted.length
      ? pasted.map((p) => ({ name: p.name, chars: p.chars, preview: p.preview, pasted: true }))
      : undefined,
  };
}
