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
  command: string;
  args: string[];
  /** Env KEYS only; values are omitted (they never leave the runtime). */
  env: Record<string, null>;
  envKeys: string[];
  envAllowlist: string[];
  secretCount: number;
  cwd?: string | null;
  enabled: boolean;
  selectedTools: string[];
  toolEffects: Record<string, MCPEffect>;
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
  command: string;
  args: string[];
  env?: Record<string, string>;
  envAllowlist?: string[];
  cwd?: string;
  enabled: boolean;
  selectedTools: string[];
  toolEffects?: Record<string, MCPEffect>;
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
