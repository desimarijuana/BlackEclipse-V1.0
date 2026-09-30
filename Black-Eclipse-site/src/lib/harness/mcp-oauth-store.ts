// ── MCP OAuth token store (Phase 6, Milestone 3) ────────────────────────────
// OAuth tokens, client registration and issuer metadata for remote MCP servers
// live ENCRYPTED at rest in JDDS under `SystemConfig.key = 'mcp_oauth_tokens_v1'`,
// using the same AES-256-GCM path as the secret vault. They are referenced by
// server id and NEVER written to `mcp-servers.json`, an event, a log, or a
// response. The only consumer is the Python runtime, over the authenticated
// read-only bridge (mcp_oauth_token_get/set/clear).
//
// If the vault cannot encrypt (no key), tokens are NOT stored in plaintext:
// saving throws, so the caller reports a hard constraint instead of a leak.

import { prisma } from "@/lib/db";
import { encryptSecret, decryptSecret, isEncryptedPayload } from "@/lib/connectors/secrets";

export const MCP_OAUTH_TOKENS_CONFIG_KEY = "mcp_oauth_tokens_v1";
const MAX_SERVERS = 200;

export interface StoredOauthToken {
  accessToken: string;
  tokenType?: string;
  refreshToken?: string;
  /** Epoch seconds when the access token expires (optional). */
  expiresAt?: number;
  scope?: string;
  clientId?: string;
  issuer?: string;
}

interface VaultRecord {
  /** serverId → encrypted JSON of StoredOauthToken. */
  tokens: Record<string, string>;
  updatedAt: string;
}

async function readVault(): Promise<VaultRecord> {
  try {
    const row = await prisma.systemConfig.findUnique({ where: { key: MCP_OAUTH_TOKENS_CONFIG_KEY } });
    if (!row?.value) return { tokens: {}, updatedAt: new Date(0).toISOString() };
    const parsed = JSON.parse(row.value) as Partial<VaultRecord>;
    return { tokens: parsed.tokens ?? {}, updatedAt: parsed.updatedAt ?? new Date(0).toISOString() };
  } catch {
    return { tokens: {}, updatedAt: new Date(0).toISOString() };
  }
}

async function writeVault(record: VaultRecord): Promise<void> {
  const value = JSON.stringify(record);
  await prisma.systemConfig.upsert({
    where: { key: MCP_OAUTH_TOKENS_CONFIG_KEY },
    update: { value },
    create: { key: MCP_OAUTH_TOKENS_CONFIG_KEY, value },
  });
}

export async function getOauthToken(serverId: string): Promise<StoredOauthToken | null> {
  if (!serverId) return null;
  const vault = await readVault();
  const payload = vault.tokens[serverId];
  if (!payload || !isEncryptedPayload(payload)) return null;
  try {
    const parsed = JSON.parse(decryptSecret(payload)) as StoredOauthToken;
    if (!parsed?.accessToken) return null;
    return parsed;
  } catch {
    return null;
  }
}

export async function saveOauthToken(serverId: string, token: StoredOauthToken): Promise<void> {
  if (!serverId) throw new Error("serverId is required");
  if (!token?.accessToken) throw new Error("accessToken is required");
  const vault = await readVault();
  if (!(serverId in vault.tokens) && Object.keys(vault.tokens).length >= MAX_SERVERS) {
    throw new Error(`At most ${MAX_SERVERS} MCP OAuth servers`);
  }
  let encrypted: string;
  try {
    encrypted = encryptSecret(JSON.stringify(token));
  } catch (err) {
    // Refuse rather than fall back to plaintext.
    throw new Error(
      `could not encrypt the OAuth token (vault key unavailable): ${err instanceof Error ? err.message : "unknown"}`
    );
  }
  vault.tokens[serverId] = encrypted;
  vault.updatedAt = new Date().toISOString();
  await writeVault(vault);
}

export async function clearOauthToken(serverId: string): Promise<boolean> {
  const vault = await readVault();
  if (!(serverId in vault.tokens)) return false;
  delete vault.tokens[serverId];
  vault.updatedAt = new Date().toISOString();
  await writeVault(vault);
  return true;
}

/** Names (server ids) with a stored token, plus expiry metadata. No values. */
export async function listOauthTokenStatus(): Promise<
  Array<{ serverId: string; expiresAt?: number; hasRefresh: boolean }>
> {
  const vault = await readVault();
  const out: Array<{ serverId: string; expiresAt?: number; hasRefresh: boolean }> = [];
  for (const serverId of Object.keys(vault.tokens).sort()) {
    try {
      const parsed = JSON.parse(decryptSecret(vault.tokens[serverId])) as StoredOauthToken;
      out.push({ serverId, expiresAt: parsed.expiresAt, hasRefresh: Boolean(parsed.refreshToken) });
    } catch {
      out.push({ serverId, hasRefresh: false });
    }
  }
  return out;
}

/** Server-only: fetch the full token for the runtime. Never browser-facing. */
export async function resolveOauthTokenForRuntime(serverId: string): Promise<StoredOauthToken | null> {
  return getOauthToken(serverId);
}
