// ── Speech text projection ──────────────────────────────────────────────────
// Model replies are Markdown. Read literally, they sound broken — "asterisk
// asterisk revenue asterisk asterisk", pasted code, pipe-delimited tables and
// raw URLs. This module is the ONE place that turns a reply into prose worth
// hearing. It is pure and dependency-free so it can be unit-tested in the Node
// test environment (no `window`), and so the projection cannot drift between
// the chat button, the response header and the settings preview.

const HTML_ENTITIES: Record<string, string> = {
  amp: '&',
  lt: '<',
  gt: '>',
  quot: '"',
  apos: "'",
  nbsp: ' ',
  mdash: '—',
  ndash: '–',
  hellip: '…',
  rsquo: '’',
  lsquo: '‘',
  rdquo: '”',
  ldquo: '“',
  copy: '©',
  reg: '®',
  trade: '™',
  deg: '°',
};

function decodeEntities(input: string): string {
  return input.replace(/&(#x?[0-9a-fA-F]+|[a-zA-Z]+);/g, (match, code: string) => {
    try {
      if (code.startsWith('#x') || code.startsWith('#X')) {
        return String.fromCodePoint(Number.parseInt(code.slice(2), 16));
      }
      if (code.startsWith('#')) {
        return String.fromCodePoint(Number.parseInt(code.slice(1), 10));
      }
      return HTML_ENTITIES[code.toLowerCase()] ?? match;
    } catch {
      return match;
    }
  });
}

/** A closed fenced block — code, JSON, Mermaid, app HTML, response envelopes. */
const CLOSED_FENCE = /^ {0,3}(`{3,}|~{3,})[^\n]*\n[\s\S]*?^ {0,3}\1[^\n]*$/gm;

/** An opening fence with no close (a streaming turn): drop the remainder. */
const OPEN_FENCE_TO_END = /^ {0,3}(?:`{3,}|~{3,})[^\n]*$[\s\S]*$/m;

const HORIZONTAL_RULE = /^([-*_])(?:\s*\1){2,}$/;
const TABLE_SEPARATOR = /^\|?\s*:?-{2,}:?\s*(?:\|\s*:?-{2,}:?\s*)*\|?$/;

/**
 * Convert Markdown to speakable prose.
 *
 * Deliberate omissions: fenced code and structured-response JSON are removed
 * entirely (reading JSON aloud is worse than silence); URLs are dropped but
 * their labels kept; tables are read as comma-separated rows. Returns `''`
 * when nothing worth hearing remains, so callers can hide the control rather
 * than play a misleading "reply is empty" sentence.
 */
export function toSpeakableText(markdown: string): string {
  if (!markdown) return '';

  let text = markdown.replace(/\r\n?/g, '\n');
  text = text.replace(CLOSED_FENCE, '\n');
  text = text.replace(OPEN_FENCE_TO_END, '\n');

  text = text.replace(/!\[([^\]]*)\]\([^)]*\)/g, '$1');
  text = text.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1');
  text = text.replace(/\[([^\]]+)\]\[[^\]]*\]/g, '$1');
  text = decodeEntities(text);
  text = text.replace(/<((?:https?|mailto):[^>\s]+)>/gi, ' ');
  text = text.replace(/<\/?[a-zA-Z][^>]*>/g, ' ');

  const out: string[] = [];
  for (const raw of text.split('\n')) {
    let line = raw.replace(/\u00a0/g, ' ').trim();
    if (!line) {
      out.push('');
      continue;
    }
    if (HORIZONTAL_RULE.test(line)) continue;
    if (TABLE_SEPARATOR.test(line)) continue;

    // Table row -> "Revenue, 1.2B, up 8%." (never pipes aloud).
    if (line.startsWith('|') || (line.includes('|') && line.endsWith('|'))) {
      const cells = line
        .replace(/^\|/, '')
        .replace(/\|$/, '')
        .split('|')
        .map((cell) => cell.trim())
        .filter(Boolean);
      if (cells.length > 0) out.push(`${cells.join(', ')}.`);
      continue;
    }

    line = line.replace(/^>\s?/, '');
    line = line.replace(/^#{1,6}\s+/, '');
    line = line.replace(/^[-*+]\s+/, '');
    line = line.replace(/^\d+[.)]\s+/, '');
    line = line.replace(/^\[[ xX]\]\s*/, '');
    line = line.replace(/\[\^[^\]]*\]/g, ' ');
    line = line.replace(/\[\d+\]/g, ' ');
    line = line.replace(/(\*\*|__|~~|\*|_|`)/g, '');
    line = line.replace(/\\([\\`*_{}[\]()#+.!|-])/g, '$1');
    line = line.replace(/[ \t]{2,}/g, ' ').trim();
    if (line) out.push(line);
  }

  let prose = out
    .join('\n')
    .replace(/\n{2,}/g, '\n')
    .replace(/[ \t]+/g, ' ')
    .trim();

  // Headings, list items and table rows often end without punctuation. Add a
  // stop between blocks so the voice pauses instead of running them together.
  prose = prose.replace(/([^\n.!?…:;])\n(?=[^\n])/g, '$1. ');
  prose = prose.replace(/\n+/g, ' ').replace(/\s{2,}/g, ' ').trim();

  // Guarantee a natural ending; some voices trail off on a bare word.
  if (prose && !/[.!?…:;)"'”’]$/.test(prose)) prose += '.';
  return prose;
}

/**
 * Break prose into utterance-sized chunks.
 *
 * Chrome truncates long utterances (and some voices stall around 15s), so the
 * engine speaks short pieces in sequence instead of one huge string. Splits on
 * sentence boundaries first, then merges short sentences up to `maxChars`, then
 * breaks any still-long sentence at a comma/semicolon/space.
 */
export function splitForSpeech(text: string, maxChars = 220): string[] {
  const limit = Math.max(40, Math.floor(maxChars) || 220);
  const flat = text.replace(/\s+/g, ' ').trim();
  if (!flat) return [];

  const sentences = flat.split(/(?<=[.!?…])\s+/).filter(Boolean);
  const chunks: string[] = [];
  let current = '';

  const push = () => {
    if (current.trim()) chunks.push(current.trim());
    current = '';
  };

  for (const sentence of sentences) {
    if (sentence.length > limit) {
      push();
      chunks.push(...breakLong(sentence, limit));
      continue;
    }
    if (!current) {
      current = sentence;
    } else if (current.length + 1 + sentence.length <= limit) {
      current += ' ' + sentence;
    } else {
      push();
      current = sentence;
    }
  }
  push();
  return chunks;
}

function breakLong(sentence: string, limit: number): string[] {
  const parts: string[] = [];
  let rest = sentence.trim();

  while (rest.length > limit) {
    const head = rest.slice(0, limit);
    let cut = Math.max(
      head.lastIndexOf(', '),
      head.lastIndexOf('; '),
      head.lastIndexOf(' — '),
    );
    if (cut < limit * 0.45) cut = head.lastIndexOf(' ');
    if (cut < limit * 0.45) cut = limit;

    const piece = rest.slice(0, cut).trim();
    if (piece) parts.push(piece);
    rest = rest.slice(cut).trim();
  }
  if (rest) parts.push(rest);
  return parts;
}
