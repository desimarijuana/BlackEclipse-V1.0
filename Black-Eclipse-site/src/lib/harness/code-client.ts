// ─── Code-verification wire types (Phase 4) ─────────────────────────────────
// Thin, read-only types for the runtime's `codeVerification` blob. Mirror of the
// Python `code/verify.py` shapes. This module holds NO agentic logic — the panel
// renders what the runtime recorded, and never upgrades an unsupported claim.

export type CheckClaimKind = "tests_pass" | "typecheck_clean" | "build_ok" | "lint_clean";

export interface CodeVerificationRecord {
  commandExecutionId: string;
  commandClass: string;
  exitCode: number;
  durationMs: number;
  outputDigest: string;
  argv: string[];
  startedAt: string;
  workspaceId: string | null;
}

export interface CodeVerificationClaim {
  sentence: string;
  kind: CheckClaimKind;
  matchedClasses: string[];
  supported: boolean;
  evidenceExecutionId: string | null;
  evidenceDigest: string | null;
  evidenceExitCode?: number | null;
}

export interface CodeVerificationRepair {
  status: "passed" | "unrepairable" | "budget_exhausted" | "refused" | "no_checks";
  repairAttempts: number;
  maxAttempts: number;
  failedClass: string | null;
  failedOutputDigest: string | null;
  stoppedReason: string | null;
}

export interface CodeVerification {
  runId: string;
  records: CodeVerificationRecord[];
  claims: CodeVerificationClaim[];
  unverifiedCount: number;
  repair: CodeVerificationRepair | null;
  truncated: boolean;
}

/**
 * The ONLY place a claim's status word is chosen. A claim that is not supported
 * can never be reported as verified — the panel calls this, so "verified" and an
 * unsupported claim can never coincide.
 */
export function claimStatusKey(supported: boolean): 'code.proof.verified' | 'code.proof.notChecked' {
  return supported ? 'code.proof.verified' : 'code.proof.notChecked';
}

/** Narrow an unknown run field to a CodeVerification blob, or null. */
export function coerceCodeVerification(raw: unknown): CodeVerification | null {
  if (raw === null || typeof raw !== "object") return null;
  const blob = raw as Record<string, unknown>;
  const records = Array.isArray(blob.records) ? (blob.records as CodeVerificationRecord[]) : [];
  const claims = Array.isArray(blob.claims) ? (blob.claims as CodeVerificationClaim[]) : [];
  if (records.length === 0 && claims.length === 0 && !blob.repair) return null;
  return {
    runId: String(blob.runId ?? ""),
    records,
    claims,
    unverifiedCount: Number(blob.unverifiedCount ?? 0),
    repair: (blob.repair as CodeVerificationRepair | null) ?? null,
    truncated: Boolean(blob.truncated),
  };
}
