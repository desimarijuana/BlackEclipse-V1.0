// ─── Acquisition (bulk collection) wire types (Phase 16) ────────────────────
// The manifest the `acquire` tool emits (`acquire.completed`). This module adds
// NO agentic logic (mirrors analysis-types.ts): it narrows the runtime blob so
// the chat can render source / window / rows / completeness / licence /
// attribution, and a partial pull can NEVER be shown as the dataset —
// completeness is structural, and an unknown completeness is PARTIAL.

export interface AcquisitionSourceReport {
  id: string;
  label: string;
  windowFrom: string | null;
  windowTo: string | null;
  rows: number | null;
  file: string | null;
  complete: boolean;
  stoppedReason: string | null;
  licence: string | null;
  attribution: string | null;
}

export interface AcquisitionManifest {
  purpose: string | null;
  collectedAt: string | null;
  sources: AcquisitionSourceReport[];
}

function strOrNull(value: unknown): string | null {
  return typeof value === 'string' && value ? value : null;
}

function coerceSource(raw: unknown): AcquisitionSourceReport | null {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const blob = raw as Record<string, unknown>;
  const id = strOrNull(blob.id);
  if (!id) return null;
  const window =
    blob.window && typeof blob.window === 'object' && !Array.isArray(blob.window)
      ? (blob.window as Record<string, unknown>)
      : null;
  return {
    id,
    label: strOrNull(blob.label) ?? id,
    windowFrom: window ? strOrNull(window.from) : null,
    windowTo: window ? strOrNull(window.to) : null,
    rows: typeof blob.rows === 'number' && Number.isFinite(blob.rows) ? blob.rows : null,
    file: strOrNull(blob.file),
    // Only the producer's own `true` is complete. Anything else — including a
    // missing flag — reads PARTIAL: completeness is never rounded up.
    complete: blob.complete === true,
    stoppedReason: strOrNull(blob.stoppedReason),
    licence: strOrNull(blob.licence),
    attribution: strOrNull(blob.attribution),
  };
}

/** Narrow an unknown manifest blob to a renderable manifest, or null. */
export function coerceAcquisitionManifest(raw: unknown): AcquisitionManifest | null {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const blob = raw as Record<string, unknown>;
  if (!Array.isArray(blob.sources)) return null;
  const sources = blob.sources
    .map(coerceSource)
    .filter((source): source is AcquisitionSourceReport => source !== null);
  if (sources.length === 0) return null;
  return {
    purpose: strOrNull(blob.purpose),
    collectedAt: strOrNull(blob.collectedAt),
    sources,
  };
}
