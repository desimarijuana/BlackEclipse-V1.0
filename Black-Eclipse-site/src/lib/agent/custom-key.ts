// ── Per-connection custom LLM key naming (no imports, no cycle) ─────────────
// Shared by the custom-connection store and the provider-key vault so both
// agree on the env var that holds a named connection's credential.

export const CUSTOM_CONNECTION_KEY_PREFIX = "CUSTOM_LLM_KEY_";

/** True for a per-connection vault entry (never for a fixed provider key). */
export function isCustomConnectionKeyEnvVar(envVar: string): boolean {
  return /^CUSTOM_LLM_KEY_[A-Z0-9_]+$/.test(envVar);
}

/** The stable vault env var for a named custom connection. */
export function customConnectionKeyEnvVar(id: string): string {
  return `${CUSTOM_CONNECTION_KEY_PREFIX}${id.replace(/[^a-zA-Z0-9]/g, "_").toUpperCase()}`;
}
