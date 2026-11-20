// ── Named custom LLM connections (server-only) ──────────────────────────────
// A user may have several OpenAI-compatible gateways (a company LiteLLM, a
// local vLLM, an Azure-shaped proxy). One shared `CUSTOM_LLM_API_KEY` slot
// forced them to overwrite each other. Each named connection now has:
//
//   - a stable id and display name,
//   - its own base URL/model,
//   - its own auth style (Bearer / x-api-key / api-key / a custom header),
//   - its OWN vault entry (`CUSTOM_LLM_KEY_<ID>`), never stored in this record.
//
// The record is non-secret. The key lives in the encrypted provider vault and
// is resolved through `provider-keys.ts`, so no secret ever reaches the client
// or this config row.

import { prisma } from "@/lib/db";
import { storedProviderKey } from "@/lib/provider-keys";
import { customConnectionKeyEnvVar } from "./custom-key";
import type { CustomAuthStyle } from "./custom-auth";

export { customConnectionKeyEnvVar } from "./custom-key";
export { CUSTOM_AUTH_STYLES, authForConnection } from "./custom-auth";
export type { CustomAuthStyle } from "./custom-auth";

export const CUSTOM_CONNECTIONS_CONFIG_KEY = "llm_custom_connections_v1";

export interface CustomConnection {
  id: string;
  name: string;
  baseUrl: string;
  model: string;
  authStyle: CustomAuthStyle;
  /** Used when authStyle is "header" (or to override the standard name). */
  apiKeyHeader?: string;
  /** Optional value prefix, e.g. "Token " (the key is appended). */
  apiKeyPrefix?: string;
  createdAt: string;
  updatedAt: string;
}

export interface CustomConnectionPublic extends CustomConnection {
  /** The vault env var for this connection's key (non-secret identity). */
  keyEnvVar: string;
  hasKey: boolean;
}

interface CustomConnectionStore {
  connections: CustomConnection[];
}

async function readStore(): Promise<CustomConnectionStore> {
  try {
    const row = await prisma.systemConfig.findUnique({
      where: { key: CUSTOM_CONNECTIONS_CONFIG_KEY },
    });
    if (!row?.value) return { connections: [] };
    const parsed = JSON.parse(row.value) as Partial<CustomConnectionStore>;
    if (!Array.isArray(parsed.connections)) return { connections: [] };
    return {
      connections: parsed.connections.filter(
        (c): c is CustomConnection =>
          Boolean(c) && typeof c.id === "string" && typeof c.baseUrl === "string",
      ),
    };
  } catch {
    return { connections: [] };
  }
}

async function writeStore(store: CustomConnectionStore): Promise<void> {
  await prisma.systemConfig.upsert({
    where: { key: CUSTOM_CONNECTIONS_CONFIG_KEY },
    update: { value: JSON.stringify(store) },
    create: { key: CUSTOM_CONNECTIONS_CONFIG_KEY, value: JSON.stringify(store) },
  });
}

function slugify(value: string): string {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 32);
}

function newId(name: string, existing: CustomConnection[]): string {
  const base = slugify(name) || "custom";
  for (let attempt = 0; attempt < 50; attempt += 1) {
    const suffix = Math.random().toString(36).slice(2, 8);
    const id = `${base}-${suffix}`;
    if (!existing.some((c) => c.id === id)) return id;
  }
  return `custom-${Date.now().toString(36)}`;
}

export async function listCustomConnections(): Promise<CustomConnection[]> {
  const store = await readStore();
  return store.connections;
}

/** Non-secret view for the UI. Resolves whether each vault entry holds a key. */
export async function listCustomConnectionsPublic(): Promise<CustomConnectionPublic[]> {
  const store = await readStore();
  const out: CustomConnectionPublic[] = [];
  for (const connection of store.connections) {
    const keyEnvVar = customConnectionKeyEnvVar(connection.id);
    const key = await storedProviderKey(keyEnvVar);
    out.push({ ...connection, keyEnvVar, hasKey: Boolean(key) });
  }
  return out;
}

export async function getCustomConnection(id: string | undefined): Promise<CustomConnection | null> {
  if (!id) return null;
  const store = await readStore();
  return store.connections.find((c) => c.id === id) ?? null;
}

export interface SaveCustomConnectionInput {
  /** Omit to create a new connection; include to edit one in place. */
  id?: string;
  name?: string;
  baseUrl: string;
  model: string;
  authStyle?: CustomAuthStyle;
  apiKeyHeader?: string;
  apiKeyPrefix?: string;
}

export async function saveCustomConnection(
  input: SaveCustomConnectionInput,
): Promise<CustomConnection> {
  const store = await readStore();
  const now = new Date().toISOString();
  const existingIndex = input.id
    ? store.connections.findIndex((c) => c.id === input.id)
    : -1;

  if (existingIndex >= 0) {
    const current = store.connections[existingIndex];
    const next: CustomConnection = {
      ...current,
      name: (input.name ?? current.name).trim() || current.name,
      baseUrl: input.baseUrl.trim().replace(/\/+$/, ""),
      model: input.model.trim() || current.model,
      authStyle: input.authStyle ?? current.authStyle,
      apiKeyHeader: input.apiKeyHeader?.trim() || current.apiKeyHeader,
      apiKeyPrefix: input.apiKeyPrefix ?? current.apiKeyPrefix,
      updatedAt: now,
    };
    store.connections[existingIndex] = next;
    await writeStore(store);
    return next;
  }

  const name = (input.name ?? "").trim() || "Custom connection";
  const connection: CustomConnection = {
    id: newId(name, store.connections),
    name,
    baseUrl: input.baseUrl.trim().replace(/\/+$/, ""),
    model: input.model.trim(),
    authStyle: input.authStyle ?? "bearer",
    apiKeyHeader: input.apiKeyHeader?.trim() || undefined,
    apiKeyPrefix: input.apiKeyPrefix,
    createdAt: now,
    updatedAt: now,
  };
  store.connections.push(connection);
  await writeStore(store);
  return connection;
}

export async function deleteCustomConnection(id: string): Promise<CustomConnection | null> {
  const store = await readStore();
  const index = store.connections.findIndex((c) => c.id === id);
  if (index < 0) return null;
  const [removed] = store.connections.splice(index, 1);
  await writeStore(store);
  return removed;
}
