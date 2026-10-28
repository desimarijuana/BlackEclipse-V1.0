// Etherscan adapter — Ethereum (and multichain) account on-chain metrics.
//
// `onchain` takes a 0x address (or ENS-style identifier already resolved
// upstream) and returns the native balance, transaction count and latest block.
// The API answers HTTP 200 with a `status: "0"` envelope on errors, so both the
// transport status and the envelope are checked. No value is invented: an
// unknown address returns UNAVAILABLE.

import { safeGet } from "@/lib/connectors/security";
import { resolveProviderKey } from "@/lib/provider-keys";
import { rateLimitFromHeaders, type RateLimitInfo } from "../rate-limit";
import { ProviderError, type MarketDataRequest, type MarketProvider } from "../types";

const BASE = process.env.ETHERSCAN_BASE || "https://api.etherscan.io/v2/api";

const CHAIN_IDS: Record<string, number> = {
  ethereum: 1, eth: 1, mainnet: 1,
  arbitrum: 42161, optimism: 10, polygon: 137, base: 8453,
  bsc: 56, avalanche: 43114,
};

async function getJson(url: string): Promise<{ data: Record<string, unknown>; rateLimit?: RateLimitInfo }> {
  const res = await safeGet({
    url,
    timeoutMs: 15000,
    maxBytes: 2 * 1024 * 1024,
    headers: { Accept: "application/json" },
  });
  const rateLimit = rateLimitFromHeaders("etherscan", res.headers);
  if (res.status === 429) throw new ProviderError("etherscan rate limited", "RATE_LIMITED", true, 429);
  if (res.status >= 400) throw new ProviderError(`etherscan HTTP ${res.status}`, "PROVIDER_UNAVAILABLE", res.status >= 500, res.status);
  let json: Record<string, unknown>;
  try {
    json = JSON.parse(res.text) as Record<string, unknown>;
  } catch {
    throw new ProviderError("etherscan parse failure", "DATA_NOT_AVAILABLE", false);
  }
  if (String(json.status) === "0") {
    const message = String(json.message ?? "");
    const result = String(json.result ?? "");
    if (/rate limit/i.test(message) || /rate limit/i.test(result)) {
      throw new ProviderError("etherscan rate limited", "RATE_LIMITED", true, 429);
    }
    if (/invalid api key/i.test(result) || /missing api key/i.test(result)) {
      throw new ProviderError("etherscan credential missing or invalid", "AUTHENTICATION_FAILED", false, 401);
    }
    throw new ProviderError(`etherscan: ${result || message || "no data"}`, "DATA_NOT_AVAILABLE", false);
  }
  return { data: json, rateLimit };
}

function weiToNative(wei: unknown): number | null {
  const text = typeof wei === "string" ? wei : typeof wei === "number" ? String(wei) : "";
  if (!/^\d+$/.test(text)) return null;
  return Number(BigInt(text) / BigInt(10 ** 12)) / 1e6;
}

function hexToInt(hex: unknown): number | null {
  const text = typeof hex === "string" ? hex : "";
  if (!/^0x[0-9a-f]+$/i.test(text)) return null;
  return Number.parseInt(text, 16);
}

async function fetchOnchain(request: MarketDataRequest): Promise<Record<string, unknown>> {
  const key = await resolveProviderKey("ETHERSCAN_API_KEY").catch(() => null);
  if (!key || !key.trim()) {
    throw new ProviderError("etherscan requires ETHERSCAN_API_KEY", "AUTHENTICATION_FAILED", false, 401);
  }
  const address = (request.address || request.symbol || "").trim();
  if (!/^0x[0-9a-fA-F]{40}$/.test(address)) {
    throw new ProviderError(`not an EVM address: ${address || "(empty)"}`, "SYMBOL_NOT_FOUND", false);
  }
  const chain = (request.chain || "ethereum").toLowerCase();
  const chainId = CHAIN_IDS[chain];
  if (!chainId) throw new ProviderError(`unsupported etherscan chain: ${chain}`, "UNSUPPORTED_CAPABILITY", false);
  const apiKey = key.trim();

  const balanceUrl = `${BASE}?chainid=${chainId}&module=account&action=balance&address=${address}&tag=latest&apikey=${encodeURIComponent(apiKey)}`;
  const txCountUrl = `${BASE}?chainid=${chainId}&module=proxy&action=eth_getTransactionCount&address=${address}&tag=latest&apikey=${encodeURIComponent(apiKey)}`;
  const blockUrl = `${BASE}?chainid=${chainId}&module=proxy&action=eth_blockNumber&apikey=${encodeURIComponent(apiKey)}`;

  const balance = await getJson(balanceUrl);
  const [txRes, blockRes] = await Promise.all([
    getJson(txCountUrl).catch(() => null),
    getJson(blockUrl).catch(() => null),
  ]);

  return {
    status: "OK",
    provider: "etherscan",
    symbol: address,
    address,
    chain,
    nativeBalance: weiToNative(balance.data.result),
    txCount: txRes ? hexToInt(txRes.data.result) : null,
    latestBlock: blockRes ? hexToInt(blockRes.data.result) : null,
    rateLimit: balance.rateLimit,
    observationTime: new Date().toISOString(),
    observationSource: "retrieval_clock",
  };
}

export const etherscanProvider: MarketProvider = {
  id: "etherscan",
  capabilityIds: ["onchain"],
  async fetch(request) {
    switch (request.capability) {
      case "onchain":
        return fetchOnchain(request);
      default:
        throw new ProviderError(`etherscan does not serve ${request.capability}`, "UNSUPPORTED_CAPABILITY", false);
    }
  },
};
