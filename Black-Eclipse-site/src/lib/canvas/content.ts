'use client';

// ─── Canvas content — what the viewer shows ──────────────────────────────────
// Canvas is a spacious VIEW of what the chat already produced: a markdown
// answer, a code block, a structured response envelope (report/charts/tables),
// a URL or an image. `contentFromMessage` derives the canonical content from a
// saved assistant message with no new schema — it reuses the response parser and
// the markdown projection.

import type { ParsedResponse } from '@/lib/response/contract';
import { parseResponsePayload } from '@/lib/response/contract';
import { splitResponseSegments } from '@/lib/response/parse';
import { toMarkdownProjection } from '@/lib/response/projection';

export type CanvasContentKind = 'markdown' | 'code' | 'report' | 'url' | 'image';

export interface CanvasContent {
  /** Stable key for the open view (not persisted). */
  id: string;
  kind: CanvasContentKind;
  title: string;
  /** Canonical markdown for `markdown` kind. */
  markdown?: string;
  /** Canonical source for `code` kind. */
  code?: { language?: string; text: string };
  /** The parsed envelope for `report` kind (rendered by ResponseView). */
  response?: ParsedResponse;
  /** Source URL for `url`/`image` kinds. */
  url?: string;
  /**
   * False for ephemeral response content (view-only). True when backed by a
   * saved canvas artifact the editor can write.
   */
  editable: boolean;
  /** Set when this view is backed by a canvas artifact. */
  artifactId?: string;
}

/** Block types that make a response read as a structured report, not prose. */
const REPORT_BLOCKS = new Set([
  'report', 'chart', 'financial_chart', 'data_table', 'diagram', 'flow', 'mermaid',
  'timeline', 'gauge', 'metric_grid', 'comparison_grid', 'node_graph', 'model3d', 'interactive',
  'anatomy', 'simulation', 'gallery', 'badge_row', 'ranked_list', 'stat_hero',
  'workflow', 'infographic', 'tabs', 'carousel', 'learning_map', 'layout', 'key_value',
]);

/** If the whole markdown is exactly one fenced block, return it as code. */
function singleCodeFence(markdown: string): { language?: string; text: string } | null {
  const match = /^\s*```([\w+#.-]*)\s*\n([\s\S]*?)\n```\s*$/.exec(markdown);
  if (!match) return null;
  const language = match[1] || undefined;
  if (language === 'eclipse-response' || language === 'mermaid') return null;
  return { language, text: match[2].replace(/\r\n?/g, '\n') };
}

function decodeResponseSource(source: string): ParsedResponse | null {
  try {
    return parseResponsePayload(JSON.parse(source));
  } catch {
    return null;
  }
}

function responseTitle(response: ParsedResponse, fallback: string): string {
  return response.title?.trim() || response.responseId?.trim() || fallback;
}

/** Build canvas content from an already-parsed response envelope. */
export function contentFromResponse(
  response: ParsedResponse,
  opts: { title?: string; id?: string } = {},
): CanvasContent {
  const title = responseTitle(response, opts.title ?? 'Eclipse response');
  const structured = response.blocks.some((block) => REPORT_BLOCKS.has(block.type));
  if (structured) {
    return { id: opts.id ?? `resp-${response.responseId ?? 'view'}`, kind: 'report', title, response, editable: false };
  }
  const markdown = toMarkdownProjection(response);
  const code = singleCodeFence(markdown);
  if (code) {
    return { id: opts.id ?? `resp-${response.responseId ?? 'view'}`, kind: 'code', title, code, editable: false };
  }
  return { id: opts.id ?? `resp-${response.responseId ?? 'view'}`, kind: 'markdown', title, markdown, editable: false };
}

/**
 * Derive canvas content from an assistant message's raw content: an
 * `eclipse-response` fence becomes a report/code/markdown view, plain markdown
 * stays markdown, and a lone code fence becomes a code view.
 */
export function contentFromMessage(
  text: string,
  opts: { title?: string; id?: string } = {},
): CanvasContent {
  const id = opts.id ?? 'message';
  const segments = splitResponseSegments(text);
  const responseSegment = segments.find((segment) => segment.kind === 'response');
  if (responseSegment && responseSegment.kind === 'response') {
    const parsed = decodeResponseSource(responseSegment.source);
    if (parsed) return contentFromResponse(parsed, { title: opts.title, id });
  }
  const markdown = text.replace(/\r\n?/g, '\n').trim();
  const code = singleCodeFence(markdown);
  if (code) return { id, kind: 'code', title: opts.title ?? 'Eclipse response', code, editable: false };
  return { id, kind: 'markdown', title: opts.title ?? 'Eclipse response', markdown, editable: false };
}

/** Canvas content backed by a saved artifact (viewer + editor). */
export function contentFromArtifact(input: {
  artifactId: string;
  title: string;
  kind: CanvasContentKind;
}): CanvasContent {
  return {
    id: `artifact-${input.artifactId}`,
    kind: input.kind,
    title: input.title,
    editable: true,
    artifactId: input.artifactId,
  };
}
