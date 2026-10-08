// ─────────────────────────────────────────────────────────────────────────────
// Vision run view — the client read model for the right-sidebar vision panel.
//
// The Python runtime collects every `vision_*` tool result into a bounded run
// blob (`VisionCollector.to_blob()`), carried on the run record and
// `client.final`. This module is a small, defensive coercion of that blob into a
// typed view the UI renders. Nothing here talks to the network and nothing is
// fabricated: an absent/odd shape yields null (no panel) rather than an empty
// panel pretending analysis happened.
// ─────────────────────────────────────────────────────────────────────────────

import type {
  VisionObservation,
  VisionRegion,
  VisionResultInfo,
  VisionRunInfo,
  VisionTextSpan,
} from './types';

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value);
}

function region(raw: unknown): VisionRegion | null {
  if (!isRecord(raw)) return null;
  const x = Number(raw.x ?? 0);
  const y = Number(raw.y ?? 0);
  const width = Number(raw.width ?? 0);
  const height = Number(raw.height ?? 0);
  if (![x, y, width, height].every(Number.isFinite)) return null;
  const bbox = Array.isArray(raw.bbox) ? (raw.bbox as number[]) : undefined;
  return { x, y, width, height, ...(bbox ? { bbox } : {}), ...(typeof raw.label === 'string' ? { label: raw.label } : {}) };
}

function observation(raw: unknown): VisionObservation | null {
  if (!isRecord(raw)) return null;
  const text = typeof raw.text === 'string' ? raw.text : '';
  if (!text) return null;
  return {
    text,
    ...(typeof raw.kind === 'string' ? { kind: raw.kind } : {}),
    ...(typeof raw.method === 'string' ? { method: raw.method } : {}),
    ...(typeof raw.confidence === 'number' ? { confidence: raw.confidence } : {}),
    region: region(raw.region),
  };
}

function textSpan(raw: unknown): VisionTextSpan | null {
  if (!isRecord(raw)) return null;
  const text = typeof raw.text === 'string' ? raw.text : '';
  if (!text) return null;
  const bounds = region(raw.bounds);
  return {
    text,
    ...(bounds ? { bounds } : {}),
    ...(typeof raw.confidence === 'number' ? { confidence: raw.confidence } : {}),
  };
}

function result(raw: unknown): VisionResultInfo | null {
  if (!isRecord(raw)) return null;
  const observations = Array.isArray(raw.observations)
    ? (raw.observations.map(observation).filter(Boolean) as VisionObservation[])
    : [];
  const text = Array.isArray(raw.text) ? (raw.text.map(textSpan).filter(Boolean) as VisionTextSpan[]) : [];
  return {
    ok: raw.ok !== false,
    ...(typeof raw.mode === 'string' ? { mode: raw.mode } : {}),
    ...(typeof raw.description === 'string' ? { description: raw.description } : {}),
    ...(typeof raw.assetId === 'string' ? { assetId: raw.assetId } : {}),
    ...(typeof raw.provider === 'string' ? { provider: raw.provider } : {}),
    ...(typeof raw.model === 'string' ? { model: raw.model } : {}),
    ...(typeof raw.backend === 'string' ? { backend: raw.backend } : {}),
    ...(typeof raw.confidence === 'number' ? { confidence: raw.confidence } : {}),
    ...(typeof raw.latencyMs === 'number' ? { latencyMs: raw.latencyMs } : {}),
    ...(typeof raw.cached === 'boolean' ? { cached: raw.cached } : {}),
    observations,
    text,
    ...(Array.isArray(raw.tables) ? { tables: raw.tables } : {}),
    ...(isRecord(raw.chart) ? { chart: raw.chart } : {}),
    ...(isRecord(raw.comparison) ? { comparison: raw.comparison } : {}),
    ...(isRecord(raw.document) ? { document: raw.document } : {}),
    ...(Array.isArray(raw.warnings) ? { warnings: raw.warnings as string[] } : {}),
    ...(isRecord(raw.provenance) ? { provenance: raw.provenance as VisionResultInfo['provenance'] } : {}),
  };
}

/** Coerce a run's raw vision blob into a typed view, or null when absent. */
export function coerceVisionRun(raw: unknown): VisionRunInfo | null {
  if (!isRecord(raw)) return null;
  const results = Array.isArray(raw.results)
    ? (raw.results.map(result).filter(Boolean) as VisionResultInfo[])
    : [];
  const failures = Array.isArray(raw.failures) ? raw.failures : [];
  if (results.length === 0 && failures.length === 0) return null;
  return {
    ...(typeof raw.type === 'string' ? { type: raw.type } : {}),
    status: typeof raw.status === 'string' ? raw.status : 'collected',
    count: typeof raw.count === 'number' ? raw.count : results.length,
    results,
    failures: (failures as VisionRunInfo['failures']) ?? null,
  };
}

/** The single most recent successful result (what the panel focuses on). */
export function primaryVisionResult(run: VisionRunInfo | null): VisionResultInfo | null {
  if (!run || run.results.length === 0) return null;
  return run.results[run.results.length - 1];
}
