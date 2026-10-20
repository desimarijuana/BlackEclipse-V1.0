// Generated-capability chat card types and the ONE coercion/merge seam.
// The runtime emits a bounded lifecycle view; the card never invents a build,
// test result or activation state that the runtime did not report.

export type CapabilityBuildStatus =
  | "gap"
  | "satisfied"
  | "one_off"
  | "needs_source"
  | "refused"
  | "active"
  | "tested"
  | "unverified"
  | "approval_required"
  | "handoff_required"
  | "disabled"
  | "retired";

export interface CapabilityVerificationCheck {
  name: string;
  ok: boolean;
  detail: string;
}

export interface CapabilityVerification {
  status: string;
  ok: boolean;
  checks: CapabilityVerificationCheck[];
  failed: CapabilityVerificationCheck[];
  stderr: string;
}

export interface CapabilityBuildView {
  requestId?: string;
  need?: string;
  capabilityId?: string;
  version?: string;
  kind?: string;
  title?: string;
  description?: string;
  scope?: string;
  surface?: string;
  status: CapabilityBuildStatus;
  activation?: string;
  requiresApproval?: boolean;
  nextTool?: string;
  inputs?: { name: string; kind: string; required?: boolean; description?: string }[];
  outputs?: { name: string; kind: string }[];
  tests?: string[];
  testStatus?: string;
  verification?: CapabilityVerification;
  sourceDigest?: string;
  testDigest?: string;
  dir?: string;
  reason?: string;
  steps?: string[];
  missing?: string[];
}

const STATUSES = new Set<CapabilityBuildStatus>([
  "gap", "satisfied", "one_off", "needs_source", "refused",
  "active", "tested", "unverified", "approval_required", "handoff_required",
  "disabled", "retired",
]);

export type CapabilityEventPhase =
  | "requested"
  | "built"
  | "activated"
  | "verification_failed"
  | "disabled"
  | "retired";

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function str(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function bool(value: unknown): boolean | undefined {
  return typeof value === "boolean" ? value : undefined;
}

function strings(value: unknown): string[] | undefined {
  if (!Array.isArray(value)) return undefined;
  return value.filter((item): item is string => typeof item === "string");
}

function checks(value: unknown): CapabilityVerificationCheck[] | undefined {
  if (!Array.isArray(value)) return undefined;
  const out: CapabilityVerificationCheck[] = [];
  for (const item of value) {
    if (!isRecord(item)) continue;
    const name = str(item.name);
    if (!name) continue;
    out.push({ name, ok: item.ok === true, detail: str(item.detail) ?? "" });
  }
  return out;
}

function verification(value: unknown): CapabilityVerification | undefined {
  if (!isRecord(value)) return undefined;
  return {
    status: str(value.status) ?? "",
    ok: value.ok === true,
    checks: checks(value.checks) ?? [],
    failed: checks(value.failed) ?? [],
    stderr: str(value.stderr) ?? "",
  };
}

export function coerceCapabilityBuild(value: unknown): CapabilityBuildView | undefined {
  if (!isRecord(value)) return undefined;
  const capabilityId = str(value.capabilityId);
  const need = str(value.need);
  if (!capabilityId && !need) return undefined;
  const rawStatus = str(value.status);
  const status = rawStatus && STATUSES.has(rawStatus as CapabilityBuildStatus)
    ? (rawStatus as CapabilityBuildStatus)
    : undefined;
  if (!status) return undefined;
  const inputs = Array.isArray(value.inputs)
    ? value.inputs
        .filter(isRecord)
        .map((item) => ({
          name: str(item.name) ?? "",
          kind: str(item.kind) ?? "",
          required: bool(item.required),
          description: str(item.description),
        }))
        .filter((item) => item.name.length > 0)
    : undefined;
  const outputs = Array.isArray(value.outputs)
    ? value.outputs
        .filter(isRecord)
        .map((item) => ({ name: str(item.name) ?? "", kind: str(item.kind) ?? "" }))
        .filter((item) => item.name.length > 0)
    : undefined;
  return {
    requestId: str(value.requestId),
    need,
    capabilityId,
    version: str(value.version),
    kind: str(value.kind),
    title: str(value.title),
    description: str(value.description),
    scope: str(value.scope),
    surface: str(value.surface),
    status,
    activation: str(value.activation),
    requiresApproval: bool(value.requiresApproval),
    nextTool: str(value.nextTool),
    inputs,
    outputs,
    tests: strings(value.tests),
    testStatus: str(value.testStatus),
    verification: verification(value.verification),
    sourceDigest: str(value.sourceDigest),
    testDigest: str(value.testDigest),
    dir: str(value.dir),
    reason: str(value.reason),
    steps: strings(value.steps),
    missing: strings(value.missing),
  };
}

const PHASE_STATUS: Record<CapabilityEventPhase, CapabilityBuildStatus | undefined> = {
  requested: undefined,
  built: undefined,
  activated: "active",
  verification_failed: "unverified",
  disabled: "disabled",
  retired: "retired",
};

export function mergeCapabilityBuild(
  current: CapabilityBuildView | undefined,
  raw: unknown,
  phase: CapabilityEventPhase,
): CapabilityBuildView | undefined {
  const status = PHASE_STATUS[phase] ?? current?.status ?? "gap";
  const next = coerceCapabilityBuild(raw)
    ?? (isRecord(raw) ? coerceCapabilityBuild({ ...raw, status }) : undefined);
  if (!next) return current;
  const resolvedStatus = PHASE_STATUS[phase] ?? next.status ?? current?.status ?? "gap";
  const defined = Object.fromEntries(
    Object.entries(next).filter(([, value]) => value !== undefined),
  ) as Partial<CapabilityBuildView>;
  return {
    ...(current ?? {}),
    ...defined,
    status: resolvedStatus,
    verification: next.verification
      ? {
          ...(current?.verification ?? { status: "", ok: false, checks: [], failed: [], stderr: "" }),
          ...next.verification,
          checks: next.verification.checks.length > 0
            ? next.verification.checks
            : current?.verification?.checks ?? [],
          failed: next.verification.failed.length > 0
            ? next.verification.failed
            : current?.verification?.failed ?? [],
        }
      : current?.verification,
  };
}
