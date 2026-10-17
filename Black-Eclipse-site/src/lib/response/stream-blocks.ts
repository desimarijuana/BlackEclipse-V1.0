// ── Incremental (streaming) block decode ──────────────────────────────────────
// While an ```eclipse-response fence is still being written, the whole envelope is
// not valid JSON — but individual top-level `blocks[]` entries already are. This
// module scans the partial source and returns each COMPLETE block object, so the
// renderer can show blocks as they close instead of waiting for the whole answer.
//
// The hard rule (this is how a wrong figure would slip in): ONLY a fully closed,
// JSON-parseable object is ever returned as a block. A half-written block is
// never rendered as data — it stays the "composing" placeholder. The scanner is
// total: any odd input returns an empty/partial result, never a throw.
//
// The scan is a fast heuristic for the streaming path only; the settled path
// (`decodeResponseFence`) remains the authoritative full parse. Finalized blocks
// are cached by their raw JSON so a streaming frame only re-finalizes the block
// that actually changed.

import {
  RESPONSE_SCHEMA_VERSION,
  parseResponsePayload,
  type ParsedResponse,
  type ValidatedBlock,
} from './contract';
import { degradeUnknownBlock, finalizeParsed } from './finalize';

export interface ScannedBlocks {
  /** The `blocks` array has been opened. */
  started: boolean;
  /** The array has not yet closed — more blocks may stream in. */
  open: boolean;
  /** Every fully-closed element parsed so far. */
  blocks: unknown[];
  /** A top-level `title`, when its string value has closed. */
  title?: string;
}

const BLOCKS_KEY_RE = /"blocks"\s*:\s*\[/;

function findBlocksArray(source: string): number {
  const match = BLOCKS_KEY_RE.exec(source);
  return match ? match.index + match[0].length : -1;
}

/** Index just past the matching `}` for the object opening at `start`, or -1. */
function matchObject(source: string, start: number): number {
  let depth = 0;
  let inString = false;
  let escaped = false;
  for (let i = start; i < source.length; i++) {
    const c = source[i];
    if (inString) {
      if (escaped) escaped = false;
      else if (c === '\\') escaped = true;
      else if (c === '"') inString = false;
      continue;
    }
    if (c === '"') inString = true;
    else if (c === '{') depth += 1;
    else if (c === '}') {
      depth -= 1;
      if (depth === 0) return i + 1;
    }
  }
  return -1;
}

/** A top-level string value for `key`, when its string has fully closed. */
function closedStringValue(source: string, key: string): string | undefined {
  const match = new RegExp(`"${key}"\\s*:\\s*"`).exec(source);
  if (!match) return undefined;
  let raw = '';
  let escaped = false;
  for (let i = match.index + match[0].length; i < source.length; i++) {
    const c = source[i];
    if (escaped) {
      raw += c;
      escaped = false;
      continue;
    }
    if (c === '\\') {
      escaped = true;
      raw += c;
      continue;
    }
    if (c === '"') {
      try {
        return JSON.parse(`"${raw}"`) as string;
      } catch {
        return raw;
      }
    }
    raw += c;
  }
  return undefined; // the string has not closed yet
}

/** Scan a partial envelope for the complete top-level blocks written so far. */
export function scanCompleteBlocks(source: string): ScannedBlocks {
  const start = findBlocksArray(source);
  if (start < 0) return { started: false, open: false, blocks: [] };

  const result: ScannedBlocks = { started: true, open: true, blocks: [] };
  const title = closedStringValue(source, 'title');
  if (title !== undefined) result.title = title;

  let i = start;
  const n = source.length;
  while (i < n) {
    while (i < n && (source[i] === ',' || /\s/.test(source[i]))) i += 1;
    if (i >= n) break; // still open
    if (source[i] === ']') {
      result.open = false;
      break;
    }
    if (source[i] !== '{') break; // unexpected element: treat as open, stop
    const end = matchObject(source, i);
    if (end < 0) break; // object not closed yet
    const chunk = source.slice(i, end);
    try {
      result.blocks.push(JSON.parse(chunk));
    } catch {
      // A closed-but-unparseable element is dropped (never rendered as data).
    }
    i = end;
  }
  return result;
}

// ── Per-block finalization (the block-level chokepoint) ───────────────────────

const CACHE_LIMIT = 256;
const blockCache = new Map<string, ValidatedBlock>();

/** Validate + repair/degrade ONE raw block via the shared machinery. */
export function finalizeBlock(raw: unknown): ValidatedBlock {
  const parsed = parseResponsePayload({ blocks: [raw] });
  const finalized = finalizeParsed(parsed);
  return finalized.response.blocks[0] ?? degradeUnknownBlock(raw);
}

/** `finalizeBlock` with a bounded cache keyed by the raw block's JSON. */
export function finalizeBlockCached(raw: unknown): ValidatedBlock {
  let key: string;
  try {
    key = JSON.stringify(raw) ?? String(raw);
  } catch {
    return finalizeBlock(raw);
  }
  const cached = blockCache.get(key);
  if (cached) return cached;
  const block = finalizeBlock(raw);
  if (blockCache.size >= CACHE_LIMIT) {
    const oldest = blockCache.keys().next().value;
    if (oldest !== undefined) blockCache.delete(oldest);
  }
  blockCache.set(key, block);
  return block;
}

export type StreamingDecode =
  | { kind: 'empty' }
  | { kind: 'ok'; response: ParsedResponse }
  | { kind: 'composing' }
  | { kind: 'partial'; response: ParsedResponse; open: boolean };

/**
 * Decode a streaming fence source.
 *
 *   * `ok`        — the whole envelope already parses (render it complete).
 *   * `partial`   — the envelope is unfinished but N complete blocks exist; the
 *                   `response` holds only those, and `open` says more may come.
 *   * `composing` — nothing renderable yet (show the placeholder).
 *   * `empty`     — no content.
 *
 * A half-written block is never included.
 */
export function decodeResponseFenceStreaming(source: string): StreamingDecode {
  const trimmed = source.trim();
  if (!trimmed) return { kind: 'empty' };

  try {
    return { kind: 'ok', response: parseResponsePayload(JSON.parse(trimmed)) };
  } catch {
    // Not valid JSON yet — fall through to the incremental scan.
  }

  const scanned = scanCompleteBlocks(trimmed);
  if (!scanned.started || scanned.blocks.length === 0) return { kind: 'composing' };

  const response: ParsedResponse = {
    schemaVersion: RESPONSE_SCHEMA_VERSION,
    title: scanned.title,
    state: [],
    computed: [],
    blocks: scanned.blocks.map(finalizeBlockCached),
    diagnostics: [],
  };
  return { kind: 'partial', response, open: scanned.open };
}
