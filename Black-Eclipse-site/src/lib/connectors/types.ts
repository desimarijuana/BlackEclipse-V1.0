// ── Universal Data Connector — core types ───────────────────────────────────
// A connector is a small, provider-specific adapter that can (a) be tested and
// (b) satisfy a capability request. Consumers ask for a CAPABILITY, never a
// provider; the resolver maps capability → connector.

/** Data capabilities a connector can satisfy. Not all are implemented yet. */
export type Capability =
  | "PRICE"
  | "OHLCV"
  | "QUOTE"
  | "FUNDAMENTALS"
  | "NEWS"
  | "MACRO"
  | "CUSTOM_DATASET";

/** Authentication schemes supported by the custom REST connector. */
export type AuthScheme = "none" | "api_key" | "bearer" | "basic";

export interface AuthConfig {
  scheme: AuthScheme;
  /** Header name for `api_key` (e.g. `X-API-Key`). */
  header?: string;
  /** Decrypted server-side only; never serialized to a client. */
  secret?: string;
  username?: string;
}

/** How a fetch request is addressed. Only GET is supported in this iteration. */
export interface ConnectorRequest {
  capability: Capability;
  /** Parameter values substituted into declared `{{placeholders}}`. */
  params?: Record<string, string>;
  /** Abort/timeout override, clamped by the security layer. */
  timeoutMs?: number;
}

export type ConnectorErrorCode =
  | "unsupported_capability"
  | "missing_param"
  | "invalid_config"
  | "auth_failed"
  | "http_error"
  | "parse_error"
  | "blocked"
  | "timeout"
  | "too_large"
  | "network";

export interface ConnectorError {
  code: ConnectorErrorCode;
  message: string;
  httpStatus?: number;
}

export interface ConnectorResult<T = unknown> {
  ok: boolean;
  data?: T;
  error?: ConnectorError;
  /** Canonical provenance — server-side, not inferred by the client. */
  provenance: Provenance;
  /** Connector/provider id that produced the data. */
  source: string;
  retrievedAt: string;
  httpStatus?: number;
  latencyMs?: number;
}

/** Server-side provenance vocabulary. `UNAVAILABLE` means "no real data". */
export type Provenance = "LIVE" | "CACHED" | "HISTORICAL" | "CUSTOM" | "UNAVAILABLE";

export type HealthState = "CONNECTED" | "ERROR" | "AUTH_FAILED" | "RATE_LIMITED" | "UNAVAILABLE";

export interface HealthSnapshot {
  state: HealthState;
  lastTested?: string;
  lastSuccess?: string;
  lastError?: string;
  httpStatus?: number;
  latencyMs?: number;
}

export interface TestResult {
  ok: boolean;
  state: HealthState;
  httpStatus?: number;
  latencyMs?: number;
  /** Short, secret-free diagnostics for the UI. */
  message: string;
  /** Parsed sample payload (secrets already stripped). */
  sample?: unknown;
}

export interface DataConnector {
  readonly id: string;
  readonly name: string;
  readonly description?: string;
  readonly capabilities: Capability[];
  /** Where this connector's configuration lives (built-in vs operator-configured). */
  readonly kind: "builtin" | "custom";
  /** A connector that has no complete configuration cannot be resolved. */
  isConfigured(): boolean;
  test(params?: Record<string, string>): Promise<TestResult>;
  fetch(request: ConnectorRequest): Promise<ConnectorResult>;
}
