import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { listSkillBundles, saveSkillBundle, isOperatorRequest } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import type { SkillBundle } from "@/lib/harness/skills-types";

export const dynamic = "force-dynamic";

// GET /api/skill-bundles — list bundles + their read-only resolution.
export async function GET() {
  try {
    const data = await listSkillBundles();
    return NextResponse.json({ success: true, ...data });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "bundle list failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}

// POST /api/skill-bundles — create/update a bundle (operator-gated).
export async function POST(request: Request) {
  const blocked = guardMutation(request, "skill-bundle-save");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  if (!isOperatorRequest(request)) {
    return NextResponse.json({ error: "operator authorization required" }, { status: 403 });
  }
  try {
    const body = (await request.json().catch(() => ({}))) as Partial<SkillBundle>;
    if (!body.id) return NextResponse.json({ error: "bundle id is required" }, { status: 400 });
    const bundle = await saveSkillBundle({ ...body, id: body.id });
    return NextResponse.json({ success: true, bundle });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "bundle save failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
