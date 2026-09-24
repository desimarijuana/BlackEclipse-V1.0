// ── MCP secret vault (Phase 5, secret references) ───────────────────────────
// Named secrets for MCP servers, stored ENCRYPTED at rest in JDDS
// (`SystemConfig.key = 'mcp_secrets_v1'`) using the existing AES-256-GCM path
// (`connectors/secrets`). This is the secure-vault alternative to writing scoped
// env values into the gitignored plaintext `mcp-servers.json`.
//
// Contract:
//   • The vault stores NAMED secrets. An MCP server config references a name,
//     never the value (`secret_refs: { ENV_KEY: secretName }`).
//   • Secret VALUES never leave this server-to-server path: the list/save/delete
//     API returns only names and metadata; the only consumer of a value is the
//     Python runtime, which fetches it over the authenticated read-only bridge
//     (`mcp_secret_resolve`) to spawn a child process.
//   • Values are never logged, never returned to a browser, never persisted in a
//     run trace/receipt.

import { prisma } from "@/lib/db";
import { encryptSecret, decryptSecret, isEncryptedPayload } from "@/lib/connectors/secrets";

export const MCP_SECRETS_CONFIG_KEY = "mcp_secrets_v1";
const MAX_SECRETS = 200;
const MAX_VALUE_LEN = 8_000;

interface VaultRecord {
  /** secretName → encrypted payload. */
  secrets: Record<string, string>;
  updatedAt: string;
}

/** Validate a secret NAME (the reference an MCP server config uses). */
export function isValidSecretName(name: string): boolean {
  return /^[A-Za-z0-9_.-]{1,64}$/.test(name);
}

async function readVault(): Promise<VaultRecord> {
  try {
    const row = await prisma.systemConfig.findUnique({ where: { key: MCP_SECRETS_CONFIG_KEY } });
    if (!row?.value) return { secrets: {}, updatedAt: new Date(0).toISOString() };
    const parsed = JSON.parse(row.value) as Partial<VaultRecord>;
    return { secrets: parsed.secrets ?? {}, updatedAt: parsed.updatedAt ?? new Date(0).toISOString() };
  } catch {
    return { secrets: {}, updatedAt: new Date(0).toISOString() };
  }
}

async function writeVault(record: VaultRecord): Promise<void> {
  const value = JSON.stringify(record);
  await prisma.systemConfig.upsert({
    where: { key: MCP_SECRETS_CONFIG_KEY },
    update: { value },
    create: { key: MCP_SECRETS_CONFIG_KEY, value },
  });
}

export interface McpSecretStatus {
  name: string;
  configured: boolean;
  /** Masked hint (last 4 chars) — never the full value. */
  hint?: string;
}

function maskHint(value: string): string {
  const v = value.trim();
  if (v.length <= 4) return "••••";
  return `••••${v.slice(-4)}`;
}

/** Names + masked hints only. The value never crosses this boundary. */
export async function listMcpSecretStatus(): Promise<McpSecretStatus[]> {
  const vault = await readVault();
  const out: McpSecretStatus[] = [];
  for (const name of Object.keys(vault.secrets).sort()) {
    let hint: string | undefined;
    try {
      const decrypted = decryptSecret(vault.secrets[name]);
      hint = maskHint(decrypted);
    } catch {
      hint = undefined; // undecryptable (wrong key) — report as configured, no hint
    }
    out.push({ name, configured: true, hint });
  }
  return out;
}

export async function saveMcpSecret(name: string, plaintext: string): Promise<void> {
  if (!isValidSecretName(name)) {
    throw new Error("Secret name must be 1–64 chars of [A-Za-z0-9_.-]");
  }
  const trimmed = plaintext.trim();
  if (!trimmed) throw new Error("Secret value must not be empty");
  if (trimmed.length > MAX_VALUE_LEN) throw new Error("Secret value is too large");
  const vault = await readVault();
  if (!(name in vault.secrets) && Object.keys(vault.secrets).length >= MAX_SECRETS) {
    throw new Error(`At most ${MAX_SECRETS} MCP secrets`);
  }
  vault.secrets[name] = encryptSecret(trimmed);
  vault.updatedAt = new Date().toISOString();
  await writeVault(vault);
}

export async function deleteMcpSecret(name: string): Promise<boolean> {
  const vault = await readVault();
  if (!(name in vault.secrets)) return false;
  delete vault.secrets[name];
  vault.updatedAt = new Date().toISOString();
  await writeVault(vault);
  return true;
}

/**
 * Resolve a secret's value. SERVER-ONLY — called by the authenticated runtime
 * bridge, never by a browser-facing route. Returns null when absent/undecryptable.
 */
export async function resolveMcpSecret(name: string): Promise<string | null> {
  if (!isValidSecretName(name)) return null;
  const vault = await readVault();
  const payload = vault.secrets[name];
  if (!payload || !isEncryptedPayload(payload)) return null;
  try {
    return decryptSecret(payload);
  } catch {
    return null;
  }
}
