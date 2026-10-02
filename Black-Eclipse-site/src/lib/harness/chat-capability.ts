// ─── Chat capability resolution (Phase 14) ───────────────────────────────────
// When a chat turn is a coding request, the front door sends a narrow code
// profile with the run: an `autonomy` and (optionally) the analysis sandbox.
//
// This module is THIN by design. The classifier lives in the runtime
// (`python/harness/code/request_intent.py`, reached over `/code/intent`); this
// code calls it and assembles the payload. It does NOT re-implement the rules —
// a model's opinion, and the front door's opinion, cannot grant a capability
// (README §3.1, §3.2; ADR-H117).

import { classifyCodeIntent, type CodeIntentVerdict } from "./code-client";

// Re-export the client-safe view contract so an existing importer can keep using
// this module; the panel imports the view module directly.
export { headlineKey } from "./chat-capability-view";
export type { ChatCapability } from "./chat-capability-view";

export interface ChatCapabilityProfile {
  autonomy: "plan_only" | "edit_verify";
  analysisEnabled: boolean;
  verdict: CodeIntentVerdict;
}

/**
 * Resolve the code profile for a chat turn, or null for an ordinary turn.
 *
 * `code_change` → `edit_verify` (write + execute, no external action).
 * `code_question` → `plan_only` (read-only).
 * `not_code` → null: the ordinary finance surface is unchanged.
 *
 * A `code_change` turn also enables the analysis sandbox for that turn, so
 * Eclipse can *compute* (a drawdown, a backtest) rather than only describe it.
 * Phase 15 owns the richer quantitative classifier; this is deliberately narrow
 * — the sandbox is on only for a turn that already asked for a code change.
 */
export async function resolveChatCodeProfile(
  query: string,
  history: Array<{ role: "user" | "assistant"; content: string }> = [],
): Promise<ChatCapabilityProfile | null> {
  const intent = await classifyCodeIntent(query, history);
  if (intent.verdict === "not_code") return null;

  const autonomy = intent.verdict === "code_change" ? "edit_verify" : "plan_only";
  return {
    autonomy,
    analysisEnabled: intent.verdict === "code_change",
    verdict: intent.verdict,
  };
}
