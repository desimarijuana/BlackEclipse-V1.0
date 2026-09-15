import { NextResponse } from "next/server";
import { recentSourceRuns } from "@/lib/investor-eye/state";
import { listSources } from "@/lib/investor-eye/sources/registry";

export const dynamic = "force-dynamic";

// GET /api/investor-eye/health — Data Health diagnostics.
// One entry per registered source with its latest run accounting. Honest: a
// source that has never run reports no last success rather than a fake one.
export async function GET() {
  try {
    const runs = await recentSourceRuns(60);
    const sources = listSources().map((s) => {
      const sourceRuns = runs.filter((r) => r.source === s.id);
      const last = sourceRuns[0];
      const lastOk = sourceRuns.find((r) => !r.error);
      const totals = sourceRuns.reduce(
        (acc, r) => ({
          received: acc.received + r.recordsReceived,
          accepted: acc.accepted + r.recordsAccepted,
          rejected: acc.rejected + r.recordsRejected,
        }),
        { received: 0, accepted: 0, rejected: 0 },
      );
      return {
        id: s.id,
        name: s.name,
        capabilities: s.capabilities,
        requiresCredentials: s.requiresCredentials,
        state: last?.error ? "error" : last ? "healthy" : "idle",
        lastRunAt: last?.finishedAt ?? null,
        lastError: last?.error ?? null,
        lastSuccessAt: lastOk?.finishedAt ?? null,
        latencyMs: last?.durationMs ?? null,
        runCount: sourceRuns.length,
        totals,
      };
    });
    return NextResponse.json({ sources, generatedAt: new Date().toISOString() });
  } catch (err) {
    console.error("[api/investor-eye/health] error:", err);
    return NextResponse.json({ sources: [], generatedAt: new Date().toISOString() });
  }
}
