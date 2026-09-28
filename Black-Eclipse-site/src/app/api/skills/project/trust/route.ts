import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { trustProjectSkill, isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// POST /api/skills/project/trust — trust a project root so its skills load.
// Operator-gated server-side; the runtime re-checks by transport/token.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "skill-project-trust");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) {
    return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  }
  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const path = typeof body.path === "string" ? body.path : undefined;
    const note = typeof body.note === "string" ? body.note : undefined;
    await trustProjectSkill(path, note);
    return NextResponse.json({ success: true });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "trust failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
