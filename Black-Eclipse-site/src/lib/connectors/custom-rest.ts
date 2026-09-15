// ── Custom REST connector ───────────────────────────────────────────────────
// The operator-facing connector: a declarative REST endpoint (GET only in this
// iteration) whose response is mapped into a custom dataset.
//
// Security posture:
//   - every request goes through `safeGet` (https only, DNS-validated + pinned,
//     no redirects followed, streamed size cap, strict timeout),
//   - credentials are decrypted server-side and never returned to a client,
//   - `{{placeholders}}` are substituted only for declared parameters and are
//     always percent-encoded, so a value cannot inject extra query parameters.

import { safeGet, redactUrl, OutboundError, type SafeGetOptions, type SafeGetResult } from "./security";
import { decryptSecret } from "./secrets";
import type {
  AuthConfig,
  Capability,
  ConnectorRequest,
  ConnectorResult,
  DataConnector,
  Provenance,
  TestResult,
} from "./types";
import { stateFromStatus } from "./health";

export interface CustomParam {
  name: string;
  /** Value template — must be exactly `{{name}}` or a literal. */
  value: string;
  required?: boolean;
}

export interface CustomConnectorConfig {
  id: string;
  name: string;
  description?: string;
  baseUrl: string;
  path: string;
  capabilities: Capability[];
  params: CustomParam[];
  headers?: Record<string, string>;
  auth: AuthConfig;
  /** Encrypted payload from JDDS; decrypted only inside `fetch`/`test`. */
  authSecretEncrypted?: string;
  enabled: boolean;
}

const VALID_CAPABILITIES: Capability[] = [
  "PRICE",
  "OHLCV",
  "QUOTE",
  "FUNDAMENTALS",
  "NEWS",
  "MACRO",
  "CUSTOM_DATASET",
];

/** `{{var}}` only. Anything else is a literal and is never interpolated. */
const PLACEHOLDER = /\{\{(\w+)\}\}/g;

/**
 * Join a base pathname with a connector path, preserving the base prefix.
 *
 * `new URL(path, base)` cannot be used directly: WHATWG resolution treats a
 * leading `/` as root-relative, so base `https://api.example.com/v1` + path
 * `/quote` silently becomes `…/quote` and the `/v1` prefix is lost. This is a
 * very common API shape, so the prefix is joined explicitly.
 */
export function joinPaths(basePathname: string, connectorPath: string): string {
  const base = basePathname.replace(/\/+$/, "");
  const rest = connectorPath.replace(/^\/+/, "");
  if (!rest) return base || "/";
  return `${base}/${rest}`;
}

export class CustomRestConfigError extends Error {}

/** Header names/values must be single-line; Node would otherwise throw opaquely. */
export function validateHeaders(headers: Record<string, string>): void {
  for (const [name, value] of Object.entries(headers)) {
    if (/[\r\n]/.test(name) || /[\r\n]/.test(value)) {
      throw new CustomRestConfigError(`Header "${name}" contains a line break`);
    }
    if (name.trim() === "") throw new CustomRestConfigError("Header name cannot be empty");
  }
}

function assertAbsoluteHttps(baseUrl: string): URL {
  let url: URL;
  try {
    url = new URL(baseUrl);
  } catch {
    throw new CustomRestConfigError("Base URL is not a valid URL");
  }
  if (url.protocol !== "https:") {
    throw new CustomRestConfigError("Base URL must use https");
  }
  return url;
}

/**
 * Build the request URL. Declared params are appended to the query string with
 * `URLSearchParams`, which percent-encodes values. Placeholders inside the path
 * are also encoded with `encodeURIComponent`.
 */
export function buildRequestUrl(
  config: Pick<CustomConnectorConfig, "baseUrl" | "path" | "params">,
  values: Record<string, string>
): string {
  const base = assertAbsoluteHttps(config.baseUrl);
  // Path may contain {{placeholders}}; substitute with encoded values.
  const substituted = config.path.replace(PLACEHOLDER, (_m, key: string) => encodeURIComponent(values[key] ?? ""));
  const path = joinPaths(base.pathname, substituted);
  const url = new URL(path, base.origin);

  // Seed with any query string the operator put on the base URL (a common spot
  // for a query-param API key), then layer the declared params on top.
  const search = new URLSearchParams(base.search);
  for (const param of config.params) {
    const match = param.value.match(/^\{\{(\w+)\}\}$/);
    if (match) {
      const key = match[1];
      if (!(key in values)) {
        if (param.required) throw new CustomRestConfigError(`Missing required parameter: ${key}`);
        continue;
      }
      search.set(param.name, values[key]);
    } else {
      // Literal value — never interpolated from user input.
      search.set(param.name, param.value);
    }
  }
  url.search = search.toString();
  return url.toString();
}

/** Collect undeclared `{{placeholders}}` so config errors surface early. */
export function findUndeclaredPlaceholders(config: CustomConnectorConfig): string[] {
  const declared = new Set(config.params.map((p) => p.name));
  const declaredParamRefs = new Set(
    config.params
      .map((p) => p.value.match(/^\{\{(\w+)\}\}$/)?.[1])
      .filter((v): v is string => Boolean(v))
  );
  const found: string[] = [];
  const scan = (text: string) => {
    for (const match of text.matchAll(PLACEHOLDER)) {
      const key = match[1];
      if (!declared.has(key) && !declaredParamRefs.has(key)) found.push(key);
    }
  };
  scan(config.path);
  for (const value of Object.values(config.headers ?? {})) scan(value);
  return [...new Set(found)];
}

function authHeaders(auth: AuthConfig, secret?: string, username?: string): Record<string, string> {
  switch (auth.scheme) {
    case "api_key":
      return { [auth.header || "X-API-Key"]: secret ?? "" };
    case "bearer":
      return { Authorization: `Bearer ${secret ?? ""}` };
    case "basic": {
      const raw = `${username ?? ""}:${secret ?? ""}`;
      return { Authorization: `Basic ${Buffer.from(raw).toString("base64")}` };
    }
    default:
      return {};
  }
}

function classifyError(err: unknown): { state: TestResult["state"]; message: string; status?: number } {
  if (err instanceof OutboundError) {
    switch (err.code) {
      case "blocked_host":
        return { state: "ERROR", message: err.message };
      case "timeout":
        return { state: "ERROR", message: err.message };
      case "too_large":
        return { state: "ERROR", message: err.message };
      case "redirect":
        return { state: "ERROR", message: err.message };
      default:
        return { state: "ERROR", message: err.message };
    }
  }
  return { state: "ERROR", message: err instanceof Error ? err.message : String(err) };
}

/** Injectable transport so tests never touch the network. */
export type ConnectorTransport = (options: SafeGetOptions) => Promise<SafeGetResult>;

export interface CustomConnectorDeps {
  transport?: ConnectorTransport;
  /** Injectable secret decryption (tests avoid the real key file). */
  decrypt?: (payload: string) => string;
}

export function buildCustomRestConnector(config: CustomConnectorConfig, deps: CustomConnectorDeps = {}): DataConnector {
  const id = config.id.startsWith("custom:") ? config.id : `custom:${config.id}`;
  const capabilities = config.capabilities.filter((c) => VALID_CAPABILITIES.includes(c));
  const transport: ConnectorTransport = deps.transport ?? ((options) => safeGet(options));
  const decrypt = deps.decrypt ?? ((payload: string) => decryptSecret(payload));

  function resolveSecret(): string | undefined {
    if (!config.authSecretEncrypted) return undefined;
    return decrypt(config.authSecretEncrypted);
  }

  async function perform(values: Record<string, string>, timeoutMs?: number) {
    const undeclared = findUndeclaredPlaceholders(config);
    if (undeclared.length > 0) {
      throw new CustomRestConfigError(`Undeclared template variables: ${undeclared.join(", ")}`);
    }
    const url = buildRequestUrl(config, values);
    const secret = resolveSecret();
    const headers = { ...(config.headers ?? {}), ...authHeaders(config.auth, secret, config.auth.username) };
    validateHeaders(headers);
    const started = Date.now();
    const res = await transport({ url, headers, timeoutMs });
    return { res, latencyMs: Date.now() - started, url };
  }

  return {
    id,
    name: config.name,
    description: config.description,
    capabilities,
    kind: "custom",
    isConfigured() {
      if (!config.enabled) return false;
      if (capabilities.length === 0) return false;
      try {
        assertAbsoluteHttps(config.baseUrl);
      } catch {
        return false;
      }
      return true;
    },

    async test(params: Record<string, string> = {}): Promise<TestResult> {
      try {
        const { res, latencyMs } = await perform(params);
        const state = stateFromStatus(res.status);
        if (res.status < 200 || res.status >= 300) {
          return {
            ok: false,
            state,
            httpStatus: res.status,
            latencyMs,
            message: `HTTP ${res.status} from ${redactUrl(res.url)}`,
            sample: res.text.slice(0, 2000),
          };
        }
        let sample: unknown = res.text;
        let parsed = false;
        try {
          sample = JSON.parse(res.text);
          parsed = true;
        } catch {
          // Non-JSON is still a valid connection; report it honestly.
        }
        return {
          ok: true,
          state,
          httpStatus: res.status,
          latencyMs,
          message: parsed ? `Connected — JSON (${res.bytes} bytes)` : `Connected — non-JSON (${res.bytes} bytes)`,
          sample,
        };
      } catch (err) {
        const { state, message, status } = classifyError(err);
        return { ok: false, state, message, httpStatus: status };
      }
    },

    async fetch(request: ConnectorRequest): Promise<ConnectorResult> {
      const now = () => new Date().toISOString();
      if (!capabilities.includes(request.capability)) {
        return {
          ok: false,
          error: { code: "unsupported_capability", message: `${config.name} does not provide ${request.capability}` },
          provenance: "UNAVAILABLE",
          source: config.name,
          retrievedAt: now(),
        };
      }
      try {
        const { res, latencyMs } = await perform(request.params ?? {}, request.timeoutMs);
        if (res.status < 200 || res.status >= 300) {
          const code = res.status === 401 || res.status === 403 ? "auth_failed" : "http_error";
          return {
            ok: false,
            error: { code, message: `HTTP ${res.status} from ${redactUrl(res.url)}`, httpStatus: res.status },
            provenance: "UNAVAILABLE",
            source: config.name,
            retrievedAt: now(),
            httpStatus: res.status,
            latencyMs,
          };
        }
        let data: unknown;
        try {
          data = JSON.parse(res.text);
        } catch {
          return {
            ok: false,
            error: { code: "parse_error", message: "Response was not valid JSON" },
            provenance: "UNAVAILABLE",
            source: config.name,
            retrievedAt: now(),
            httpStatus: res.status,
            latencyMs,
          };
        }
        const provenance: Provenance = "LIVE";
        return {
          ok: true,
          data,
          provenance,
          source: config.name,
          retrievedAt: now(),
          httpStatus: res.status,
          latencyMs,
        };
      } catch (err) {
        const { message } = classifyError(err);
        const code =
          err instanceof CustomRestConfigError
            ? "invalid_config"
            : err instanceof OutboundError && err.code === "blocked_host"
              ? "blocked"
              : err instanceof OutboundError && err.code === "timeout"
                ? "timeout"
                : err instanceof OutboundError && err.code === "too_large"
                  ? "too_large"
                  : "network";
        return {
          ok: false,
          error: { code, message },
          provenance: "UNAVAILABLE",
          source: config.name,
          retrievedAt: now(),
        };
      }
    },
  };
}
