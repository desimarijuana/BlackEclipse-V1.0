// MCP catalog types (Phase 5E) — the shapes the settings UI consumes.
//
// These mirror the runtime's `public_configs()` output. Secret env VALUES never
// cross this boundary: only `envKeys` (names) are carried, never values.

export type MCPEffect = "read" | "write" | "external_action" | "unknown";

export type MCPServerState =
  | "disabled"
  | "pending"
  | "connected"
  | "failed"
  | "closed"
  | "new"
  | "starting";

export type MCPTransport = "stdio" | "http";

export interface MCPAuthView {
  kind: "header" | "query";
  name: string;
  prefix?: string;
  /** The vault secret NAME only — never the value. */
  secretRef: string;
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
  selectedTools: string[];
  toolEffects: Record<string, MCPEffect>;
  enabledEffects: MCPEffect[];
  /** The catalog digest the operator last reviewed; activation requires a match. */
  confirmedCatalogDigest?: string | null;
  protocolVersion?: string | null;
  startupTimeoutMs?: number;
  catalogTimeoutMs?: number;
  callTimeoutMs?: number;
  outputLimitBytes?: number;
  maxConcurrency?: number;
  maxTools?: number;
  limits?: Record<string, number>;
  description?: string | null;
  // Live status merged in by the runtime.
  state: MCPServerState;
  diagnostic?: string | null;
  serverInfo?: { name?: string | null; version?: string | null } | null;
  catalogDigest?: string | null;
  registeredTools: string[];
  tools: MCPToolView[];
}

export interface MCPListResponse {
  success: boolean;
  servers: MCPServerView[];
  configured: number;
  connected: number;
  registeredTools: number;
  loadDiagnostics: Array<{ server: string; code: string; message: string }>;
}

/** The editable subset the UI posts back. Env values are write-only. */
export interface MCPServerInput {
  id: string;
  name?: string;
  transport?: MCPTransport;
  command?: string;
  args?: string[];
  url?: string;
  auth?: { kind: "header" | "query"; name: string; prefix?: string; secretRef: string };
  env?: Record<string, string>;
  envAllowlist?: string[];
  secretRefs?: Record<string, string>;
  cwd?: string;
  enabled: boolean;
  selectedTools: string[];
  toolEffects?: Record<string, MCPEffect>;
  enabledEffects?: MCPEffect[];
  startupTimeoutMs?: number;
  catalogTimeoutMs?: number;
  callTimeoutMs?: number;
  outputLimitBytes?: number;
  maxConcurrency?: number;
  maxTools?: number;
  description?: string;
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

/** A named vault secret. Values never cross this boundary — only names/hints. */
export interface MCPSecretView {
  name: string;
  configured: boolean;
  hint?: string;
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
