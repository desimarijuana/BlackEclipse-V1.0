// ── Source-referenced figures ─────────────────────────────────────────────────
// The mechanism that stops the model from RETYPING a financial figure: a figure
// value may be a reference (`{ "$ref": "<namespace>:<id>#/<field>" }`) resolved
// from a real surface instead of a literal. Resolution happens BEFORE render, so
// the renderer only ever sees a number (or an UNAVAILABLE marker) — never the
// raw reference string. A reference that cannot be resolved renders UNAVAILABLE;
// it NEVER falls back to the string, so "the model said 237" cannot masquerade as
// "the source returned 237".
//
// Pure and server-safe (no React, no network). The renderer supplies a resolver;
// the chat builds one from the turn's computed-result blob (`buildFigureResolver`).
// Other namespaces (tool/JDdS/artifact) have no client-side source yet, so a
// reference to them is honestly UNAVAILABLE until server-side resolution lands.

import type {
  FigureProvenance,
  FigureRef,
  ParsedResponse,
  ValidatedBlock,
} from './contract';

export type FigureNamespace = 'analysis' | 'tool' | 'jdds' | 'artifact';
export const FIGURE_NAMESPACES: readonly FigureNamespace[] = ['analysis', 'tool', 'jdds', 'artifact'];
const NAMESPACE_SET = new Set<string>(FIGURE_NAMESPACES);

export interface ResolvedFigure {
  value: number;
  provenance?: FigureProvenance;
}

/** Resolve `(namespace, id, pointer)` to a real value, or null for a miss. */
export type FigureResolver = (
  namespace: FigureNamespace,
  id: string,
  pointer: string,
) => ResolvedFigure | null;

export interface ParsedFigureRef {
  namespace: FigureNamespace;
  id: string;
  pointer: string;
}

/** Parse `<namespace>:<id>[#/<pointer>]`. Returns null for a bad/unknown form. */
export function parseFigureRef(ref: string): ParsedFigureRef | null {
  if (typeof ref !== 'string') return null;
  const hash = ref.indexOf('#');
  const head = hash >= 0 ? ref.slice(0, hash) : ref;
  const pointer = hash >= 0 ? ref.slice(hash) : '';
  const colon = head.indexOf(':');
  if (colon <= 0) return null;
  const namespace = head.slice(0, colon).trim();
  const id = head.slice(colon + 1).trim();
  if (!NAMESPACE_SET.has(namespace) || !id) return null;
  return { namespace: namespace as FigureNamespace, id, pointer };
}

function isFigureRef(value: unknown): value is FigureRef {
  return !!value && typeof value === 'object' && typeof (value as { $ref?: unknown }).$ref === 'string';
}

function computedRefId(value: unknown): string | null {
  if (value && typeof value === 'object' && typeof (value as { $computed?: unknown }).$computed === 'string') {
    return (value as { $computed: string }).$computed;
  }
  return null;
}

/** Resolve a single figure value, or null when it is not a ref / cannot resolve. */
export function resolveFigureValue(value: unknown, resolver: FigureResolver | null): ResolvedFigure | null {
  if (!isFigureRef(value)) return null;
  const parsed = parseFigureRef(value.$ref);
  if (!parsed || !resolver) return null;
  try {
    return resolver(parsed.namespace, parsed.id, parsed.pointer);
  } catch {
    return null;
  }
}

interface FigureItem {
  value: unknown;
  unavailable?: boolean;
  provenance?: FigureProvenance;
}

function resolveItem<T extends FigureItem>(
  item: T,
  resolver: FigureResolver | null,
  computed: Record<string, number> | null,
): T {
  // A computed binding (envelope `computed` from envelope `state`).
  const computedId = computedRefId(item.value);
  if (computedId) {
    const value = computed?.[computedId];
    if (typeof value === 'number' && Number.isFinite(value)) {
      return { ...item, value, provenance: { source: 'Computed in-chat' } };
    }
    return { ...item, value: 0, unavailable: true, provenance: undefined };
  }
  if (!isFigureRef(item.value)) return item;
  const resolved = resolveFigureValue(item.value, resolver);
  if (resolved) {
    return { ...item, value: resolved.value, provenance: resolved.provenance };
  }
  // Unresolvable: an explicit UNAVAILABLE — never the reference and never a
  // placeholder number.
  return { ...item, value: 0, unavailable: true, provenance: undefined };
}

function nestedBlocks(value: unknown): ValidatedBlock[] {
  return Array.isArray(value) ? (value as ValidatedBlock[]) : [];
}

/** Resolve every figure reference in a block, recursing into container blocks. */
function resolveBlock(
  block: ValidatedBlock,
  resolver: FigureResolver | null,
  computed: Record<string, number> | null,
): ValidatedBlock {
  switch (block.type) {
    case 'metric_grid':
      return { ...block, metrics: block.metrics.map((m) => resolveItem(m, resolver, computed)) };
    case 'stat_hero':
      return { ...block, stats: block.stats.map((s) => resolveItem(s, resolver, computed)) };
    case 'tabs':
      return {
        ...block,
        tabs: block.tabs.map((tab) => ({
          ...tab,
          blocks: nestedBlocks(tab.blocks).map((b) => resolveBlock(b, resolver, computed)),
        })),
      };
    case 'report':
      return {
        ...block,
        sections: block.sections.map((section) => ({
          ...section,
          blocks: nestedBlocks(section.blocks).map((b) => resolveBlock(b, resolver, computed)),
        })),
      };
    case 'carousel':
      return {
        ...block,
        slides: block.slides.map((slide) => ({
          ...slide,
          blocks: nestedBlocks(slide.blocks).map((b) => resolveBlock(b, resolver, computed)),
        })),
      };
    case 'layout':
      return {
        ...block,
        blocks: nestedBlocks(block.blocks).map((b) => resolveBlock(b, resolver, computed)),
      };
    default:
      return block;
  }
}

/**
 * Return a copy of `response` with every figure reference resolved. A reference
 * that cannot be resolved becomes an explicit UNAVAILABLE item — a reference is
 * never left in the tree and never becomes a literal.
 */
export function resolveResponseFigures(
  response: ParsedResponse,
  resolver: FigureResolver | null,
  computed: Record<string, number> | null = null,
): ParsedResponse {
  return { ...response, blocks: response.blocks.map((b) => resolveBlock(b, resolver, computed)) };
}

interface AnalysisBlob {
  outputs: Record<string, unknown>;
  provenance?: { label?: string; detail?: string };
}

function coerceAnalysis(raw: unknown): AnalysisBlob | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const blob = raw as Record<string, unknown>;
  const outputs =
    blob.outputs && typeof blob.outputs === 'object' && !Array.isArray(blob.outputs)
      ? (blob.outputs as Record<string, unknown>)
      : null;
  if (!outputs) return null;
  const provenance =
    blob.provenance && typeof blob.provenance === 'object'
      ? (blob.provenance as { label?: string; detail?: string })
      : undefined;
  return { outputs, provenance };
}

function numericValue(raw: unknown): number | null {
  if (typeof raw === 'number' && Number.isFinite(raw)) return raw;
  if (typeof raw === 'string') {
    const n = Number(raw.replace(/[%,$\s,]/g, ''));
    return Number.isFinite(n) ? n : null;
  }
  return null;
}

/**
 * Build a resolver from the turn's own data. Today only the `analysis` namespace
 * (this run's computed-result outputs) has a client-side source; a reference to
 * any other namespace resolves to null (UNAVAILABLE) until server-side resolution
 * lands. Returns null when the turn has no computed result.
 */
export function buildFigureResolver(sources: { analysis?: unknown }): FigureResolver | null {
  const analysis = coerceAnalysis(sources.analysis);
  if (!analysis) return null;
  return (namespace, _id, pointer) => {
    if (namespace !== 'analysis') return null;
    const key = /^#\/outputs\/(.+)$/.exec(pointer)?.[1];
    if (!key) return null;
    const value = numericValue(analysis.outputs[key]);
    if (value == null) return null;
    return {
      value,
      provenance: {
        source: analysis.provenance?.label,
        method: analysis.provenance?.detail,
      },
    };
  };
}
