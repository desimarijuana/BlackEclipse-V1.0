import { NextResponse } from "next/server";
import { bundleUpdatePreview } from "@/lib/harness/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skill-bundles/:id/update-preview — what would change on re-lock.
// Read-only: never mutates, never enables a skill.
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  const { id } = await params;
  try {
    return NextResponse.json({ success: true, ...(await bundleUpdatePreview(id)) });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "update preview failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
