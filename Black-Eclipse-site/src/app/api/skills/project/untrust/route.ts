import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { untrustProjectSkill, isOperatorRequest } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skills/project/untrust — revoke project trust. Its skills stop
// being injected on the next load.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "skill-project-untrust");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) {
    return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  }
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const path = typeof body.path === "string" ? body.path : undefined;
    await untrustProjectSkill(path);
    return NextResponse.json({ success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "untrust failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
