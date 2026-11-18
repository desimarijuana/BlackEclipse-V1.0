// ── First-run setup state (server-only) ─────────────────────────────────────
// One reader/writer for the two SystemConfig keys setup owns. Nothing else may
// invent a second onboarding or source-preference store.
//
//   onboarding_v1        completed flag + mode + audit of explicit choices
//   data_source_prefs_v1 the enforced source toggles
//
// Source prefs are read in two flavors:
//   - setupSourcePreferences(): what the wizard shows (safe defaults when unset)
//   - effectiveSourcePreferences(): what the fetchers honor (legacy behavior
//     when unset, so an upgrade never breaks live data)

import path from "node:path";
import { existsSync, rmSync } from "node:fs";
import {
  getConfig,
  setConfig,
  deleteConfig,
  getLLMConfig,
  LOCAL_KEY_SENTINEL,
} from "@/lib/settings";
import { deleteProviderKey, PROVIDER_KEYS } from "@/lib/provider-keys";
import { isLocalBaseUrl } from "@/lib/agent/presets";
import type {
  OnboardingState,
  SetupCompleteInput,
  SetupMode,
  SourceId,
  SourcePrefs,
} from "./types";
import { isSourceId, sourceById } from "./source-catalog";
import { legacySourceDefaults, safeSourceDefaults, isRestrictedSource } from "./defaults";
import { RISK_DISCLOSURE_VERSION } from "@/lib/legal/disclosure";
import {
  recordRiskAcknowledgement,
  RISK_ACK_CONFIG_KEY,
} from "@/lib/legal/acceptance";

export const ONBOARDING_CONFIG_KEY = "onboarding_v1";
export const SOURCE_PREFS_CONFIG_KEY = "data_source_prefs_v1";

/** Errors that mean "another writer holds the lock for a moment". */
const BUSY_PATTERN = /SQLITE_BUSY|database is locked|SQLITE_LOCKED|P2010|P1008|timed out/i;

export function isDatabaseBusyError(err: unknown): boolean {
  const text = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
  return BUSY_PATTERN.test(text);
}

/**
 * Turn a low-level write failure into something a person can act on. The
 * setup screen shows exactly this string, so it must never be a Prisma code.
 */
export function describeSetupWriteError(err: unknown): string {
  const text = err instanceof Error ? err.message : String(err ?? "");
  if (/SQLITE_BUSY|database is locked|SQLITE_LOCKED|P2010|P1008|timed out/i.test(text)) {
    return "Eclipse could not write its settings because the local database was busy. Close any other Eclipse window, then press Finish setup to try again.";
  }
  if (/SQLITE_READONLY|readonly database|EPERM|EACCES|access is denied|permission denied/i.test(text)) {
    return "Eclipse could not write to its data folder. Check that the folder is writable, then press Finish setup to try again.";
  }
  return text || "Could not save setup";
}

/**
 * Retry an idempotent write a few times when the database is momentarily busy.
 * Everything setup persists is an upsert keyed by `SystemConfig.key`, so a
 * retry cannot duplicate or reorder anything.
 */
async function withBusyRetry<T>(label: string, work: () => Promise<T>): Promise<T> {
  let lastError: unknown;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    try {
      return await work();
    } catch (err) {
      lastError = err;
      if (!isDatabaseBusyError(err) || attempt === 2) throw err;
      console.warn(`[setup] ${label}: database busy — retrying (${attempt + 1}/3)`);
      await new Promise((resolve) => setTimeout(resolve, 250 * (attempt + 1)));
    }
  }
  throw lastError;
}

function parseJSON<T>(raw: string | null): T | null {
  if (!raw) return null;
  try {
    return JSON.parse(raw) as T;
  } catch {
    return null;
  }
}

export async function readOnboardingState(): Promise<OnboardingState | null> {
  const parsed = parseJSON<Partial<OnboardingState>>(
    await getConfig(ONBOARDING_CONFIG_KEY),
  );
  if (!parsed || typeof parsed !== "object") return null;
  return {
    completed: parsed.completed === true,
    completedAt: typeof parsed.completedAt === "string" ? parsed.completedAt : undefined,
    mode: parsed.mode === "commercial" ? "commercial" : "personal",
    version: 1,
    aiSkipped: parsed.aiSkipped === true,
    migrated: parsed.migrated === true,
  };
}

export async function isOnboardingComplete(): Promise<boolean> {
  return (await readOnboardingState())?.completed === true;
}

export async function markOnboardingComplete(
  mode: SetupMode,
  extra: Partial<OnboardingState> = {},
): Promise<OnboardingState> {
  const state: OnboardingState = {
    completed: true,
    completedAt: new Date().toISOString(),
    mode,
    version: 1,
    ...extra,
  };
  await setConfig(ONBOARDING_CONFIG_KEY, JSON.stringify(state));
  return state;
}

/** Mark an upgraded install complete without showing the wizard. */
export async function markMigrated(): Promise<void> {
  await markOnboardingComplete("personal", { migrated: true });
}

export async function readSourcePreferences(): Promise<SourcePrefs | null> {
  const parsed = parseJSON<Partial<SourcePrefs>>(await getConfig(SOURCE_PREFS_CONFIG_KEY));
  if (!parsed || typeof parsed !== "object" || !parsed.sources) return null;
  const sources: Record<string, boolean> = {};
  for (const [id, value] of Object.entries(parsed.sources)) {
    if (isSourceId(id) && typeof value === "boolean") sources[id] = value;
  }
  return {
    version: 1,
    mode: parsed.mode === "commercial" ? "commercial" : "personal",
    sources,
    acceptedRestrictedSources: Array.isArray(parsed.acceptedRestrictedSources)
      ? parsed.acceptedRestrictedSources.filter((id): id is string => typeof id === "string")
      : [],
    updatedAt:
      typeof parsed.updatedAt === "string" ? parsed.updatedAt : new Date(0).toISOString(),
  };
}

/** What the wizard renders: safe defaults for a new install. */
export async function setupSourcePreferences(
  mode: SetupMode,
): Promise<Record<string, boolean>> {
  const saved = await readSourcePreferences();
  const base = safeSourceDefaults(mode);
  if (!saved) return base;
  return { ...base, ...saved.sources };
}

/**
 * What the fetcher layer honors. Absent prefs = legacy behavior, so an existing
 * install keeps its current data path until the user finishes (or re-runs)
 * setup.
 */
export async function effectiveSourcePreferences(): Promise<Record<string, boolean>> {
  const saved = await readSourcePreferences();
  if (!saved) return legacySourceDefaults();
  return { ...legacySourceDefaults(), ...saved.sources };
}

export async function isSourceEnabled(id: SourceId): Promise<boolean> {
  const prefs = await effectiveSourcePreferences();
  return prefs[id] !== false;
}

export interface WriteSourcePrefsInput {
  mode: SetupMode;
  sources: Record<string, boolean>;
  acceptedRestrictedSources?: string[];
}

export async function writeSourcePreferences(
  input: WriteSourcePrefsInput,
): Promise<SourcePrefs> {
  const accepted = new Set(input.acceptedRestrictedSources ?? []);
  const sources = safeSourceDefaults(input.mode);

  for (const [id, value] of Object.entries(input.sources)) {
    if (!isSourceId(id)) continue;
    if (value !== true) {
      sources[id] = false;
      continue;
    }
    const def = sourceById(id);
    // Advanced/community sources are opt-in, and a personal-only source in
    // commercial mode must be acknowledged explicitly.
    const needsAck =
      def?.tier === "advanced" ||
      (input.mode === "commercial" && isRestrictedSource(id));
    if (needsAck && !accepted.has(id)) {
      sources[id] = false;
      continue;
    }
    sources[id] = true;
  }

  const prefs: SourcePrefs = {
    version: 1,
    mode: input.mode,
    sources,
    acceptedRestrictedSources: [...accepted].filter((id) => isSourceId(id)),
    updatedAt: new Date().toISOString(),
  };
  await setConfig(SOURCE_PREFS_CONFIG_KEY, JSON.stringify(prefs));
  return prefs;
}

export async function completeOnboarding(input: SetupCompleteInput): Promise<{
  onboarding: OnboardingState;
  prefs: SourcePrefs;
}> {
  // Finishing setup requires an acceptance of the CURRENT risk notice. A stale
  // or missing acknowledgement must not be silently upgraded to "accepted".
  if (input.riskAckVersion !== RISK_DISCLOSURE_VERSION) {
    throw new Error("Please acknowledge the current risk notice before finishing setup.");
  }

  // Finishing setup is three small writes. On a first run they can briefly
  // collide with the boot-time integrity check (or a leftover Eclipse process)
  // and surface as SQLITE_BUSY, which used to fail the whole finish with a
  // database error. Retrying a settle-safe upsert is correct: all three writes
  // are idempotent, so a retry can never duplicate or corrupt anything.
  await withBusyRetry("risk acknowledgement", () => recordRiskAcknowledgement(input.mode));

  const prefs = await withBusyRetry("source preferences", () =>
    writeSourcePreferences({
      mode: input.mode,
      sources: input.sources,
      acceptedRestrictedSources: input.acceptedRestrictedSources,
    }),
  );
  const onboarding = await withBusyRetry("onboarding flag", () =>
    markOnboardingComplete(input.mode, {
      aiSkipped: input.ai?.kind === "skip",
    }),
  );
  return { onboarding, prefs };
}

// ── Reset scopes (configuration only; factory reset is a script) ────────────

export async function resetOnboarding(): Promise<void> {
  await setConfig(ONBOARDING_CONFIG_KEY, JSON.stringify({
    completed: false,
    mode: "personal",
    version: 1,
  } satisfies OnboardingState));
}

/** Clear setup + credentials, keep user data (chats, portfolio, research). */
export async function resetSetup(): Promise<void> {
  await resetOnboarding();
  await deleteConfig(SOURCE_PREFS_CONFIG_KEY);
  await deleteConfig("llm_config");
  await deleteConfig("setup_check_v1");
  // Re-running setup must re-ask for the risk acknowledgement.
  await deleteConfig(RISK_ACK_CONFIG_KEY);
  for (const def of PROVIDER_KEYS) {
    await deleteProviderKey(def.envVar);
  }
  // MCP servers are operator setup too. Delete only the config file (never a
  // directory) and only the known locations; source files are untouched.
  const mcpCandidates = new Set<string>();
  if (process.env.HARNESS_MCP_CONFIG) mcpCandidates.add(path.resolve(process.env.HARNESS_MCP_CONFIG));
  mcpCandidates.add(path.resolve(process.cwd(), "mcp-servers.json"));
  mcpCandidates.add(path.resolve(process.cwd(), "..", "mcp-servers.json"));
  mcpCandidates.add(path.resolve(process.cwd(), "..", "..", "mcp-servers.json"));
  mcpCandidates.add(path.resolve(process.cwd(), "..", "..", "..", "mcp-servers.json"));
  for (const file of mcpCandidates) {
    if (path.basename(file) !== "mcp-servers.json") continue;
    try {
      if (existsSync(file)) rmSync(file, { force: true });
    } catch {
      /* best-effort: a locked config must not fail the reset */
    }
  }
  // Reset the applied-key memory so the next boot re-reads the now-empty vault.
  // `deleteProviderKey` already removes vault-applied vars.
}

// ── AI status ──────────────────────────────────────────────────────────────

export interface AiStatus {
  provider: string;
  model: string;
  baseUrl: string;
  hasKey: boolean;
  configured: boolean;
}

export async function getAiStatus(): Promise<AiStatus> {
  const llm = await getLLMConfig();
  const hasKey = Boolean(llm.apiKey) && llm.apiKey !== LOCAL_KEY_SENTINEL;
  return {
    provider: llm.provider,
    model: llm.model,
    baseUrl: llm.baseUrl,
    hasKey,
    // `auto`/`mock` are sentinels, not a verdict: a saved local endpoint is a
    // usable chat configuration and must not read as "unconfigured".
    configured: llm.provider !== "mock" || isLocalBaseUrl(llm.baseUrl),
  };
}
