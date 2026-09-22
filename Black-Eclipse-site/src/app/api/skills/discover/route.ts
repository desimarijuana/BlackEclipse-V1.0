import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { discoverSkills } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skills/discover — deterministic discovery over discovery metadata.
// Static route: it wins over the sibling [id] dynamic segment.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "skills-discover");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const results = await discoverSkills({
      query: typeof body.query === "string" ? body.query : undefined,
      category: typeof body.category === "string" ? body.category : undefined,
      tags: Array.isArray(body.tags) ? (body.tags as string[]) : undefined,
      status: typeof body.status === "string" ? body.status : undefined,
      riskLevel: typeof body.riskLevel === "string" ? body.riskLevel : undefined,
      includeNonExecutable: body.includeNonExecutable === true,
    });
    return NextResponse.json({ success: true, results });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "discovery failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
