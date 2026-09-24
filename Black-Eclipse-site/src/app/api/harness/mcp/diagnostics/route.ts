import { NextResponse } from "next/server";
import { getMCPDiagnostics } from "@/lib/harness/mcp-client";
import { listMcpSecretStatus } from "@/lib/harness/mcp-secrets";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/mcp/diagnostics — setup diagnostics for every server + the
// environment, with actionable recovery steps. The vault lives in TS and the
// runtime cannot see it, so the set of known secret NAMES is passed to the
// runtime, which then reports missing references honestly (names only, never
// values).
export async function GET() {
  let knownSecrets: string[] = [];
  try {
    knownSecrets = (await listMcpSecretStatus()).filter((s) => s.configured).map((s) => s.name);
  } catch {
    /* vault unavailable — the runtime reports references as unverified */
  }
  try {
    const diagnostics = await getMCPDiagnostics(knownSecrets);
    return NextResponse.json({ ...diagnostics, success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "MCP diagnostics failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
