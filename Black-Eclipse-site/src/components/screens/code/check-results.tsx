'use client';

// ── Check results (Phase 5, from the Phase 4 ledger) ────────────────────────
// A thin wrapper over the shared "Proof it works" panel. It NEVER prints
// "verified" for a claim the runtime marked unsupported — that decision lives in
// `claimStatusKey`, so the two can never disagree.

import { CodeVerificationPanel } from '@/components/chat/code-verification-panel';

export interface CheckResultsProps {
  verification: unknown;
}

export function CheckResults({ verification }: CheckResultsProps) {
  return <CodeVerificationPanel verification={verification} />;
}
