import { NextResponse } from "next/server";
import { loadAgentPresets, HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/harness/agents — agent presets, authoritative in the Python runtime.
export async function GET() {
  try {
    const { agents, defaultAgentId } = await loadAgentPresets();
    return NextResponse.json({ success: true, defaultAgentId, agents });
  } catch (err) {
    const status = err instanceof HarnessRuntimeUnavailable ? 503 : 500;
    console.error("[api/harness/agents] GET error:", err);
    return NextResponse.json({ error: "Failed to load agents" }, { status });
  }
}
