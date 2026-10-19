// ── Problem-Solving & Recovery view model ────────────────────────────────────
// Shared types for the /recovery console and pure formatters/aggregators. Kept
// framework-free so they are unit-tested directly (see recovery-view.test.ts);
// the console component carries only presentation.

export interface RecoveryDecisionView {
  action: "recover" | "suspend" | "stop";
  strategy: string | null;
  reason: string;
  backoffMs: number;
  exhausted: boolean;
  requiresApproval: boolean;
  candidates?: { strategy: string; reason: string; priority: number; requiresApproval: boolean }[];
}

export interface RecoveryHypothesisView {
  cause: string;
  confidence: number;
  supporting: string[];
  contradicting: string[];
  test: string;
  repairHint: string;
}

export interface RecoveryDiagnosisView {
  kind: string;
  selected: string | null;
  confidence: number;
  decisive: boolean;
  hypotheses: RecoveryHypothesisView[];
  evidence: Record<string, unknown>;
  missingInformation: string[];
}

export interface RecoveryIncidentView {
  id: string;
  signature: string;
  kind: string;
  retryability: string;
  code: string | null;
  subsystem: string | null;
  source: string | null;
  message: string | null;
  taskId: string | null;
  runId: string | null;
  status: "open" | "resolved" | "failed" | string;
  occurrenceCount: number;
  attempts: number;
  decision: RecoveryDecisionView | null;
  diagnosis: RecoveryDiagnosisView | null;
  firstSeenAt: string;
  lastSeenAt: string;
}

export interface RecoveryAttemptView {
  id: string;
  attemptNo: number;
  action: string;
  strategy: string | null;
  outcome: string;
  reason: string;
  backoffMs: number;
  createdAt: string;
}

export interface RoutingRepairFileView {
  path: string;
  op: string;
  beforeHash: string | null;
  afterHash: string | null;
}

/** A prepared routing repair (round 4, W4): proposal + preview + landing verdict. */
export interface RoutingRepairView {
  incidentId: string;
  runId: string;
  proposal: {
    cause: string;
    kind: string;
    summary: string;
    targetFile: string | null;
    patch: { old: string; new: string } | null;
    fixture: { text: string; expectedMode: string; expectedGap: boolean };
    evidence: Record<string, unknown>;
  };
  preview: {
    filesChanged: number;
    files: RoutingRepairFileView[];
    previewDigest: string;
    added: number;
    modified: number;
    deleted: number;
  };
  landing: {
    restartRequired: boolean;
    buildRequired: boolean;
    authorities: string[];
  };
}

export interface AcquisitionStepView {
  action: string;
  description: string;
  capabilityId: string | null;
  requiresApproval: boolean;
  surface: string;
  ready: boolean;
  reason: string;
  missing: string[];
}

/** The typed acquisition lifecycle for a capability incident (W5/W9). */
export interface AcquisitionView {
  query: string;
  resolvedBy: string | null;
  steps: AcquisitionStepView[];
  requiresApproval: boolean;
  gaps: string[];
  retry: Record<string, unknown>;
}

/** True for a routing incident that has a landable repair path. */
export function isRoutingRepairIncident(incident: RecoveryIncidentView | null): boolean {
  if (!incident) return false;
  return incident.kind === "capability" ||
    (incident.code ?? "").toUpperCase() === "UI_CAPABILITY_GAP";
}

/** Count incidents per status. */
export function countByStatus(incidents: RecoveryIncidentView[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const incident of incidents) out[incident.status] = (out[incident.status] ?? 0) + 1;
  return out;
}

/** The most frequent failure kinds, descending. */
export function topKinds(incidents: RecoveryIncidentView[], limit = 5): { kind: string; count: number }[] {
  const counts = new Map<string, number>();
  for (const incident of incidents) counts.set(incident.kind, (counts.get(incident.kind) ?? 0) + 1);
  return [...counts.entries()]
    .map(([kind, count]) => ({ kind, count }))
    .sort((a, b) => b.count - a.count || a.kind.localeCompare(b.kind))
    .slice(0, Math.max(1, limit));
}

/** One-line, content-light summary for a list row. */
export function formatIncidentLine(incident: RecoveryIncidentView): string {
  const code = incident.code || "error";
  const strategy = incident.decision?.strategy ?? "n/a";
  return `${incident.kind} · ${code} · ${incident.subsystem ?? "?"} ×${incident.occurrenceCount} → ${strategy}`;
}

/** A truthful headline for a diagnosis (never presents a guess as fact). */
export function diagnosisHeadline(diagnosis: RecoveryDiagnosisView | null): string {
  if (!diagnosis) return "no diagnosis";
  if (diagnosis.decisive && diagnosis.selected) {
    return `root cause: ${diagnosis.selected} (${Math.round(diagnosis.confidence * 100)}%)`;
  }
  const gaps = diagnosis.missingInformation.length;
  return `root cause undetermined — ${gaps} evidence gap${gaps === 1 ? "" : "s"}`;
}

/** Tailwind tone for a status badge. */
export function statusTone(status: string): string {
  switch (status) {
    case "resolved":
      return "text-emerald-300";
    case "failed":
      return "text-red-300";
    case "open":
      return "text-amber-300";
    default:
      return "text-zinc-400";
  }
}