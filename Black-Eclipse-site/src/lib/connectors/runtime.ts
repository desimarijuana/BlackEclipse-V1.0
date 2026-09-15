// ── Connector runtime ───────────────────────────────────────────────────────
// Executes a capability request against the highest-precedence connector.
//
// Precedence is deterministic (see `resolver.ts`). This runtime deliberately
// does NOT chain across connectors: if the primary connector fails, the result
// is UNAVAILABLE. Cross-connector fallback is a future architectural decision
// (it changes provider semantics), not an implicit behavior of this layer.
//
// The runtime never fabricates data. Route-level demo fallbacks remain in the
// routes that already implement them.

import { getConnector, listConnectors, registerConnector, unregisterConnector } from "./registry";
import { resolvePrimary, resolveConnectors } from "./resolver";
import type { Capability, ConnectorResult, DataConnector } from "./types";
import { buildCustomRestConnector, type CustomConnectorConfig } from "./custom-rest";

export interface CapabilityRequest {
  capability: Capability;
  params?: Record<string, string>;
  /** Restrict execution to a specific connector id (used by the Test button). */
  connectorId?: string;
  timeoutMs?: number;
}

function unavailable(capability: Capability, source: string, message: string): ConnectorResult {
  return {
    ok: false,
    error: { code: "unsupported_capability", message },
    provenance: "UNAVAILABLE",
    source,
    retrievedAt: new Date().toISOString(),
  };
}

/**
 * Run a capability request. Returns real data or an UNAVAILABLE result — never
 * a fabricated payload.
 */
export async function runCapability(request: CapabilityRequest): Promise<ConnectorResult> {
  let connector: DataConnector | undefined;

  if (request.connectorId) {
    connector = getConnector(request.connectorId);
    if (!connector) {
      return unavailable(request.capability, request.connectorId, `Unknown connector: ${request.connectorId}`);
    }
  } else {
    connector = resolvePrimary({ capability: request.capability });
  }

  if (!connector) {
    return unavailable(request.capability, "none", `No connector provides ${request.capability}`);
  }

  return connector.fetch({
    capability: request.capability,
    params: request.params,
    timeoutMs: request.timeoutMs,
  });
}

/**
 * Materialize operator-configured connectors from JDDS into the registry.
 * Idempotent: re-registering replaces the previous instance for the same id.
 * Disabled connectors are removed so they cannot be resolved.
 */
export function syncCustomConnectors(configs: CustomConnectorConfig[]): void {
  const seen = new Set<string>();
  for (const config of configs) {
    const id = `custom:${config.id}`;
    seen.add(id);
    if (!config.enabled) {
      unregisterConnector(id);
      continue;
    }
    registerFromConfig(config);
  }
  for (const connector of listConnectors()) {
    if (connector.id.startsWith("custom:") && !seen.has(connector.id)) {
      unregisterConnector(connector.id);
    }
  }
}

/** Register or replace a single custom connector. Returns its connector id. */
export function registerFromConfig(config: CustomConnectorConfig): string {
  const connector = buildCustomRestConnector(config);
  registerConnector(connector);
  return connector.id;
}

/** Ids of every connector currently registered, for diagnostics/UI. */
export function registeredConnectorIds(): string[] {
  return listConnectors().map((c) => c.id);
}

/** Candidate connectors for a capability (used by the Data Sources UI). */
export function capabilityCandidates(capability: Capability): DataConnector[] {
  return resolveConnectors({ capability });
}
