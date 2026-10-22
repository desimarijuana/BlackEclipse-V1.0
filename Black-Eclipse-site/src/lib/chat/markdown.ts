// Minimal Markdown parser for assistant chat output.
//
// The Eclipse Agent (and every chat model) answers in Markdown, but the chat
// transcript used to render `msg.content` as a raw string, so `**bold**`,
// `### Heading`, lists and fenced code showed up literally. This module turns
// that subset of Markdown into a small typed AST so the view layer
// (`components/chat/markdown.tsx`) can render real elements.
//
// It is deliberately NOT a full CommonMark implementation: no new dependency,
// small bundle, and it degrades gracefully on partial/streaming input (an
// unclosed fence or trailing `**` is just text). Supported: headings (ATX),
// fenced + indented code, blockquotes, ordered/unordered lists, horizontal
// rules, paragraphs, LaTeX mathematics (`$...$`, `$$...$$`, `\(...\)`,
// `\[...\]`), and inline bold / italic / strikethrough / inline code / links,
// plus GFM pipe tables (with alignment).

export type InlineNode =
  | { type: 'text'; value: string }
  | { type: 'strong'; children: InlineNode[] }
  | { type: 'em'; children: InlineNode[] }
  | { type: 'del'; children: InlineNode[] }
  | { type: 'code'; value: string }
  | { type: 'link'; href: string; children: InlineNode[] }
  /** A formula: `$x^2$` inline, `$$...$$` as a block. */
  | { type: 'math'; value: string; display: boolean };

export type TableAlign = 'left' | 'center' | 'right' | null;

export type BlockNode =
  | { type: 'paragraph'; children: InlineNode[] }
  | { type: 'math'; value: string }
  | { type: 'heading'; level: 1 | 2 | 3 | 4 | 5 | 6; children: InlineNode[] }
  | { type: 'code'; language: string | null; value: string }
  | { type: 'blockquote'; children: BlockNode[] }
  | { type: 'list'; ordered: boolean; items: InlineNode[][] }
  | { type: 'table'; align: TableAlign[]; header: InlineNode[][]; rows: InlineNode[][][] }
  | { type: 'hr' };

type InlineMatch =
  | { kind: 'escape'; end: number; char: string }
  | { kind: 'math'; end: number; value: string; display: boolean }
  | { kind: 'code'; end: number; value: string }
  | { kind: 'del'; end: number; children: InlineNode[] }
  | { kind: 'emphasis'; end: number; strong: boolean; children: InlineNode[] }
  | { kind: 'link'; end: number; href: string; children: InlineNode[] };

const FENCE_RE = /^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)\s*$/;
const FENCE_CLOSE_RE = /^ {0,3}(?:`{3,}|~{3,})\s*$/;
const HEADING_RE = /^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const HR_RE = /^ {0,3}([-*_])(?:[ \t]*\1){2,}[ \t]*$/;
const UL_RE = /^ {0,3}[-*+][ \t]+(.*)$/;
const OL_RE = /^ {0,3}\d{1,9}[.)][ \t]+(.*)$/;
const BLOCKQUOTE_RE = /^ {0,3}>[ \t]?(.*)$/;
const TABLE_DELIM_CELL_RE = /^:?-{1,}:?$/;
// Display mathematics opens a block even when the previous line was prose with
// no blank line between them (`**Return definition**\n$$r_t = ...$$`).
const DISPLAY_MATH_START_RE = /^ {0,3}(?:\$\$|\\\[)/;

function isTableDelimiterRow(line: string): boolean {
  const cells = splitTableRow(line);
  return cells.length > 0 && cells.every((cell) => TABLE_DELIM_CELL_RE.test(cell));
}

// Splits a pipe-table row, honouring `\|` escapes. Leading/trailing empty cells
// from the boundary pipes are dropped; the `|---|---|` form relies on that.
function splitTableRow(line: string): string[] {
  let trimmed = line.trim();
  if (trimmed.startsWith('|')) trimmed = trimmed.slice(1);
  if (trimmed.endsWith('|') && !trimmed.endsWith('\\|')) trimmed = trimmed.slice(0, -1);

  const cells: string[] = [];
  let current = '';
  for (let i = 0; i < trimmed.length; i += 1) {
    if (trimmed[i] === '\\' && trimmed[i + 1] === '|') {
      current += '|';
      i += 1;
    } else if (trimmed[i] === '|') {
      cells.push(current.trim());
      current = '';
    } else {
      current += trimmed[i];
    }
  }
  cells.push(current.trim());
  return cells;
}

function tableAlign(cell: string): TableAlign {
  const left = cell.startsWith(':');
  const right = cell.endsWith(':');
  if (left && right) return 'center';
  if (right) return 'right';
  if (left) return 'left';
  return null;
}

// Finds the closing delimiter of an inline span starting at `open`, skipping
// backtick runs so `**a `code` b**` nests correctly. Returns -1 when
// unterminated, letting the caller leave the marker as literal text — which is
// what partial streaming output needs.
function findClose(src: string, delimiter: string, open: number): number {
  let i = open + delimiter.length;
  while (i < src.length) {
    if (src[i] === '\\') {
      i += 2;
      continue;
    }
    if (src[i] === '`') {
      const run = src.slice(i).match(/^`+/)![0].length;
      const close = src.indexOf('`'.repeat(run), i + run);
      if (close === -1) return -1;
      i = close + run;
      continue;
    }
    if (src.startsWith(delimiter, i)) return i;
    i += 1;
  }
  return -1;
}

function matchDelimiterRun(src: string, open: number, ch: string): InlineMatch | null {
  let run = 1;
  while (src[open + run] === ch) run += 1;
  const delimiter = ch.repeat(run);
  const close = findClose(src, delimiter, open);
  if (close === -1) return null;
  const inner = src.slice(open + run, close);
  if (!inner.trim()) return null;
  return {
    kind: 'emphasis',
    end: close + run,
    strong: run >= 2,
    children: parseInline(inner),
  };
}

// Code spans bind tighter than emphasis, so callers match them first. Returns
// null when the run at `open` must be treated as plain text.
function matchInlineAt(src: string, open: number): InlineMatch | null {
  const ch = src[open];

  if (ch === '\\') {
    const next = src[open + 1];
    // The alternate LaTeX delimiters `\(...\)` / `\[...\]` appear in model
    // output often enough to recognise; `\[...\]` is display mathematics.
    const closer = next === '(' ? '\\)' : next === '[' ? '\\]' : null;
    if (closer) {
      const close = src.indexOf(closer, open + 2);
      if (close === -1) return null;
      const value = src.slice(open + 2, close).trim();
      if (!value) return null;
      return { kind: 'math', end: close + 2, value, display: next === '[' };
    }
    if (next && '\\`*_~[]()$'.includes(next)) {
      return { kind: 'escape', end: open + 2, char: next };
    }
    return null;
  }

  // Display mathematics inside a line: `$$ ... $$`. It is not money, but the
  // span may not be left unclosed (streaming output keeps the source as text).
  if (ch === '$' && src[open + 1] === '$') {
    const close = src.indexOf('$$', open + 2);
    if (close === -1) return null;
    const value = src.slice(open + 2, close).trim();
    if (!value) return null;
    return { kind: 'math', end: close + 2, value, display: true };
  }

  // A formula: `$x^2$`. Money must stay money, so a `$...$` span only counts
  // as a formula when it LOOKS like one: it carries a LaTeX operator (`\`, `^`,
  // `_`, `{`, `}`, `=`, `+`, `<`, `>`), is a single non-digit symbol (`$x$`,
  // `$\mu$`), or is a compact term mixing digits and letters (`$2x$`). The
  // opening `$` may not follow a word character or a digit (`US$100`, `1$`),
  // the span may not break over a line, and the closing `$` may not be followed
  // by a digit (`$100`). Surrounding whitespace is trimmed (`$ x $` is a
  // formula), but a money-shaped span (`$ 100 $`, `$5 and $10`) is not.
  if (ch === '$' && src[open + 1] !== '$') {
    const before = open > 0 ? src[open - 1] : '';
    if (before && /[A-Za-z0-9]/.test(before)) return null;
    const close = src.indexOf('$', open + 1);
    if (close === -1) return null;
    const raw = src.slice(open + 1, close);
    if (!raw || /\n/.test(raw)) return null;
    const value = raw.trim();
    if (!value) return null;
    const after = src[close + 1] ?? '';
    if (/\d/.test(after)) return null;
    const compactTerm =
      !/\s/.test(value) &&
      /\d/.test(value) &&
      /[A-Za-z]/.test(value) &&
      !/^\d[\d,.]*[KMBT]$/i.test(value);
    if (!/[\\^_{}=+<>]/.test(value) && !/^[^\d\s]$/.test(value) && !compactTerm) {
      return null;
    }
    return { kind: 'math', end: close + 1, value, display: false };
  }

  if (ch === '`') {
    const run = src.slice(open).match(/^`+/)![0];
    const close = src.indexOf(run, open + run.length);
    if (close === -1) return null;
    // Per CommonMark, newlines inside a span collapse into spaces.
    const value = src.slice(open + run.length, close).replace(/\n/g, ' ');
    return { kind: 'code', end: close + run.length, value };
  }

  if (ch === '[') {
    const labelEnd = findClose(src, ']', open);
    if (labelEnd === -1 || src[labelEnd + 1] !== '(') return null;
    const destEnd = findClose(src, ')', labelEnd + 1);
    if (destEnd === -1) return null;
    const href = src.slice(labelEnd + 2, destEnd).trim().replace(/^<|>$/g, '');
    if (!href || /\s/.test(href)) return null;
    return {
      kind: 'link',
      end: destEnd + 1,
      href,
      children: parseInline(src.slice(open + 1, labelEnd)),
    };
  }

  if (ch === '~' && src[open + 1] === '~') {
    const close = findClose(src, '~~', open);
    if (close === -1) return null;
    return {
      kind: 'del',
      end: close + 2,
      children: parseInline(src.slice(open + 2, close)),
    };
  }

  if (ch === '*' || ch === '_') return matchDelimiterRun(src, open, ch);

  return null;
}

export function parseInline(src: string): InlineNode[] {
  const nodes: InlineNode[] = [];
  let buffer = '';
  let i = 0;

  const pushText = (value: string) => {
    const last = nodes[nodes.length - 1];
    if (last && last.type === 'text') {
      last.value += value;
    } else {
      nodes.push({ type: 'text', value });
    }
  };

  const flush = () => {
    if (buffer) {
      pushText(buffer);
      buffer = '';
    }
  };

  while (i < src.length) {
    const match = matchInlineAt(src, i);
    if (!match) {
      buffer += src[i];
      i += 1;
      continue;
    }

    flush();

    switch (match.kind) {
      case 'escape':
        pushText(match.char);
        break;
      case 'code':
        nodes.push({ type: 'code', value: match.value });
        break;
      case 'math':
        nodes.push({ type: 'math', value: match.value, display: match.display });
        break;
      case 'del':
        nodes.push({ type: 'del', children: match.children });
        break;
      case 'emphasis':
        nodes.push({
          type: match.strong ? 'strong' : 'em',
          children: match.children,
        });
        break;
      case 'link':
        nodes.push({ type: 'link', href: match.href, children: match.children });
        break;
    }

    i = match.end;
  }

  flush();
  return nodes;
}

// Reads a display formula beginning at `start` (`$$` / `\[`), on one line or
// across several. Returns null when the closing delimiter never appears, so an
// in-progress stream leaves the source visible rather than swallowing the rest.
function readDisplayMath(
  lines: string[],
  start: number,
): { value: string; next: number } | null {
  const line = lines[start];
  const open = line.trimStart().startsWith('$$') ? '$$' : '\\[';
  const close = open === '$$' ? '$$' : '\\]';
  const at = line.indexOf(open);
  const rest = line.slice(at + open.length);
  const sameLine = rest.indexOf(close);
  if (sameLine !== -1) {
    const value = rest.slice(0, sameLine).trim();
    return value ? { value, next: start + 1 } : null;
  }

  const body = [rest];
  for (let i = start + 1; i < lines.length; i += 1) {
    const end = lines[i].indexOf(close);
    if (end !== -1) {
      body.push(lines[i].slice(0, end));
      const value = body.join('\n').trim();
      return value ? { value, next: i + 1 } : null;
    }
    body.push(lines[i]);
  }
  return null;
}

export function parseMarkdown(src: string): BlockNode[] {
  const lines = src.replace(/\r\n?/g, '\n').split('\n');
  const blocks: BlockNode[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (!line.trim()) {
      i += 1;
      continue;
    }

    const fence = line.match(FENCE_RE);
    if (fence) {
      const language = fence[2] || null;
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !FENCE_CLOSE_RE.test(lines[i])) {
        body.push(lines[i]);
        i += 1;
      }
      // Skip the closing fence when present; leave an unterminated fence open
      // so streaming output still renders as a code block, not literal text.
      if (i < lines.length) i += 1;
      blocks.push({ type: 'code', language, value: body.join('\n') });
      continue;
    }

    // A display formula: `$$ ... $$` or `\[ ... \]`, on one line or across
    // several. Like a fence, it opens a block even when the preceding prose
    // line had no blank line after it.
    if (DISPLAY_MATH_START_RE.test(line)) {
      const math = readDisplayMath(lines, i);
      if (math) {
        blocks.push({ type: 'math', value: math.value });
        i = math.next;
        continue;
      }
    }

    if (HR_RE.test(line)) {
      blocks.push({ type: 'hr' });
      i += 1;
      continue;
    }

    const heading = line.match(HEADING_RE);
    if (heading) {
      blocks.push({
        type: 'heading',
        level: heading[1].length as 1 | 2 | 3 | 4 | 5 | 6,
        children: parseInline(heading[2]),
      });
      i += 1;
      continue;
    }

    if (BLOCKQUOTE_RE.test(line)) {
      const quoted: string[] = [];
      while (i < lines.length && (BLOCKQUOTE_RE.test(lines[i]) || !lines[i].trim())) {
        const m = lines[i].match(BLOCKQUOTE_RE);
        quoted.push(m ? m[1] : '');
        i += 1;
      }
      blocks.push({ type: 'blockquote', children: parseMarkdown(quoted.join('\n')) });
      continue;
    }

    // GFM pipe table: a header row followed by a `---|:---:` delimiter row.
    if (line.includes('|') && i + 1 < lines.length && isTableDelimiterRow(lines[i + 1])) {
      const align = splitTableRow(lines[i + 1]).map(tableAlign);
      const header = splitTableRow(line).map(parseInline);
      const rows: InlineNode[][][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim() && lines[i].includes('|')) {
        rows.push(splitTableRow(lines[i]).map(parseInline));
        i += 1;
      }
      blocks.push({ type: 'table', align, header, rows });
      continue;
    }

    const isUl = UL_RE.test(line);
    const isOl = OL_RE.test(line);
    if (isUl || isOl) {
      const ordered = isOl;
      const items: InlineNode[][] = [];
      while (i < lines.length) {
        const m = ordered ? lines[i].match(OL_RE) : lines[i].match(UL_RE);
        if (!m) break;
        items.push(parseInline(m[1]));
        i += 1;
      }
      blocks.push({ type: 'list', ordered, items });
      continue;
    }

    // Paragraph: consume until a blank line or the start of another block.
    // Display math only breaks the paragraph when it actually closes; an
    // unclosed `$$` in a stream stays visible as text.
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !startsBlock(lines, i)) {
      para.push(lines[i]);
      i += 1;
    }
    if (para.length === 0) {
      // Defensive: never loop forever if a future branch forgets to consume.
      i += 1;
      continue;
    }
    blocks.push({ type: 'paragraph', children: parseInline(para.join('\n')) });
  }

  return blocks;
}

export function isBlockStart(line: string): boolean {
  return (
    FENCE_RE.test(line) ||
    HEADING_RE.test(line) ||
    HR_RE.test(line) ||
    BLOCKQUOTE_RE.test(line) ||
    UL_RE.test(line) ||
    OL_RE.test(line)
  );
}

function startsBlock(lines: string[], i: number): boolean {
  const line = lines[i];
  if (DISPLAY_MATH_START_RE.test(line)) return readDisplayMath(lines, i) !== null;
  return isBlockStart(line);
}

/** Flatten inline nodes back to plain text (for copy actions). */
export function inlineText(nodes: InlineNode[]): string {
  return nodes
    .map((n) => {
      switch (n.type) {
        case 'text':
        case 'code':
          return n.value;
        case 'math':
          // A formula reads as its source in plain text (PDF, CSV, copy).
          return n.value;
        default:
          return inlineText(n.children);
      }
    })
    .join('');
}

/** Serialize a parsed table to TSV so a paste into a spreadsheet stays aligned. */
export function tableToTsv(header: InlineNode[][], rows: InlineNode[][][]): string {
  const line = (cells: InlineNode[][]) => cells.map((c) => inlineText(c)).join('\t');
  return [line(header), ...rows.map(line)].join('\n');
}

// ── Financial presentation helpers (pure; the view layer styles with them) ───
// These never invent data. They only recognise what the model actually wrote:
// numeric cells, explicit "unavailable" markers, and source/reference sections.

/**
 * A cell that reads as a number, so it can be right-aligned like a financial
 * table. Accepts thousands separators, currency symbols, signs, percent and
 * magnitude suffixes, and parenthesised negatives — but never a bare word (so
 * a ticker like `AAPL` is NOT treated as numeric).
 */
const NUMERIC_CELL_RE = /^[($€£¥]?\s*-?\d[\d,]*(?:\.\d+)?\s*(?:%|[KMBT])?\)?$/i;
export function isNumericText(text: string): boolean {
  const t = text.trim();
  if (!t) return false;
  return NUMERIC_CELL_RE.test(t);
}

/** A negative value: leading minus or accounting-style parentheses. */
export function isNegativeValue(text: string): boolean {
  const t = text.trim();
  return /^\(.*\)$/.test(t) || /^[($€£¥]?\s*-/.test(t);
}

/**
 * Markers the agent/backend use for data that is genuinely not available. They
 * are rendered distinctly so "we don't have this" never looks like a value.
 */
const UNAVAILABLE_RE = /^(unavailable|n\/?a|not available|—|-{2,}|null|nil|unknown)$/i;
export function isUnavailableText(text: string): boolean {
  return UNAVAILABLE_RE.test(text.trim());
}

/** Heading text that introduces a list of sources / references / citations. */
const SOURCE_HEADING_RE = /^(sources?|references?|citations?|further reading|see also)\b/i;
export function isSourceHeading(text: string): boolean {
  return SOURCE_HEADING_RE.test(text.trim());
}

/** The display host of a URL, e.g. `https://www.sec.gov/x` → `sec.gov`. */
export function extractHost(href: string): string | null {
  try {
    const h = new URL(href).hostname.replace(/^www\./, '');
    return h || null;
  } catch {
    return null;
  }
}

/** Collect every link node in an inline tree (for source-list rendering). */
export function collectLinks(nodes: InlineNode[]): { href: string; label: string }[] {
  const out: { href: string; label: string }[] = [];
  const walk = (list: InlineNode[]) => {
    for (const n of list) {
      if (n.type === 'link') out.push({ href: n.href, label: inlineText(n.children) });
      else if ('children' in n) walk(n.children);
    }
  };
  walk(nodes);
  return out;
}

export { splitTableRow };
