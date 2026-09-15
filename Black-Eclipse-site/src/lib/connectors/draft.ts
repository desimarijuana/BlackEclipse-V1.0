// ── Draft connector parsing ─────────────────────────────────────────────────
// Builds a `CustomConnectorConfig` from an unsaved wizard draft, without any
// database access. Shared by the Test route and the save route's validation so
// the two can never disagree about what a valid draft is.

import { findUndeclaredPlaceholders, type CustomConnectorConfig, type CustomParam } from "./custom-rest";
import { encryptSecret } from "./secrets";
import type { Capability } from "./types";

export const ALLOWED_CAPABILITIES: Capability[] = [
  "PRICE",
  "OHLCV",
  "QUOTE",
  "FUNDAMENTALS",
  "NEWS",
  "MACRO",
  "CUSTOM_DATASET",
];

export const AUTH_SCHEMES = ["none", "api_key", "bearer", "basic"] as const;

export interface TestInput {
  name?: unknown;
  baseUrl?: unknown;
  path?: unknown;
  capabilities?: unknown;
  params?: unknown;
  headers?: unknown;
  auth?: unknown;
  secret?: unknown;
  enabled?: unknown;
}

export type DraftResult =
  | { ok: true; config: CustomConnectorConfig }
  | { ok: false; error: string };

function asString(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

/**
 * Validate a draft into a connector config. The returned config carries an
 * ENCRYPTED secret, so it is safe to hand to the runtime but never to send back
 * to a client.
 */
export function configFromDraft(input: TestInput, draftId = "draft"): DraftResult {
  const name = asString(input.name).trim();
  if (!name) return { ok: false, error: "Name is required" };

  const baseUrl = asString(input.baseUrl);
  if (!baseUrl) return { ok: false, error: "Base URL is required" };
  let parsed: URL;
  try {
    parsed = new URL(baseUrl);
  } catch {
    return { ok: false, error: "Base URL is not a valid URL" };
  }
  if (parsed.protocol !== "https:") return { ok: false, error: "Base URL must use https" };

  const path = asString(input.path, "/") || "/";

  const capabilities = Array.isArray(input.capabilities)
    ? (input.capabilities as unknown[]).filter((c): c is Capability =>
        ALLOWED_CAPABILITIES.includes(c as Capability)
      )
    : [];
  if (capabilities.length === 0) return { ok: false, error: "Select at least one capability" };

  const params: CustomParam[] = Array.isArray(input.params)
    ? (input.params as unknown[])
        .filter((p): p is Record<string, unknown> => Boolean(p) && typeof p === "object")
        .map((p) => ({
          name: asString(p.name),
          value: asString(p.value),
          required: Boolean(p.required),
        }))
        .filter((p) => p.name !== "")
    : [];

  const headers: Record<string, string> = {};
  if (input.headers && typeof input.headers === "object") {
    for (const [key, value] of Object.entries(input.headers as Record<string, unknown>)) {
      if (typeof value === "string") headers[key] = value;
    }
  }

  const authShape = (input.auth && typeof input.auth === "object" ? input.auth : {}) as Record<string, unknown>;
  const scheme = AUTH_SCHEMES.includes(authShape.scheme as (typeof AUTH_SCHEMES)[number])
    ? (authShape.scheme as (typeof AUTH_SCHEMES)[number])
    : "none";

  const secret = asString(input.secret);

  const config: CustomConnectorConfig = {
    id: draftId,
    name,
    baseUrl,
    path,
    capabilities,
    params,
    headers,
    auth: {
      scheme,
      header: asString(authShape.header) || undefined,
      username: asString(authShape.username) || undefined,
    },
    authSecretEncrypted: secret ? encryptSecret(secret) : undefined,
    enabled: true,
  };

  const undeclared = findUndeclaredPlaceholders(config);
  if (undeclared.length > 0) {
    return { ok: false, error: `Undeclared template variables: ${undeclared.join(", ")}` };
  }

  return { ok: true, config };
}
