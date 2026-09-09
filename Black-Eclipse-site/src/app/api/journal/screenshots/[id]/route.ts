import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getOrCreateProfile, deleteTradeScreenshot } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// DELETE /api/journal/screenshots/[id] — delete a screenshot.
export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "journal-screenshots-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const profileId = await getOrCreateProfile();
    const deleted = await deleteTradeScreenshot(profileId, id);
    if (!deleted) return NextResponse.json({ error: "Screenshot not found" }, { status: 404 });
    return NextResponse.json({ success: true });
  } catch (err) {
    console.error("[api/journal/screenshots] DELETE error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to delete screenshot" },
      { status: 500 },
    );
  }
}
