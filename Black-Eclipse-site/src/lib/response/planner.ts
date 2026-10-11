// ── Response planner (deterministic) ─────────────────────────────────────────
// Turns an ordinary Markdown answer into structured blocks WITHOUT asking the
// model or inventing anything. It only *re-presents* what is already there:
//
//   • GFM pipe tables          → interactive `data_table` blocks
//   • "Sources/References …"   → `citations` blocks (when the list is links)
//   • everything else          → one `markdown` block (byte-identical rendering)
//
// It is deterministic, pure and total. It never fabricates values, never
// reorders content, and leaves fenced code untouched. When it finds nothing to
// upgrade it returns a single markdown block, so an ordinary answer renders
// exactly as before.

import {
  collectLinks,
  inlineText,
  isSourceHeading,
  parseInline,
  splitTableRow,
  type TableAlign,
} from '@/lib/chat/markdown';
import {
  RESPONSE_SCHEMA_VERSION,
  type ParsedResponse,
  type TableCell,
  type ValidatedBlock,
} from './contract';

const FENCE_RE = /^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)\s*$/;
const FENCE_CLOSE_RE = /^ {0,3}(?:`{3,}|~{3,})\s*$/;
const HEADING_RE = /^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
const UL_RE = /^ {0,3}[-*+][ \t]+(.*)$/;
const OL_RE = /^ {0,3}\d{1,9}[.)][ \t]+(.*)$/;
const DELIM_CELL_RE = /^:?-{1,}:?$/;

function alignOf(cell: string): TableAlign {
  const left = cell.startsWith(':');
  const right = cell.endsWith(':');
  if (left && right) return 'center';
  if (right) return 'right';
  if (left) return 'left';
  return null;
}

function isDelimiterRow(line: string): boolean {
  const cells = splitTableRow(line);
  return cells.length > 0 && cells.every((cell) => DELIM_CELL_RE.test(cell));
}

function isTableStart(lines: string[], i: number): boolean {
  if (i + 1 >= lines.length) return false;
  const header = lines[i];
  return header.includes('|') && isDelimiterRow(lines[i + 1]);
}

function readTable(lines: string[], i: number): { block: ValidatedBlock; next: number } {
  const headerCells = splitTableRow(lines[i]);
  const align = splitTableRow(lines[i + 1]).map(alignOf);
  const columns = headerCells.map((label, index) => ({
    key: `c${index}`,
    label: label || `Column ${index + 1}`,
    align: align[index] ?? undefined,
  }));
  const rows: Record<string, TableCell>[] = [];
  let j = i + 2;
  while (j < lines.length && lines[j].trim() && lines[j].includes('|')) {
    const cells = splitTableRow(lines[j]);
    const row: Record<string, TableCell> = {};
    columns.forEach((col, index) => {
      row[col.key] = cells[index] ?? '';
    });
    rows.push(row);
    j += 1;
  }
  return {
    block: { type: 'data_table', columns, rows, filterable: true, sortable: true, pageSize: 25 },
    next: j,
  };
}

function sourceHeadingText(line: string): string | null {
  const heading = line.match(HEADING_RE);
  if (!heading) return null;
  return isSourceHeading(heading[2]) ? heading[2] : null;
}

/**
 * A list item is a "source item" when it contains at least one link and almost
 * no prose beyond the links (mirrors the Markdown renderer's own source-list
 * heuristic, so the planner and the renderer agree).
 */
function sourceItem(text: string): { title: string; url: string; snippet?: string } | null {
  const nodes = parseInline(text);
  const links = collectLinks(nodes);
  if (links.length === 0) return null;
  const textWithoutLinks = inlineText(nodes)
    .replace(links.map((l) => l.label).join(''), '')
    .replace(/[\s—–\-:.]/g, '');
  if (textWithoutLinks.length > 3) return null;
  const primary = links[0];
  const snippet = text
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '')
    .replace(/^[\s—–\-:.]+/, '')
    .trim();
  return { title: primary.label || primary.href, url: primary.href, snippet: snippet || undefined };
}

function readSourceList(lines: string[], i: number, heading: string): { block: ValidatedBlock; next: number } | null {
  const sources: { title: string; url: string; snippet?: string }[] = [];
  let j = i + 1;
  while (j < lines.length) {
    const line = lines[j];
    if (!line.trim()) break;
    const m = line.match(UL_RE) ?? line.match(OL_RE);
    if (!m) break;
    const item = sourceItem(m[1]);
    if (!item) return null; // not a pure source list → leave as prose
    try {
      // Only http(s) citations are allowed; a `javascript:`/`data:` scheme is
      // never rendered as a link.
      const parsed = new URL(item.url);
      if (parsed.protocol !== 'http:' && parsed.protocol !== 'https:') return null;
    } catch {
      return null;
    }
    sources.push(item);
    j += 1;
  }
  if (sources.length === 0) return null;
  return { block: { type: 'citations', title: heading, sources }, next: j };
}

export function planMarkdown(markdown: string): ParsedResponse {
  const lines = markdown.replace(/\r\n?/g, '\n').split('\n');
  const blocks: ValidatedBlock[] = [];
  let buffer: string[] = [];

  const flush = () => {
    const text = buffer.join('\n');
    if (text.trim()) blocks.push({ type: 'markdown', markdown: text });
    buffer = [];
  };

  let i = 0;
  let inFence = false;
  while (i < lines.length) {
    const line = lines[i];

    if (inFence) {
      buffer.push(line);
      if (FENCE_CLOSE_RE.test(line)) inFence = false;
      i += 1;
      continue;
    }
    if (FENCE_RE.test(line)) {
      inFence = true;
      buffer.push(line);
      i += 1;
      continue;
    }

    if (isTableStart(lines, i)) {
      flush();
      const table = readTable(lines, i);
      blocks.push(table.block);
      i = table.next;
      continue;
    }

    const heading = sourceHeadingText(line);
    if (heading) {
      const sourceList = readSourceList(lines, i, heading);
      if (sourceList) {
        flush();
        blocks.push(sourceList.block);
        i = sourceList.next;
        continue;
      }
    }

    buffer.push(line);
    i += 1;
  }
  flush();

  if (blocks.length === 0) {
    blocks.push({ type: 'markdown', markdown });
  }

  return { schemaVersion: RESPONSE_SCHEMA_VERSION, blocks, diagnostics: [] };
}

/** True when the planner found anything worth upgrading beyond raw markdown. */
export function plannerUpgraded(response: ParsedResponse): boolean {
  return response.blocks.some((b) => b.type !== 'markdown');
}
