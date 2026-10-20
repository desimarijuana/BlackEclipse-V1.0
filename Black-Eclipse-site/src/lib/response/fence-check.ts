// Lightweight fence detection. Deliberately does NOT import `contract.ts`:
// that module pulls the full Zod response schema (and its block registry) into
// any caller. Chat history and the markdown renderer only need to know whether a
// turn contains an `eclipse-response` fence; the heavy decoder loads later, with
// the response renderer itself.

export const RESPONSE_FENCE_LANGUAGE = 'eclipse-response';

const OPEN_FENCE_RE = /^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)\s*$/;

/** True when the markdown contains an opening ` ```eclipse-response ` fence. */
export function hasResponseFence(markdown: string): boolean {
  for (const line of markdown.replace(/\r\n?/g, '\n').split('\n')) {
    const open = line.match(OPEN_FENCE_RE);
    if (open && open[2] === RESPONSE_FENCE_LANGUAGE) return true;
  }
  return false;
}
