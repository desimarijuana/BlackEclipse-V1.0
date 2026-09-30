// ─── MCP server view <-> draft mapping (Phase 6.1) ──────────────────────────
// The single, testable translation between the runtime's secret-free view and
// the editor's draft, and back. Extracted from the settings component so the
// round-trip contract can be proven without rendering React.
//
// The wire rule the Python side enforces:
//   absent means preserve; explicitly present means replace — including an
//   explicit `null` / `false` / `{}` / `[]` for clearing.
// So `draftToInput` always sends every field the editor owns, using explicit
// empty values to clear, while fields the editor must not touch (the catalog
// confirmation, a write-only client certificate already stored) are omitted so
// the runtime preserves them.

import type {
  MCPEffect,
  MCPServerInput,
  MCPServerView,
  MCPSelectedTools,
  MCPTransport,
  MCPTrust,
} from "./mcp-types";

/**
 * The catalog-change counters to render beside the "catalog changed" banner.
 *
 * Returns null when the runtime reported no changes (or an absent/zero count),
 * so the UI renders NO stray "0"/"—". `formattedWhen` is a short local time, or
 * null when the runtime omitted it.
 */
export function catalogChangeSummary(
  lifecycle: { catalogChanges?: number; lastCatalogChangeAt?: string | null } | undefined
): { count: number; formattedWhen: string | null } | null {
  const count = lifecycle?.catalogChanges;
  if (typeof count !== "number" || count <= 0) return null;
  const iso = lifecycle?.lastCatalogChangeAt;
  let formattedWhen: string | null = null;
  if (iso) {
    const d = new Date(iso);
    if (!Number.isNaN(d.getTime())) formattedWhen = d.toLocaleTimeString();
  }
  return { count, formattedWhen };
}

// Documented defaults, stated inline in the editor. A blank limit field means
// "use the default", which is sent explicitly as that number so a save on an
// existing server can restore the default rather than preserve an old value.
export const LIMIT_DEFAULTS = {
  startupTimeoutMs: 10_000,
  catalogTimeoutMs: 15_000,
  callTimeoutMs: 20_000,
  outputLimitBytes: 100_000,
  maxConcurrency: 4,
  maxTools: 200,
} as const;

export type SSLVerifyMode = "true" | "custom-ca" | "false";

/**
 * Tokens that suggest a tool WRITES. Mirrors `WRITE_SHAPED_TOKENS` in
 * `python/harness/mcp/naming.py`. Used only to FLAG a possible mismatch for the
 * operator to acknowledge — never to infer an effect (a name is untrusted).
 */
export const WRITE_SHAPED_TOKENS = [
  "create", "delete", "update", "patch", "move", "post", "append", "set",
  "remove", "write", "archive",
] as const;

export function writesLikeName(name: string): boolean {
  const lowered = (name ?? "").toLowerCase();
  return WRITE_SHAPED_TOKENS.some((t) => lowered.includes(t));
}

export interface DraftServer {
  id: string;
  name: string;
  transport: MCPTransport;
  command: string;
  argsText: string;
  url: string;
  authKind: "header" | "query" | "oauth";
  authName: string;
  authPrefix: string;
  authSecretRef: string;
  /** ENV_KEY=VALUE per line. A blank value means "keep the stored value". */
  envText: string;
  envKeys: string[];
  envAllowlistText: string;
  /** ENV_VAR=secretName per line — vault references, never values. */
  secretRefsText: string;
  cwd: string;
  enabled: boolean;
  trust: MCPTrust;
  /** Effect classes the operator opts in to for this server (`read` is always on). */
  enabledEffects: MCPEffect[];
  // Tool filters.
  filterMode: "list" | "include-exclude";
  selectedTools: string[];
  includeText: string;
  excludeText: string;
  // Tool effects and native data-source declarations.
  toolEffects: Record<string, MCPEffect>;
  /** Original tool names whose write-shaped NAME the operator acknowledged. */
  acknowledgedEffectMismatches: string[];
  dataSourceTools: Record<string, string>;
  /** tool=dataType per line. */
  dataSourcesText: string;
  // Capability toggles.
  resourcesEnabled: boolean;
  promptsEnabled: boolean;
  /** Comma/space-separated resource URI schemes to narrow to (empty = no narrowing). */
  resourceSchemesText: string;
  // Lifecycle.
  lazy: boolean;
  /** Live OSV advisory check at the spawn path (default true). */
  liveSupplyChainCheck: boolean;
  keepaliveIntervalText: string;
  idleTimeoutText: string;
  maxLifetimeText: string;
  // TLS.
  sslVerifyMode: SSLVerifyMode;
  /** A custom CA path (only meaningful for mode "custom-ca"). */
  sslVerifyPath: string;
  /** A combined PEM, a `[cert, key]` pair, or a `[cert, key, passphrase]` triple (one per line). */
  clientCertText: string;
  clientCertConfigured: boolean;
  /** When true, send explicit nulls to clear a stored certificate. */
  clearClientCert: boolean;
  // Limits.
  startupTimeoutText: string;
  catalogTimeoutText: string;
  callTimeoutText: string;
  outputLimitText: string;
  maxConcurrencyText: string;
  maxToolsText: string;
  protocolVersion: string;
  description: string;
}

export function emptyDraft(): DraftServer {
  return {
    id: "", name: "", transport: "stdio", command: "", argsText: "", url: "",
    authKind: "header", authName: "Authorization", authPrefix: "Bearer ", authSecretRef: "",
    envText: "", envKeys: [], envAllowlistText: "", secretRefsText: "", cwd: "",
    enabled: false, trust: "full",
    filterMode: "list", selectedTools: [], includeText: "", excludeText: "",
    enabledEffects: ["read"],
    toolEffects: {}, acknowledgedEffectMismatches: [], dataSourceTools: {}, dataSourcesText: "",
    resourcesEnabled: false, promptsEnabled: false,
    resourceSchemesText: "",
    lazy: false, liveSupplyChainCheck: true, keepaliveIntervalText: "", idleTimeoutText: "", maxLifetimeText: "",
    sslVerifyMode: "true", sslVerifyPath: "", clientCertText: "", clientCertConfigured: false,
    clearClientCert: false,
    startupTimeoutText: "", catalogTimeoutText: "", callTimeoutText: "",
    outputLimitText: "", maxConcurrencyText: "", maxToolsText: "",
    protocolVersion: "", description: "",
  };
}

/** Parse `ENV_VAR=secretName` per line into a reference map. */
export function parseRefs(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;
    const name = trimmed.slice(eq + 1).trim();
    if (name) out[trimmed.slice(0, eq).trim()] = name;
  }
  return out;
}

/** Parse a KEY=VALUE per line editor into an env map (blank value kept blank). */
export function parseEnv(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;
    out[trimmed.slice(0, eq).trim()] = trimmed.slice(eq + 1);
  }
  return out;
}

/** Parse `tool=dataType` per line into a data-source map. */
function parseDataSourceText(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const eq = trimmed.indexOf("=");
    if (eq <= 0) continue;
    const dataType = trimmed.slice(eq + 1).trim();
    if (dataType) out[trimmed.slice(0, eq).trim()] = dataType;
  }
  return out;
}

function linesToText(lines: string[]): string {
  return lines.join("\n");
}

function splitTextLines(text: string): string[] {
  return text.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
}

/** A number editor field: blank means "use the default". */
function limitText(value: number | undefined, fallback: number): string {
  if (value === undefined || value === null || value === fallback) return "";
  return String(value);
}

function limitValue(text: string, fallback: number): number {
  const trimmed = text.trim();
  if (!trimmed) return fallback;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : fallback;
}

/** A "leave blank for default" optional integer: blank => explicit null (clear). */
function optionalIntText(value: number | null | undefined): string {
  return value === null || value === undefined ? "" : String(value);
}

function optionalInt(text: string): number | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  const n = Number(trimmed);
  return Number.isFinite(n) ? n : null;
}

/** The explicit wire shape for `selectedTools` from a draft. */
export function draftSelectedTools(draft: DraftServer): MCPSelectedTools {
  if (draft.filterMode === "include-exclude") {
    return {
      include: splitTextLines(draft.includeText),
      exclude: splitTextLines(draft.excludeText),
    };
  }
  return [...draft.selectedTools];
}

/** The exact-name list a per-tool checkbox grid toggles (list form only). */
export function selectedToolNames(view: MCPServerView): string[] {
  return Array.isArray(view.selectedTools) ? [...view.selectedTools] : [];
}

/**
 * fnmatch-style glob match, mirroring the Python `resolve_selected` rule:
 * `*` matches any run, `?` matches one character. Case-sensitive, matching
 * `fnmatch.fnmatchcase`.
 */
export function matchesGlob(name: string, pattern: string): boolean {
  const escaped = pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".");
  return new RegExp(`^${escaped}$`).test(name);
}

export function matchesAnyGlob(name: string, patterns: string[]): boolean {
  return patterns.some((p) => p.trim() && matchesGlob(name, p.trim()));
}

/** Split a multi-line glob editor into trimmed, non-empty patterns. */
export function splitFilterLines(text: string): string[] {
  return text.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
}

/**
 * Resolve a tool's selection under the include/exclude rule (include wins over
 * exclude; an empty include selects nothing), mirroring the runtime's
 * `MCPServerConfig.resolve_selected`. Pure, so the editor can show the OPERATOR'S
 * dynamic filter honestly rather than freezing it into a static list.
 */
export function resolveSelectedByGlobs(
  name: string,
  include: string[],
  exclude: string[]
): boolean {
  const included = matchesAnyGlob(name, include);
  if (!included) return false;
  return !matchesAnyGlob(name, exclude);
}

/**
 * Whether a manually-selected tool is SHADOWED by the live include/exclude filter:
 * the operator checked it in the list, but the filter would not select it. The
 * editor reports this rather than showing the tool as enabled when it is not.
 */
export function isShadowedByExclude(
  name: string,
  selected: boolean,
  include: string[],
  exclude: string[]
): boolean {
  return selected && !resolveSelectedByGlobs(name, include, exclude);
}

export function draftFromServer(view: MCPServerView): DraftServer {
  const base = emptyDraft();
  const selected = view.selectedTools;
  const objectForm = !Array.isArray(selected);
  return {
    ...base,
    id: view.id,
    name: view.name ?? "",
    transport: view.transport ?? "stdio",
    command: view.command ?? "",
    argsText: linesToText(view.args ?? []),
    url: view.url ?? "",
    authKind: (view.auth?.kind ?? "header") as DraftServer["authKind"],
    authName: view.auth?.name ?? "Authorization",
    authPrefix: view.auth?.prefix ?? "Bearer ",
    authSecretRef: view.auth?.secretRef ?? "",
    // One blank line per stored key so a save keeps them unless removed.
    envText: (view.envKeys ?? []).map((k) => `${k}=`).join("\n"),
    envKeys: [...(view.envKeys ?? [])],
    envAllowlistText: (view.envAllowlist ?? []).join(" "),
    secretRefsText: Object.entries(view.secretRefs ?? {})
      .map(([envName, secretName]) => `${envName}=${secretName}`)
      .join("\n"),
    cwd: view.cwd ?? "",
    enabled: view.enabled,
    trust: view.trust ?? "full",
    enabledEffects: view.enabledEffects?.length ? [...view.enabledEffects] : ["read"],
    filterMode: objectForm ? "include-exclude" : "list",
    selectedTools: Array.isArray(selected) ? [...selected] : [],
    includeText: objectForm ? (selected.include ?? []).join("\n") : "",
    excludeText: objectForm ? (selected.exclude ?? []).join("\n") : "",
    toolEffects: { ...(view.toolEffects ?? {}) },
    acknowledgedEffectMismatches: [...(view.acknowledgedEffectMismatches ?? [])],
    dataSourceTools: { ...(view.dataSourceTools ?? {}) },
    dataSourcesText: Object.entries(view.dataSourceTools ?? {})
      .map(([tool, dataType]) => `${tool}=${dataType}`)
      .join("\n"),
    resourcesEnabled: Boolean(view.capabilityToggles?.resources),
    promptsEnabled: Boolean(view.capabilityToggles?.prompts),
    resourceSchemesText: (view.resourceSchemes ?? []).join(", "),
    lazy: view.lazy,
    liveSupplyChainCheck: view.liveSupplyChainCheck !== false,
    keepaliveIntervalText: optionalIntText(view.keepaliveInterval),
    idleTimeoutText: optionalIntText(view.idleTimeoutSeconds),
    maxLifetimeText: optionalIntText(view.maxLifetimeSeconds),
    sslVerifyMode: view.sslVerify === "custom-ca" ? "custom-ca" : view.sslVerify ? "true" : "false",
    // A stored custom CA path is never echoed; the user re-enters it only to
    // change it, otherwise leaving blank preserves the stored path.
    sslVerifyPath: "",
    clientCertText: "",
    clientCertConfigured: view.clientCertConfigured,
    clearClientCert: false,
    startupTimeoutText: limitText(view.startupTimeoutMs, LIMIT_DEFAULTS.startupTimeoutMs),
    catalogTimeoutText: limitText(view.catalogTimeoutMs, LIMIT_DEFAULTS.catalogTimeoutMs),
    callTimeoutText: limitText(view.callTimeoutMs, LIMIT_DEFAULTS.callTimeoutMs),
    outputLimitText: limitText(view.outputLimitBytes, LIMIT_DEFAULTS.outputLimitBytes),
    maxConcurrencyText: limitText(view.maxConcurrency, LIMIT_DEFAULTS.maxConcurrency),
    maxToolsText: limitText(view.maxTools, LIMIT_DEFAULTS.maxTools),
    protocolVersion: view.protocolVersion ?? "",
    description: view.description ?? "",
  };
}

export interface DraftPayload {
  server: MCPServerInput;
  envKeys: string[];
}

export function draftToInput(draft: DraftServer): DraftPayload {
  const parsedEnv = parseEnv(draft.envText);
  // A blank value ("KEY=") means "keep the stored value": it is listed as a key
  // to retain but omitted from `env`, so the runtime preserves the secret. A
  // non-empty value overwrites.
  const env: Record<string, string> = {};
  for (const [key, value] of Object.entries(parsedEnv)) {
    if (value !== "") env[key] = value;
  }
  const envKeys = Object.keys(parsedEnv);
  const allowlist = draft.envAllowlistText.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean);
  const isRemote = draft.transport === "http" || draft.transport === "sse";

  const auth = isRemote
    ? draft.authKind === "oauth"
      ? { kind: "oauth" as const }
      : draft.authSecretRef.trim()
        ? {
            kind: draft.authKind,
            name: draft.authName.trim() || "Authorization",
            prefix: draft.authPrefix || undefined,
            secretRef: draft.authSecretRef.trim(),
          }
        : undefined
    : undefined;

  const server: MCPServerInput = {
    id: draft.id.trim(),
    name: draft.name.trim() || null,
    transport: draft.transport,
    command: isRemote ? "" : draft.command.trim(),
    args: isRemote ? [] : splitTextLines(draft.argsText),
    url: isRemote ? draft.url.trim() : null,
    auth: auth ?? null,
    env,
    envAllowlist: allowlist,
    secretRefs: parseRefs(draft.secretRefsText),
    cwd: draft.cwd.trim() || null,
    enabled: draft.enabled,
    trust: draft.trust,
    selectedTools: draftSelectedTools(draft),
    toolEffects: { ...draft.toolEffects },
    acknowledgedEffectMismatches: [...draft.acknowledgedEffectMismatches],
    enabledEffects: draft.enabledEffects.length ? [...draft.enabledEffects] : ["read"],
    dataSourceTools: parseDataSourceText(draft.dataSourcesText),
    lazy: draft.lazy,
    liveSupplyChainCheck: draft.liveSupplyChainCheck,
    keepaliveInterval: optionalInt(draft.keepaliveIntervalText),
    idleTimeoutSeconds: optionalInt(draft.idleTimeoutText),
    maxLifetimeSeconds: optionalInt(draft.maxLifetimeText),
    // A custom CA path is only sent when the operator supplied one; otherwise the
    // stored value is preserved by omission.
    sslVerify:
      draft.sslVerifyMode === "true"
        ? true
        : draft.sslVerifyMode === "false"
          ? false
          : draft.sslVerifyPath.trim() || undefined,
    tools: { resources: draft.resourcesEnabled, prompts: draft.promptsEnabled },
    resourceSchemes: draft.resourceSchemesText.split(/[\s,]+/).map((s) => s.trim()).filter(Boolean),
    startupTimeoutMs: limitValue(draft.startupTimeoutText, LIMIT_DEFAULTS.startupTimeoutMs),
    catalogTimeoutMs: limitValue(draft.catalogTimeoutText, LIMIT_DEFAULTS.catalogTimeoutMs),
    callTimeoutMs: limitValue(draft.callTimeoutText, LIMIT_DEFAULTS.callTimeoutMs),
    outputLimitBytes: limitValue(draft.outputLimitText, LIMIT_DEFAULTS.outputLimitBytes),
    maxConcurrency: limitValue(draft.maxConcurrencyText, LIMIT_DEFAULTS.maxConcurrency),
    maxTools: limitValue(draft.maxToolsText, LIMIT_DEFAULTS.maxTools),
    protocolVersion: draft.protocolVersion.trim() || null,
    description: draft.description.trim() || null,
  };

  // Client certificate: never echo a stored value. Send a freshly-entered value,
  // or explicit nulls when the operator asked to clear; otherwise omit so the
  // runtime preserves whatever is stored.
  const certLines = splitTextLines(draft.clientCertText);
  if (draft.clearClientCert) {
    server.clientCert = null;
    server.clientKey = null;
  } else if (certLines.length === 1) {
    server.clientCert = certLines[0];
  } else if (certLines.length >= 2) {
    server.clientCert = certLines[0];
    server.clientKey = certLines.length >= 3 ? certLines.slice(1, 3) : certLines[1];
  }

  return { server, envKeys };
}
