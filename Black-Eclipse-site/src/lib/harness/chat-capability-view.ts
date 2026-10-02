// ─── Chat capability VIEW contract (Phase 14) ────────────────────────────────
// Client-safe and pure: no fetch, no `child_process`, no `ensurePythonRuntime`.
// The panel and the chat transcript import this; the server-side resolution
// (`chat-capability.ts`, which calls the runtime) imports it too. Keeping the
// view types + the profile→headline mapping here is what stops a client
// component from pulling a server-only module into the browser bundle (a 500 on
// `/` that no static gate catches).

import type { TranslationKey } from "@/lib/i18n/types";

/** The turn-level capability the chat surface renders for one coding turn. */
export interface ChatCapability {
  autonomy?: string | null;
  verification?: unknown;
  /** Phase 14 §6.4: the runtime-derived view, when present, wins. */
  capability?: unknown;
}

/**
 * The ONE place a narrow profile becomes a plain headline key. The classifier's
 * verdict is never shown as a category; the user sees what Eclipse will DO. An
 * ordinary turn, or any profile chat never sends, yields null (no headline).
 */
export function headlineKey(autonomy: string | null | undefined): TranslationKey | null {
  if (autonomy === "edit_verify") return "code.chat.headline.editVerify";
  if (autonomy === "plan_only") return "code.chat.headline.planOnly";
  return null;
}

/** The runtime's Phase-14 capability view (mirror of `code/capability.py`). */
export interface ChatCapabilityView {
  kind: "code";
  profile: "plan_only" | "edit_verify";
  /** i18n key for the plain "what Eclipse will do" sentence. */
  headline: TranslationKey;
  verification?: unknown;
}

/** Narrow an unknown run field to the capability view, or null. */
export function coerceChatCapability(raw: unknown): ChatCapabilityView | null {
  if (raw === null || typeof raw !== "object") return null;
  const blob = raw as Record<string, unknown>;
  const profile = blob.profile;
  if (profile !== "plan_only" && profile !== "edit_verify") return null;
  const headline = headlineKey(profile);
  if (!headline) return null;
  return { kind: "code", profile, headline, verification: blob.verification };
}
