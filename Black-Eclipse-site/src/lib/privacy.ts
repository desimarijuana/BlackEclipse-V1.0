// Privacy mode — the ONE decision about whether a model call is allowed to leave
// this machine.
//
// WHY: BlackEclipse is a local-first workbench that can hold a portfolio, a
// journal, personal memory and document text. The single largest way that data
// leaves the machine is the model provider: OpenAI, Anthropic, Gemini, Groq and
// every other hosted endpoint receive the prompt (and therefore the user's
// conversations). "Local-only" is a real, enforceable mode, not a label.
//
//   ECLIPSE_PRIVACY unset          -> any configured provider (default)
//   ECLIPSE_PRIVACY=local-models   -> ONLY loopback base URLs / keyless local
//                                     providers. A remote provider is refused,
//                                     fail closed, before any request is sent.
//
// The authoritative enforcement is server-side in Python
// (`python/harness/models.py: build_chat_model`), because that is the chokepoint
// every agent run, job and automation passes through. The helpers here exist so
// the UI and the settings API can refuse early with a clear message instead of
// failing after a run has started.
//
// Scope: this mode governs MODEL traffic. Web search/fetch tools still contact
// their own providers unless you also disconnect the network; see
// `docs/data-and-privacy.md`.

import { isLocalBaseUrl } from "@/lib/agent/presets";

export type PrivacyMode = "off" | "local-models";

const LOCAL_MODELS_VALUES = new Set([
  "local-models",
  "local_models",
  "local",
  "local-only",
  "local_only",
  "no-cloud",
  "nocloud",
]);

export function privacyMode(env: Record<string, string | undefined> = process.env): PrivacyMode {
  const raw = (env.ECLIPSE_PRIVACY ?? "").trim().toLowerCase();
  return LOCAL_MODELS_VALUES.has(raw) ? "local-models" : "off";
}

export function localModelsOnly(env: Record<string, string | undefined> = process.env): boolean {
  return privacyMode(env) === "local-models";
}

export class PrivacyViolationError extends Error {
  readonly code = "PRIVACY_LOCAL_MODELS_ONLY";
  constructor(message: string) {
    super(message);
    this.name = "PrivacyViolationError";
  }
}

/**
 * Throw when local-only mode forbids this provider. `mock` is the built-in
 * offline provider and is always allowed.
 *
 * Call this wherever a provider config is accepted (save, test, run). It throws
 * `PrivacyViolationError` — callers should map it to a 4xx/403 with the message,
 * never silently fall back to a cloud provider.
 */
export function assertModelAllowed(
  baseUrl: string | null | undefined,
  provider: string | null | undefined,
  env: Record<string, string | undefined> = process.env,
): void {
  if (!localModelsOnly(env)) return;
  if ((provider ?? "").trim().toLowerCase() === "mock") return;
  if (baseUrl && isLocalBaseUrl(baseUrl)) return;
  throw new PrivacyViolationError(
    "Local-only privacy mode is on (ECLIPSE_PRIVACY=local-models): the configured " +
      "model provider is remote, so the request was blocked before any data left " +
      "this machine. Point the provider at a local server (Ollama / LM Studio) or " +
      "unset ECLIPSE_PRIVACY to allow cloud models.",
  );
}
