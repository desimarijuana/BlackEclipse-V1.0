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
  // `null` = no profile switch: the ordinary finance surface is unchanged.
  autonomy: "plan_only" | "edit_verify" | null;
  analysisEnabled: boolean;
  verdict: CodeIntentVerdict;
}

/**
 * Resolve the code profile for a chat turn, or null for an ordinary turn.
 *
 * `code_change` → `edit_verify` (write + execute, no external action).
 * `code_question` → `plan_only` (read-only).
 * `data_task` → no profile switch, analysis sandbox ON: the ordinary finance
 *   surface is unchanged and Eclipse may compute the result instead of
 *   refusing. Additive — a data task never widens the tool surface.
 * `not_code` → null: the ordinary finance surface is unchanged.
 *
 * A `code_change` or `data_task` turn also enables the analysis sandbox for
 * that turn, so Eclipse can *compute* (a drawdown, a cleaned dataset) rather
 * than only describe it.
 */
export async function resolveChatCodeProfile(
  query: string,
  history: Array<{ role: "user" | "assistant"; content: string }> = [],
): Promise<ChatCapabilityProfile | null> {
  const intent = await classifyCodeIntent(query, history);
  if (intent.verdict === "not_code") return null;

  const autonomy =
    intent.verdict === "code_change" ? "edit_verify"
    : intent.verdict === "code_question" ? "plan_only"
    : null;
  return {
    autonomy,
    analysisEnabled: intent.verdict === "code_change" || intent.verdict === "data_task",
    verdict: intent.verdict,
  };
}
