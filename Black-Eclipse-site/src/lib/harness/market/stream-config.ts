// Streaming provider config for the Python market stream manager.
//
// For a KEYED provider the socket URL/token is resolved from the encrypted vault
// here (the side that owns it — `resolveProviderKey`) and handed to the
// authenticated runtime, the same trust boundary as `mcp_secret_resolve`. The
// token is never persisted or logged by Python. An absent credential is an
// honest AUTHENTICATION_FAILED. Kept out of `data-bridge.ts` so that file stays
// under its size ratchet.

import type { DataBridgeResult } from "@/lib/harness/data-bridge/data-bridge-types";
import { resolveProviderKey } from "@/lib/provider-keys";

const PROVIDERS: Record<string, { env: string; url: string; protocol: string }> = {
  finnhub: { env: "FINNHUB_API_KEY", url: "wss://ws.finnhub.io", protocol: "finnhub" },
  polygon: { env: "POLYGON_API_KEY", url: "wss://socket.polygon.io/stocks", protocol: "polygon" },
};

export async function marketStreamConfig(params: Record<string, unknown>): Promise<DataBridgeResult> {
  const provider = String(params.provider ?? "").toLowerCase();
  const spec = PROVIDERS[provider];
  if (!spec) {
    return { status: "UNAVAILABLE", failureClass: "not_covered", error: `no stream config for provider '${provider}'` };
  }
  const token = await resolveProviderKey(spec.env).catch(() => null);
  if (!token || !token.trim()) {
    return { status: "UNAVAILABLE", failureClass: "unconfigured", error: `${spec.env} is not configured` };
  }
  return { status: "OK", provider, protocol: spec.protocol, url: spec.url, token: token.trim() };
}
