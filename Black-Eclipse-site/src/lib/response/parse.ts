// ── Fenced Eclipse response extraction ───────────────────────────────────────
//
// An assistant turn opts into the Interactive Response Engine by emitting a
// fenced code block whose info string is `eclipse-response` (see
// docs/interactive-response-engine.md for the producer contract). Everything
// outside such fences stays ordinary Markdown.
//
// This module is pure and framework-free so it can be unit-tested and reused by
// any surface. It never executes anything —— it only splits text and decodes
// JSON, then hands the value to the validated contract parser.

import {
  RESPONSE_FENCE_LANGUAGE,
  parseResponsePayload,
  type ParsedResponse,
} from './contract';

export interface TextSegment {
  kind: 'markdown';
  text: string;
}

export interface ResponseSegment {
  kind: 'response';
  /** Raw JSON source between the fences (for diagnostics / warnings). */
  source: string;
  /** Whether the closing fence was present. */
  closed: boolean;
}

export type ResponseSegmentOrText = TextSegment | ResponseSegment;

const OPEN_FENCE_RE = /^ {0,3}(`{3,}|~{3,})\s*([^\s`]*)\s*$/;
const CLOSE_FENCE_RE = /^ {0,3}(?:`{3,}|~{3,})\s*$/;

/**
 * Split Markdown into alternating prose and `eclipse-response` fence segments.
 * Unterminated fences are returned with `closed: false` so callers can treat a
 * streaming turn differently from a settled one.
 */
export function splitResponseSegments(markdown: string): ResponseSegmentOrText[] {
  const lines = markdown.replace(/\r\n?/g, '\n').split('\n');
  const segments: ResponseSegmentOrText[] = [];
  let buffer: string[] = [];
  let i = 0;

  const flushText = () => {
    if (buffer.length === 0) return;
    segments.push({ kind: 'markdown', text: buffer.join('\n') });
    buffer = [];
  };

  while (i < lines.length) {
    const open = lines[i].match(OPEN_FENCE_RE);
    if (open && open[2] === RESPONSE_FENCE_LANGUAGE) {
      flushText();
      const body: string[] = [];
      i += 1;
      let closed = false;
      while (i < lines.length) {
        if (CLOSE_FENCE_RE.test(lines[i])) {
          closed = true;
          i += 1;
          break;
        }
        body.push(lines[i]);
        i += 1;
      }
      segments.push({ kind: 'response', source: body.join('\n'), closed });
      continue;
    }
    buffer.push(lines[i]);
    i += 1;
  }
  flushText();
  return segments;
}

export type DecodeResult =
  | { status: 'ok'; response: ParsedResponse }
  | { status: 'empty' }
  | { status: 'incomplete'; error: string }
  | { status: 'malformed'; error: string };

/**
 * Decode one response fence's source into a validated `ParsedResponse`.
 *
 * `settled` distinguishes a finished turn (a malformed body is a real error)
 * from a streaming turn (a body that is not yet valid JSON is simply incomplete
 * and the renderer shows a composing placeholder instead of an error).
 *
 * JSON syntax errors are treated as `incomplete` while streaming and as
 * `malformed` once settled; schema failures (valid JSON, invalid blocks) are
 * always `ok` because `parseResponsePayload` degrades per-block.
 */
export function decodeResponseFence(source: string, settled = true): DecodeResult {
  const trimmed = source.trim();
  if (!trimmed) return { status: 'empty' };

  let value: unknown;
  try {
    value = JSON.parse(trimmed);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'Unexpected end of JSON input';
    return settled ? { status: 'malformed', error: message } : { status: 'incomplete', error: message };
  }
  return { status: 'ok', response: parseResponsePayload(value) };
}

/** Convenience for tests and non-React callers: parse the FIRST response fence. */
export function parseFirstResponseFence(markdown: string, settled = true): DecodeResult | null {
  const segment = splitResponseSegments(markdown).find((s): s is ResponseSegment => s.kind === 'response');
  if (!segment) return null;
  return decodeResponseFence(segment.source, settled);
}

/** True when the markdown contains at least one Eclipse response fence. */
export function hasResponseFence(markdown: string): boolean {
  return splitResponseSegments(markdown).some((s) => s.kind === 'response');
}
