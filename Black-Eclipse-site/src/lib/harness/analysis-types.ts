// ─── Analysis / computed-result wire types (Phase 8) ────────────────────────
// The computed vs retrieved distinction is STRUCTURAL. This module adds NO
// agentic logic (mirrors code-client.ts): it coerces the runtime's provenance
// blob and chooses the ONE status word, so a computed number can never be shown
// as retrieved, and a computed number with no provenance renders UNAVAILABLE.

export type ProvenanceKind = "retrieved" | "computed";

export interface Provenance {
  kind: ProvenanceKind;
  label: string;
  detail: string;
  sourceDigest?: string | null;
  citation?: string | null;
}

export interface ComputedArtifact {
  name: string;
  path: string;
  sha256: string;
  bytes: number;
  mediaType: string;
}

/** Phase 18: the figure payload that rides a computed result (never evidence). */
export interface ComputedFigure {
  kind: string;
  label: string;
  artifact: string | null;
  series: { name: string; points: number }[];
  seed: number | null;
  isEvidence: boolean;
}

export interface ComputedResult {
  status: "ok" | "failed" | "refused" | "timed_out";
  provenance: Provenance | null;
  outputs: Record<string, unknown>;
  artifacts: ComputedArtifact[];
  figure: ComputedFigure | null;
  sourceDigest?: string;
  durationMs?: number;
}

/** The ONE place a computed/retrieved status word is chosen. */
export function provenanceStatusKey(
  provenance: Provenance | null,
): 'analysis.computed' | 'analysis.retrieved' | 'analysis.unavailable' {
  if (!provenance) return 'analysis.unavailable';
  return provenance.kind === 'computed' ? 'analysis.computed' : 'analysis.retrieved';
}

/** A computed number whose provenance is absent is UNAVAILABLE — never bare. */
export function renderComputedValue(
  value: unknown,
  provenance: Provenance | null,
): { status: 'computed' | 'retrieved' | 'unavailable'; value: unknown } {
  if (!provenance) return { status: 'unavailable', value: null };
  return {
    status: provenance.kind === 'computed' ? 'computed' : 'retrieved',
    value,
  };
}

function coerceProvenance(raw: unknown): Provenance | null {
  if (raw === null || typeof raw !== 'object') return null;
  const blob = raw as Record<string, unknown>;
  const kind = blob.kind;
  if (kind !== 'computed' && kind !== 'retrieved') return null;
  if (!blob.label || !blob.detail) return null;
  return {
    kind,
    label: String(blob.label),
    detail: String(blob.detail),
    sourceDigest: (blob.sourceDigest as string | null) ?? null,
    citation: (blob.citation as string | null) ?? null,
  };
}

function coerceFigure(raw: unknown): ComputedFigure | null {
  if (raw === null || typeof raw !== 'object') return null;
  const blob = raw as Record<string, unknown>;
  const kind = typeof blob.kind === 'string' ? blob.kind : '';
  if (!kind) return null;
  const series = Array.isArray(blob.series)
    ? (blob.series as Record<string, unknown>[])
        .filter((s) => s && typeof s.name === 'string')
        .map((s) => ({ name: String(s.name), points: Number(s.points) || 0 }))
    : [];
  return {
    kind,
    label: typeof blob.label === 'string' ? blob.label : 'computed',
    artifact: typeof blob.artifact === 'string' ? blob.artifact : null,
    series,
    seed: typeof blob.seed === 'number' ? blob.seed : null,
    // A figure is computed, never evidence — the wire may not claim otherwise.
    isEvidence: false,
  };
}

/** Narrow an unknown tool/result blob to a ComputedResult, or null. */
export function coerceComputedResult(raw: unknown): ComputedResult | null {
  if (raw === null || typeof raw !== 'object') return null;
  const blob = raw as Record<string, unknown>;
  const status = blob.status;
  if (status !== 'ok' && status !== 'failed' && status !== 'refused' && status !== 'timed_out') {
    return null;
  }
  const outputs =
    blob.outputs && typeof blob.outputs === 'object' && !Array.isArray(blob.outputs)
      ? (blob.outputs as Record<string, unknown>)
      : {};
  const artifacts = Array.isArray(blob.artifacts) ? (blob.artifacts as ComputedArtifact[]) : [];
  return {
    status,
    provenance: coerceProvenance(blob.provenance),
    outputs,
    artifacts,
    figure: coerceFigure(blob.figure),
    sourceDigest: typeof blob.sourceDigest === 'string' ? blob.sourceDigest : undefined,
    durationMs: typeof blob.durationMs === 'number' ? blob.durationMs : undefined,
  };
}
