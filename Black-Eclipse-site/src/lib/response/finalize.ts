// ── Response finalization (the render chokepoint) ─────────────────────────────
//
// THE INVARIANT: the renderer must be a TOTAL function from any input to a
// proper render. There must be no input that produces a user-visible *error*.
//
// `parseResponsePayload` is total, but its totality is "degrade to a diagnostic
// card" — which is exactly the error a user must never see. This module is the
// single chokepoint every render path passes through: it parses, then replaces
// any block the contract rejected (`unknown`) with a readable block carrying the
// block's REAL content (never fabricated), and downgrades every error diagnostic
// so the UI cannot raise a diagnostics panel. The raw diagnostics are retained
// on the response and surfaced through the `degraded` telemetry records so the
// failure rate can be measured and driven to zero.
//
// It is pure and framework-free: no React, no network.

import {
  RESPONSE_SCHEMA_VERSION,
  parseResponsePayload,
  type ParsedResponse,
  type ValidatedBlock,
} from './contract';
import { responseBlockMeta } from './schema-meta';
import { repairUnknownBlock } from './repair';

/** A block that could not be validated, recorded for telemetry — never shown as an error. */
export interface DegradeRecord {
  code: string;
  message: string;
  blockIndex?: number;
  declaredType?: string;
}

export interface FinalizedResponse {
  response: ParsedResponse;
  /** One record per block/diagnostic that had to be repaired or degraded. */
  degraded: DegradeRecord[];
}

const MARKDOWN_BLOCK_MAX = 4000;

// Field names a producer plausibly uses for the human-readable body of a block
// that otherwise failed to validate. Used only to RESCUE real content — the
// backstop never invents text.
const BODY_KEYS = [
  'markdown', 'text', 'content', 'body', 'summary', 'description',
  'caption', 'message', 'note', 'detail', 'label', 'value',
];
const TITLE_KEYS = ['title', 'heading', 'summary', 'label'];

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function firstString(obj: Record<string, unknown>, keys: string[]): string | undefined {
  for (const key of keys) {
    const value = obj[key];
    if (typeof value === 'string' && value.trim()) return value;
  }
  return undefined;
}

function boundedCode(source: string): string {
  const trimmed = source.length > MARKDOWN_BLOCK_MAX ? `${source.slice(0, MARKDOWN_BLOCK_MAX)}\n…` : source;
  return `\`\`\`json\n${trimmed}\n\`\`\``;
}

/**
 * Degrade a block the contract rejected into a readable `markdown` block.
 *
 * Prefers the block's own prose/title; otherwise shows its structure as a JSON
 * code fence so no data is lost. It never fabricates and never renders an error
 * affordance — a wrong block costs its visual, never the answer.
 */
export function degradeUnknownBlock(raw: unknown): Extract<ValidatedBlock, { type: 'markdown' }> {
  const obj = asRecord(raw);
  if (!obj) {
    const text = typeof raw === 'string' ? raw : raw == null ? '' : String(raw);
    return { type: 'markdown', markdown: text };
  }
  const title = firstString(obj, TITLE_KEYS);
  const body = firstString(obj, BODY_KEYS);
  if (body) {
    return { type: 'markdown', markdown: title && title !== body ? `**${title}**\n\n${body}` : body };
  }
  let json: string;
  try {
    json = JSON.stringify(obj, null, 2) ?? String(raw);
  } catch {
    json = String(raw);
  }
  const header = title ? `**${title}**\n\n` : '';
  return { type: 'markdown', markdown: `${header}${boundedCode(json)}` };
}

/** Degrade a raw fence source (malformed JSON) into a readable markdown block. */
function degradeSourceText(source: string): Extract<ValidatedBlock, { type: 'markdown' }> {
  return { type: 'markdown', markdown: boundedCode(source) };
}

/** Recursively degrade `unknown` blocks, including inside tabs/report/carousel. */
function degradeBlocks(blocks: ValidatedBlock[], degraded: DegradeRecord[]): ValidatedBlock[] {
  return blocks.map((block, index) => {
    switch (block.type) {
      case 'unknown': {
        // Phase 2: one deterministic, schema-directed repair attempt BEFORE the
        // backstop, so a drifted block renders as its intended visual.
        const meta = responseBlockMeta().get(block.declaredType);
        const candidate = repairUnknownBlock(block.raw, meta?.fields);
        const reparsed = parseResponsePayload({ blocks: [candidate] });
        const repaired = reparsed.blocks[0];
        if (repaired && repaired.type !== 'unknown') {
          degraded.push({
            code: 'BLOCK_REPAIRED',
            message: 'block was repaired to match the schema',
            blockIndex: index,
            declaredType: block.declaredType,
          });
          // A repaired block may be a container; recurse so any nested rejected
          // blocks are repaired/degraded too.
          return degradeBlocks([repaired], degraded)[0];
        }
        degraded.push({
          code: 'BLOCK_DEGRADED',
          message: 'block did not match the schema; shown as readable content',
          blockIndex: index,
          declaredType: block.declaredType,
        });
        return degradeUnknownBlock(block.raw);
      }
      case 'tabs':
        return {
          ...block,
          tabs: block.tabs.map((tab) => ({ ...tab, blocks: degradeBlocks(tab.blocks as ValidatedBlock[], degraded) })),
        };
      case 'report':
        return {
          ...block,
          sections: block.sections.map((section) =>
            section.blocks
              ? { ...section, blocks: degradeBlocks(section.blocks as ValidatedBlock[], degraded) }
              : section,
          ),
        };
      case 'carousel':
        return {
          ...block,
          slides: block.slides.map((slide) => ({
            ...slide,
            blocks: degradeBlocks(slide.blocks as ValidatedBlock[], degraded),
          })),
        };
      default:
        return block;
    }
  });
}

/**
 * Finalize an already-parsed response: degrade rejected blocks and downgrade
 * every error diagnostic to a non-fatal note so the UI shows no error. Pure.
 */
export function finalizeParsed(response: ParsedResponse): FinalizedResponse {
  const degraded: DegradeRecord[] = [];
  const blocks = degradeBlocks(response.blocks, degraded);
  const diagnostics = response.diagnostics.map((diagnostic) => {
    if (diagnostic.severity !== 'error') return diagnostic;
    degraded.push({
      code: diagnostic.code,
      message: diagnostic.message,
      blockIndex: diagnostic.blockIndex,
      declaredType: diagnostic.declaredType,
    });
    return { ...diagnostic, severity: 'warning' as const };
  });
  return { response: { ...response, blocks, diagnostics }, degraded };
}

/**
 * The raw-input chokepoint: parse ANY value, then finalize it. An invalid
 * envelope (which yields no blocks) degrades the whole raw input to readable
 * content rather than an empty error region.
 */
export function finalizeResponse(raw: unknown): FinalizedResponse {
  const parsed = parseResponsePayload(raw);
  const finalized = finalizeParsed(parsed);
  const result =
    finalized.response.blocks.length === 0 && finalized.degraded.length > 0
      ? { response: { ...finalized.response, blocks: [degradeUnknownBlock(raw)] }, degraded: finalized.degraded }
      : finalized;
  reportResponseDegrade(result.degraded);
  return result;
}

/** Finalize a fence's raw JSON source. Malformed JSON degrades to a code fence. */
export function finalizeFenceSource(source: string): FinalizedResponse {
  const trimmed = source.trim();
  if (!trimmed) {
    return { response: { schemaVersion: RESPONSE_SCHEMA_VERSION, blocks: [], diagnostics: [] }, degraded: [] };
  }
  let value: unknown;
  try {
    value = JSON.parse(trimmed);
  } catch (error) {
    const message = error instanceof Error ? error.message : 'invalid JSON';
    const result: FinalizedResponse = {
      response: { schemaVersion: RESPONSE_SCHEMA_VERSION, blocks: [degradeSourceText(source)], diagnostics: [] },
      degraded: [{ code: 'MALFORMED_JSON', message }],
    };
    reportResponseDegrade(result.degraded);
    return result;
  }
  return finalizeResponse(value);
}

// ── Telemetry seam (wired to real reporting in a later phase) ──────────────────
type DegradeReporter = (records: DegradeRecord[]) => void;

let reporter: DegradeReporter | null = null;

/** Install a reporter for degraded/repaired blocks. Returns an uninstall handle. */
export function setResponseDegradeReporter(next: DegradeReporter | null): () => void {
  reporter = next;
  return () => {
    if (reporter === next) reporter = null;
  };
}

/** Report degraded blocks (no-op unless a reporter is installed). Always logged in dev. */
export function reportResponseDegrade(records: DegradeRecord[]): void {
  if (records.length === 0) return;
  if (process.env.NODE_ENV !== 'production') {
    // eslint-disable-next-line no-console
    console.warn('[eclipse-response] degraded blocks', records);
  }
  reporter?.(records);
}
