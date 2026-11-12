import { NextResponse } from "next/server";
import { projectSkillStatus } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skills/project — project-local skill discovery + trust state. Read
// only; untrusted roots report names/notices, never skill contents.
export async function GET() {
  try {
    const data = await projectSkillStatus();
    return NextResponse.json({ success: true, ...data });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "project skill status failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
