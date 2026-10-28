import { NextResponse } from "next/server";
import { fetchMarketData } from "@/lib/harness/market/bridge";

export const dynamic = "force-dynamic";

const CAPABILITIES = new Set(["tvl", "liquidations", "long_short", "onchain"]);

// Small in-memory cache: these are slow-moving (TVL/liquidations update on the
// provider's cadence) and the UI polls a handful of symbols.
const TTL_MS = 30_000;
const cache = new Map<string, { t: number; body: unknown }>();

function str(value: string | null): string | undefined {
  const trimmed = value?.trim();
  return trimmed ? trimmed : undefined;
}

/**
 * GET /api/crypto/alt-data
 *
 * A thin read-only front door over the SAME market adapters the agent uses
 * (`fetchMarketData` → DefiLlama/CoinGlass/Solscan/Etherscan). It invents
 * nothing: the bridge's UNAVAILABLE envelope is returned as-is.
 */
export async function GET(request: Request) {
  const url = new URL(request.url);
  const capability = str(url.searchParams.get("capability"))?.toLowerCase() ?? "";
  if (!CAPABILITIES.has(capability)) {
    return NextResponse.json(
      { status: "UNAVAILABLE", failureClass: "invalid_request", error: `unsupported capability: ${capability || "(none)"}` },
      { status: 400 },
    );
  }

  const symbol = str(url.searchParams.get("symbol"));
  const address = str(url.searchParams.get("address"));
  if (!symbol && !address) {
    return NextResponse.json(
      { status: "UNAVAILABLE", failureClass: "invalid_request", error: "symbol or address is required" },
      { status: 400 },
    );
  }

  const params: Record<string, unknown> = {
    capability,
    // An on-chain address is case-sensitive to explorers; never upper-case it.
    symbol: capability === "onchain" ? (address ?? symbol ?? "") : (symbol ?? address ?? "").toUpperCase(),
    assetType: "crypto",
    market: "CRYPTO",
  };
  if (address) params.address = address;
  const chain = str(url.searchParams.get("chain"));
  if (chain) params.chain = chain;
  const exchange = str(url.searchParams.get("exchange"));
  if (exchange) params.exchange = exchange;
  const interval = str(url.searchParams.get("interval"));
  if (interval) params.interval = interval;
  const window = str(url.searchParams.get("window"));
  if (window) params.window = window;
  const limit = Number(url.searchParams.get("limit"));
  if (Number.isFinite(limit) && limit > 0) params.limit = Math.min(limit, 1000);

  const key = JSON.stringify(params);
  const hit = cache.get(key);
  if (hit && Date.now() - hit.t < TTL_MS) {
    return NextResponse.json(hit.body, { headers: { "x-cache": "hit" } });
  }

  try {
    const result = await fetchMarketData(params);
    cache.set(key, { t: Date.now(), body: result });
    return NextResponse.json(result, { headers: { "x-cache": "miss" } });
  } catch (error) {
    return NextResponse.json(
      { status: "UNAVAILABLE", failureClass: "no_data", error: error instanceof Error ? error.message : String(error) },
      { status: 502 },
    );
  }
}
