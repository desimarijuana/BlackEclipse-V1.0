import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getOrCreateProfile } from "@/lib/journal/data";
import { deleteAttributionRule } from "@/lib/journal/broker/links";

export const dynamic = "force-dynamic";

// DELETE /api/journal/broker/rules/{id}
export async function DELETE(
  request: Request,
  ctx: { params: Promise<{ id: string }> },
) {
  const blocked = guardMutation(request, "journal-broker-rule");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await ctx.params;
    const profileId = await getOrCreateProfile();
    const deleted = await deleteAttributionRule(profileId, id);
    if (!deleted) return NextResponse.json({ error: "Rule not found" }, { status: 404 });
    return NextResponse.json({ success: true, deleted: true });
  } catch (err) {
    console.error("[api/journal/broker/rules/[id]] DELETE error:", err);
    return NextResponse.json({ error: "Failed to delete rule" }, { status: 500 });
  }
}
