// MCP catalog types (Phase 5E, extended Phase 6.1) — the shapes the settings UI
// consumes.
//
// These mirror the runtime's `public_configs()` output (which merges
// `MCPServerConfig.public_dict()` with live status). Secret env VALUES never
// cross this boundary: only `envKeys` (names) are carried, never values. Client
// certificate/key VALUES and a custom CA path are likewise never echoed — the
// view carries `clientCertConfigured` and a `"custom-ca"` marker only.

export type MCPEffect = "read" | "write" | "external_action" | "unknown";

// The exact state strings `MCPManager` emits. `lazy` means tools were registered
// from the on-disk cache without a live connection; `unavailable` means the
// reconnect budget was exhausted (distinct from a first-start `failed`).
export type MCPServerState =
  | "disabled"
  | "pending"
  | "connected"
  | "failed"
  | "failed_refused"
  | "closed"
  | "lazy"
  | "unavailable"
  | "new"
  | "starting";

export type MCPTransport = "stdio" | "http" | "sse";

export type MCPTrust = "full" | "untrusted";

/**
 * The two shapes the runtime accepts for `selected_tools`: the legacy exact list
 * or the `{include, exclude}` glob form (include wins over exclude; an empty
 * include selects nothing).
 */
export type MCPSelectedTools =
  | string[]
  | { include: string[]; exclude: string[] };

export interface MCPAuthView {
  kind: "header" | "query" | "oauth";
  /** Required for header/query; absent for oauth. */
  name?: string;
  prefix?: string;
  /** The vault secret NAME only — never the value. Absent for oauth. */
  secretRef?: string;
}

export interface MCPToolView {
  originalName: string;
  eclipseName: string;
  description: string;
  effect: MCPEffect;
  effectSource: string;
  selected: boolean;
  activatable: boolean;
  diagnostic?: string | null;
  /** Informational only; does NOT gate activation (e.g. a shortented call name). */
  note?: string | null;
}

/** A server's circuit-breaker state (continuation). Content-free. */
export interface MCPCircuitView {
  state: "closed" | "open" | "half_open";
  failures: number;
  threshold: number;
  lastErrorCode?: string | null;
  /** Seconds until the next HALF_OPEN probe, or null when not OPEN. */
  retryAfterSeconds?: number | null;
  trippedCount?: number;
  lastTrippedAt?: string | null;
}

/** Bounded, content-free lifecycle status for one server. */
export interface MCPLifecycleView {
  /** Connection attempts / reconnects from `RetryBudget.public()`. */
  initialAttempts?: number;
  reconnectAttempts?: number;
  exhausted?: boolean;
  lazy?: boolean;
  lazyActive?: boolean;
  cachedTools?: number;
  /** A lazy server's on-disk cache no longer matches its config; needs a connect. */
  cacheStale?: boolean;
  connected?: boolean;
  /** Discovered catalog size and how much was kept after the `maxTools` slice. */
  toolsDiscovered?: number | null;
  toolsKept?: number | null;
  toolsTruncated?: boolean;
  inFlight?: number;
  keepaliveInterval?: number | null;
  keepaliveFailures?: number;
  recycledReason?: string | null;
  lastErrorCode?: string | null;
  sampling?: Record<string, unknown>;
  interactions?: Record<string, unknown>;
  metrics?: { calls: number; errors: number; avgLatencyMs: number };
  /** Inbound-notification bookkeeping: how many catalog changes were handled. */
  catalogChanges?: number;
  lastCatalogChangeAt?: string | null;
  removedTools?: string[];
  /** Circuit breaker state for a server that connects but fails every call. */
  circuit?: MCPCircuitView;
  /**
   * The last operator-triggered Verify verdict (content-free), or null. A
   * `credentials_rejected` server is CONNECTED but its credentials do not work —
   * distinct from `endpoint_unreachable` and `server_not_connected`.
   */
  verify?: {
    code: "credentials_valid" | "credentials_rejected" | "verify_inconclusive";
    verifiedAt: string;
    tool: string;
    bounded: boolean;
    reason?: string;
    providerCode?: string;
    providerStatus?: number;
  } | null;
}

export interface MCPServerView {
  id: string;
  name?: string | null;
  transport: MCPTransport;
  command: string;
  args: string[];
  url?: string | null;
  auth?: MCPAuthView | null;
  /** Env KEYS only; values are omitted (they never leave the runtime). */
  env: Record<string, null>;
  envKeys: string[];
  envAllowlist: string[];
  /** Vault secret REFERENCES: env var name → secret name. Names only. */
  secretRefs: Record<string, string>;
  secretRefNames: string[];
  secretCount: number;
  cwd?: string | null;
  enabled: boolean;
  trust: MCPTrust;
  /** Boolean form of `is_untrusted()`; kept exactly as the runtime emits it. */
  untrusted: boolean;
  selectedTools: MCPSelectedTools;
  toolEffects: Record<string, MCPEffect>;
  /**
   * Original tool names whose write-shaped NAME the operator has explicitly
   * acknowledged as read-only. Until acknowledged, a `read` tool whose name
   * contains a write-ish token stays inert.
   */
  acknowledgedEffectMismatches: string[];
  enabledEffects: MCPEffect[];
  /** Declared MCP tools that act as native retrieval data sources (tool → dataType). */
  dataSourceTools: Record<string, string>;
  /** The catalog digest the operator last reviewed; activation requires a match. */
  confirmedCatalogDigest?: string | null;
  lazy: boolean;
  keepaliveInterval?: number | null;
  idleTimeoutSeconds?: number | null;
  maxLifetimeSeconds?: number | null;
  /** `true`/`false`, or the `"custom-ca"` marker (the path is never echoed). */
  sslVerify: boolean | "custom-ca";
  /** Whether a client certificate is configured (the value is never echoed). */
  clientCertConfigured: boolean;
  /**
   * Per-server capability toggles (`resources` / `prompts`). Distinct from
   * `tools` below, which is the discovered-tool array on `public_configs()`.
   */
  capabilityToggles: Record<string, boolean>;
  /** Optional narrowing of resource URI schemes (a subset of the global list). */
  resourceSchemes: string[];
  /** Raw operator-set bounds (what the operator configured). */
  startupTimeoutMs?: number;
  catalogTimeoutMs?: number;
  callTimeoutMs?: number;
  outputLimitBytes?: number;
  maxConcurrency?: number;
  maxTools?: number;
  /** Effective, clamped bounds actually applied at runtime. */
  limits?: Record<string, number>;
  protocolVersion?: string | null;
  description?: string | null;
  // Live status merged in by the runtime.
  state: MCPServerState;
  diagnostic?: string | null;
  serverInfo?: { name?: string | null; version?: string | null } | null;
  catalogDigest?: string | null;
  registeredTools: string[];
  /** Discovered tools with their resolved effect/selection state. */
  tools: MCPToolView[];
  /** Capabilities the live session advertises (distinct from what is enabled). */
  capabilities?: Record<string, unknown>;
  resources?: unknown[];
  prompts?: unknown[];
  lifecycle?: MCPLifecycleView;
}

export interface MCPListResponse {
  success: boolean;
  servers: MCPServerView[];
  configured: number;
  connected: number;
  registeredTools: number;
  loadDiagnostics: Array<{ server: string; code: string; message: string }>;
}

/** The editable payload the UI posts back. Env/cert values are write-only. */
export interface MCPServerInput {
  id: string;
  name?: string | null;
  transport?: MCPTransport;
  command?: string;
  args?: string[];
  url?: string | null;
  auth?: MCPAuthView | null;
  env?: Record<string, string>;
  envAllowlist?: string[];
  secretRefs?: Record<string, string>;
  cwd?: string | null;
  enabled: boolean;
  trust?: MCPTrust;
  selectedTools?: MCPSelectedTools;
  toolEffects?: Record<string, MCPEffect>;
  acknowledgedEffectMismatches?: string[];
  enabledEffects?: MCPEffect[];
  dataSourceTools?: Record<string, string>;
  confirmedCatalogDigest?: string | null;
  lazy?: boolean;
  keepaliveInterval?: number | null;
  idleTimeoutSeconds?: number | null;
  maxLifetimeSeconds?: number | null;
  sslVerify?: boolean | string;
  clientCert?: string | string[] | null;
  clientKey?: string | string[] | null;
  tools?: Record<string, boolean>;
  resourceSchemes?: string[];
  startupTimeoutMs?: number;
  catalogTimeoutMs?: number;
  callTimeoutMs?: number;
  outputLimitBytes?: number;
  maxConcurrency?: number;
  maxTools?: number;
  protocolVersion?: string | null;
  description?: string | null;
}

export interface MCPTestResult {
  success: boolean;
  state: MCPServerState;
  diagnostic?: string | null;
  protocolVersion?: string | null;
  serverInfo?: { name?: string | null; version?: string | null } | null;
  catalogDigest?: string | null;
  tools: MCPToolView[];
}

/**
 * The content-free verdict of an operator-triggered Verify call. The response
 * body is NEVER carried — only a stable code and, for a rejection, the
 * provider's own status/code.
 */
export interface MCPVerifyResult {
  success?: boolean;
  code: "credentials_valid" | "credentials_rejected" | "verify_inconclusive";
  verifiedAt: string;
  tool: string;
  bounded: boolean;
  reason?: string;
  providerCode?: string;
  providerStatus?: number;
}

/** A named vault secret. Values never cross this boundary — only names/hints. */
export interface MCPSecretView {
  name: string;
  configured: boolean;
  hint?: string;
}

/** OAuth token status for one server (no values). */
export interface MCPOauthTokenStatus {
  configured: boolean;
  expired: boolean;
  refreshFailed: boolean;
  rejected: boolean;
}

/** One pending/decided approval for an effectful MCP tool. */
export interface MCPApprovalView {
  id: string;
  serverId: string;
  tool: string;
  eclipseTool: string;
  effect: MCPEffect;
  argsDigest: string;
  status: "pending" | "approved" | "denied" | "expired";
  createdAt: string;
  expiresAt?: string | null;
  requestedByRunId?: string | null;
  decidedBy?: string | null;
  reason?: string | null;
  /** Plain-language description of the requested action. */
  actionSummary?: string | null;
  /** JSON string describing what data the action affects. */
  affectedData?: string | null;
  risk?: "high" | "low" | string | null;
}

/** A finance-relevant MCP integration (server) with plain-language setup. */
export interface MCPIntegrationView {
  id: string;
  label: string;
  purpose: string;
  category: string;
  transport: MCPTransport;
  command?: string | null;
  args: string[];
  url?: string | null;
  secret_ref?: string | null;
  secret_label?: string | null;
  requires_node: boolean;
  requires_python: boolean;
  read_tool_hints: string[];
  write_tool_hints: string[];
  community: boolean;
  verified: boolean;
  /** The date the launch values were last confirmed (never absent when verified). */
  verified_at?: string | null;
  /** The package version or doc URL the verification is against. */
  verified_against?: string | null;
  /** True when the remote endpoint uses OAuth 2.1 (a sign-in is coming). */
  oauth: boolean;
  notes: string;
}

export interface MCPWorkflowStepView {
  id: string;
  title: string;
  detail: string;
  effect: MCPEffect;
  integration?: string | null;
  native_data: boolean;
}

/** A named finance job the user recognises (not a raw tool). */
export interface MCPWorkflowView {
  id: string;
  name: string;
  summary: string;
  category: string;
  integrations: string[];
  output: string;
  requiresNativePortfolio: boolean;
  /** True when the workflow needs provisioning this agent does not have yet. */
  requiresProvisioning: boolean;
  /** Plain-language note on what is missing when requiresProvisioning. */
  provisioningNote: string;
  steps: MCPWorkflowStepView[];
  approvalSteps: string[];
}

export interface MCPDiagnosticView {
  code: string;
  status: "ok" | "warn" | "error" | "skipped";
  message: string;
  recovery: string;
}

export interface MCPServerDiagnosticsView {
  serverId: string;
  transport: MCPTransport;
  ok: boolean;
  checks: MCPDiagnosticView[];
}

export interface MCPDiagnosticsResponse {
  success: boolean;
  environment: MCPDiagnosticView[];
  servers: MCPServerDiagnosticsView[];
}

/** One package in the offline supply-chain report. */
export interface MCPSupplyChainPackage {
  package: string;
  source: "preset" | "configured";
  integrationId?: string;
  serverId?: string;
  pinned: boolean;
  verified: boolean;
  verifiedAgainst?: string | null;
  checkedAt: string;
}

/** The offline, read-only supply-chain report (`GET /mcp/supply-chain`). */
export interface MCPSupplyChainReport {
  success?: boolean;
  readOnly: boolean;
  offline: boolean;
  /** True always: this report never contacts the network. */
  offlineOnly?: boolean;
  /** True when the report does NOT reflect a live upstream check. */
  upstreamChecked?: boolean;
  /** When the report was produced (not a live freshness check). */
  generatedAt?: string;
  unavailable?: boolean;
  checkedAt: string;
  packages: MCPSupplyChainPackage[];
  unpinnedCount: number;
  note: string;
}

/** The result of `installMCPIntegration` (`POST /mcp/integrations/{id}/install`). */
export interface MCPInstallResult {
  success: boolean;
  installed: string;
  /** True when a server with this id already existed and was left unchanged. */
  alreadyInstalled?: boolean;
  reason?: string;
  config?: Record<string, unknown>;
}
