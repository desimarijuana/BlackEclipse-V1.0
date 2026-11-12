import { NextResponse } from "next/server";
import { getMCPDiagnostics } from "@/lib/harness/clients/mcp-client";
import { listMcpSecretStatus } from "@/lib/harness/mcp-secrets";
import { listOauthTokenStatus } from "@/lib/harness/mcp-oauth-store";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/mcp/diagnostics — setup diagnostics for every server + the
// environment, with actionable recovery steps. The vault lives in TS and the
// runtime cannot see it, so the set of known secret NAMES and the OAuth token
// status (by server id, no values) are passed to the runtime, which then reports
// missing/expired references honestly.
export async function GET() {
  let knownSecrets: string[] = [];
  try {
    knownSecrets = (await listMcpSecretStatus()).filter((s) => s.configured).map((s) => s.name);
  } catch {
    /* vault unavailable — the runtime reports references as unverified */
  }
  let oauthTokens: Array<{ serverId: string; expiresAt?: number; hasRefresh: boolean }> = [];
  try {
    oauthTokens = await listOauthTokenStatus();
  } catch {
    /* vault unavailable — the runtime reports OAuth as unverified */
  }
  const nowSec = Math.floor(Date.now() / 1000);
  const tokenStatus: Record<string, { configured: boolean; expired: boolean; refreshFailed: boolean; rejected: boolean }> = {};
  for (const t of oauthTokens) {
    tokenStatus[t.serverId] = {
      configured: true,
      expired: typeof t.expiresAt === "number" && t.expiresAt > 0 && t.expiresAt < nowSec,
      refreshFailed: false,
      rejected: false,
    };
  }
  try {
    const diagnostics = await getMCPDiagnostics(knownSecrets, tokenStatus);
    return NextResponse.json({ ...diagnostics, success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP diagnostics failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
