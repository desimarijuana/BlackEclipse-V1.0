// Solscan adapter — Solana account on-chain metrics.
//
// Verified against the Solscan Pro API V2 docs (2026-10): GET
// `/v2.0/account/detail?address=…` with a `token` header, a
// `{ success, data | errors }` envelope, and lamports as the native balance.
// A Solana address is NOT an EVM address, so this adapter never claims an EVM
// account; a malformed address is refused before any call.

import { safeGet } from "@/lib/connectors/security";
import { resolveProviderKey } from "@/lib/provider-keys";
import { rateLimitFromHeaders, type RateLimitInfo } from "../rate-limit";
import { ProviderError, type MarketDataRequest, type MarketProvider } from "../types";

const BASE = process.env.SOLSCAN_BASE || "https://pro-api.solscan.io/v2.0";

const LAMPORTS_PER_SOL = 1_000_000_000;
const BASE58 = /^[1-9A-HJ-NP-Za-km-z]{32,44}$/;

interface SolscanEnvelope {
  success?: boolean;
  data?: Record<string, unknown>;
  errors?: { code?: number; message?: string };
}

async function fetchOnchain(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const key = await resolveProviderKey("SOLSCAN_API_KEY").catch(() => null);
  if (!key || !key.trim()) {
    throw new ProviderError("solscan requires SOLSCAN_API_KEY", "AUTHENTICATION_FAILED", false, 401);
  }
  const address = (request.address || request.symbol || "").trim();
  if (!BASE58.test(address)) {
    throw new ProviderError(`not a Solana base58 address: ${address || "(empty)"}`, "SYMBOL_NOT_FOUND", false);
  }
  const res = await safeGet({
    url: `${BASE}/account/detail?address=${encodeURIComponent(address)}`,
    timeoutMs: 12000,
    maxBytes: 2 * 1024 * 1024,
    headers: { Accept: "application/json", token: key.trim() },
  });
  const rateLimit = rateLimitFromHeaders("solscan", res.headers);
  if (res.status === 429) throw new ProviderError("solscan rate limited", "RATE_LIMITED", true, 429);
  if (res.status === 401 || res.status === 403) {
    throw new ProviderError("solscan credential rejected", "AUTHENTICATION_FAILED", false, res.status);
  }
  if (res.status >= 400) throw new ProviderError(`solscan HTTP ${res.status}`, "PROVIDER_UNAVAILABLE", res.status >= 500, res.status);
  let json: SolscanEnvelope;
  try {
    json = JSON.parse(res.text) as SolscanEnvelope;
  } catch {
    throw new ProviderError("solscan parse failure", "DATA_NOT_AVAILABLE", false);
  }
  if (!json.success || !json.data) {
    const code = json.errors?.code;
    const message = json.errors?.message ?? "no data";
    if (code === 429 || /rate/i.test(message)) throw new ProviderError("solscan rate limited", "RATE_LIMITED", true, 429);
    if (code === 401 || /token|auth/i.test(message)) throw new ProviderError(`solscan: ${message}`, "AUTHENTICATION_FAILED", false, 401);
    throw new ProviderError(`solscan: ${message}`, "DATA_NOT_AVAILABLE", false);
  }
  const lamports = typeof json.data.lamports === "number" ? json.data.lamports : null;
  return {
    status: "OK",
    provider: "solscan",
    symbol: address,
    address,
    chain: "solana",
    nativeBalance: lamports !== null ? lamports / LAMPORTS_PER_SOL : null,
    txCount: null,
    latestBlock: null,
    accountType: typeof json.data.type === "string" ? json.data.type : null,
    executable: typeof json.data.executable === "boolean" ? json.data.executable : null,
    ownerProgram: typeof json.data.owner_program === "string" ? json.data.owner_program : null,
    rateLimit,
    observationTime: new Date().toISOString(),
    observationSource: "retrieval_clock",
  };
}

export const solscanProvider: MarketProvider = {
  id: "solscan",
  capabilityIds: ["onchain"],
  async fetch(request) {
    switch (request.capability) {
      case "onchain":
        return fetchOnchain(request);
      default:
        throw new ProviderError(`solscan does not serve ${request.capability}`, "UNSUPPORTED_CAPABILITY", false);
    }
  },
};
