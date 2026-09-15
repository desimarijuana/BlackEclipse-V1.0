// ── Connector registry ──────────────────────────────────────────────────────
// Flat map of connector id → connector. Built-in connectors register at module
// load; operator-configured (custom REST) connectors are materialized from JDDS
// by the runtime and registered on demand.

import type { Capability, DataConnector } from "./types";

// Anchored on `globalThis` for the same reason `lib/db.ts` anchors Prisma: dev
// HMR can re-evaluate a module and leave a second, empty registry behind, so a
// connector registered by one route would be invisible to another.
const globalForConnectors = globalThis as unknown as {
  connectorRegistry: Map<string, DataConnector> | undefined;
};

const connectors: Map<string, DataConnector> =
  globalForConnectors.connectorRegistry ?? new Map<string, DataConnector>();

globalForConnectors.connectorRegistry = connectors;

/** Register (or replace) a connector. Idempotent by id. */
export function registerConnector(connector: DataConnector): void {
  connectors.set(connector.id, connector);
}

export function unregisterConnector(id: string): void {
  connectors.delete(id);
}

export function getConnector(id: string): DataConnector | undefined {
  return connectors.get(id) ?? connectors.get(`custom:${id}`);
}

export function listConnectors(): DataConnector[] {
  return [...connectors.values()];
}

/** Every connector that declares the capability AND is currently configured. */
export function connectorsForCapability(capability: Capability): DataConnector[] {
  return listConnectors().filter(
    (c) => c.capabilities.includes(capability) && c.isConfigured()
  );
}

/** Test seam: drop every registered connector. */
export function clearRegistry(): void {
  connectors.clear();
}

/**
 * A connector can be addressed by its raw id or its `custom:`-prefixed id.
 * Kept as a helper so callers never hand-build the prefix.
 */
export function qualifyId(id: string): string {
  return id.startsWith("custom:") ? id : `custom:${id}`;
}
