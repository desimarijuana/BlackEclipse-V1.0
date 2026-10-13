// ── Mermaid repair (pure) ─────────────────────────────────────────────────────
//
// Models emit plausible Mermaid that Mermaid v12 rejects on small syntax slips:
// unquoted labels containing reserved characters (`( ) [ ] { } < > | / \ →`),
// HTML entities used as escapes (`&gt;`), and sequence statements wrapped across
// lines (a `Note over X:` continued on the next line). This module performs a
// small, conservative, side-effect-free repair so a diagram renders instead of
// degrading to a parse-error card.
//
// It is total (never throws) and never invents content: it only quotes, decodes
// and joins what is already present. When it is unsure it leaves the source
// untouched — a diagram that still fails to parse shows the existing honest
// "Diagram could not be rendered" card.

/** Characters that force a flowchart label to be quoted. */
const RESERVED_IN_LABEL = /[()[\]{}<>|/\\→←↑↓↔⇒]/;

const HTML_ENTITIES: Record<string, string> = {
  '&gt;': '>',
  '&lt;': '<',
  '&amp;': '&',
  '&quot;': '"',
  '&#39;': "'",
  '&apos;': "'",
};

function decodeEntities(text: string): string {
  // Single left-to-right pass; each occurrence is decoded once, so an escaped
  // `&amp;gt;` decodes to `&gt;` rather than being double-decoded.
  return text.replace(/&(?:gt|lt|amp|quot|#39|apos);/g, (m) => HTML_ENTITIES[m] ?? m);
}

/** Keywords whose presence at the start of a line means it is NOT a wrapped
 *  continuation of the previous sequence statement. */
const SEQUENCE_KEYWORDS = new Set([
  'participant', 'actor', 'note', 'loop', 'alt', 'else', 'opt', 'par', 'and',
  'end', 'activate', 'deactivate', 'autonumber', 'rect', 'box', 'critical',
  'break', 'link', 'links', 'over', 'left', 'right', 'title', 'create',
  'destroy', 'sequencediagram', 'acctitle', 'accdescription',
]);

/** Join sequence statements that were wrapped onto a following line. A wrapped
 *  fragment begins with a lowercase word and has no `:` or arrow of its own,
 *  while the line it continues does carry a `:` (a message or note). */
function repairSequenceLines(lines: string[]): string[] {
  const out: string[] = [];
  for (const line of lines) {
    const trimmed = line.trim();
    const prev = out.length > 0 ? out[out.length - 1] : '';
    const prevHasColon = prev.includes(':');
    const startsLower = /^[a-z]/.test(trimmed);
    const head = trimmed.split(/[\s:]/)[0].toLowerCase();
    const isKeyword = SEQUENCE_KEYWORDS.has(head);
    const looksLikeStatement = trimmed.includes(':') || trimmed.includes('-') || isKeyword;
    if (trimmed && startsLower && prevHasColon && !looksLikeStatement) {
      out[out.length - 1] = `${prev} ${trimmed}`;
      continue;
    }
    out.push(line);
  }
  return out;
}

/** Quote the inner text of a flowchart node when it holds reserved characters,
 *  leaving already-quoted, nested-shape and directive lines untouched. */
function quoteFlowchartLabels(line: string): string {
  const t = line.trimStart();
  if (
    t.startsWith('%%') ||
    t.startsWith('classDef') ||
    t.startsWith('class ') ||
    t.startsWith('style ') ||
    t.startsWith('linkStyle') ||
    t.startsWith('click ') ||
    t.startsWith('direction')
  ) {
    return line;
  }

  let out = line;
  out = out.replace(/([A-Za-z0-9_.\-]+)\[([^\]"\n]*?)\]/g, (match, id: string, body: string) =>
    needsQuote(body) ? `${id}["${body}"]` : match,
  );
  out = out.replace(/([A-Za-z0-9_.\-]+)\{([^}"\n]*?)\}/g, (match, id: string, body: string) =>
    needsQuote(body) ? `${id}{"${body}"}` : match,
  );
  out = out.replace(/([A-Za-z0-9_.\-]+)\(([^)"\n]*?)\)/g, (match, id: string, body: string) =>
    needsQuote(body) ? `${id}("${body}")` : match,
  );
  return out;
}

function needsQuote(body: string): boolean {
  // Empty, or a nested shape like `[[text]]` / `(())` — leave the shape alone.
  if (!body.trim()) return false;
  if (/^[([{]/.test(body.trim())) return false;
  return RESERVED_IN_LABEL.test(body);
}

/**
 * Repair a Mermaid definition so a small syntax slip does not cost the diagram.
 * Returns the original source unchanged when nothing is recognised.
 */
export function repairMermaid(source: string): string {
  if (!source) return source;
  let text = source.replace(/\r\n?/g, '\n');
  text = decodeEntities(text);

  const lines = text.split('\n');
  const header = lines.find((l) => l.trim())?.trim().toLowerCase() ?? '';
  const isSequence = header.startsWith('sequencediagram');
  const isFlow = /^(flowchart|graph)\b/.test(header);

  let out = isSequence ? repairSequenceLines(lines) : lines;
  if (isFlow) out = out.map(quoteFlowchartLabels);
  return out.join('\n');
}
