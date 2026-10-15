import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getOrCreateProfile, updateJournalEntry, deleteJournalEntry } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// PATCH /api/journal/entries/[id] — update a free-form journal entry.
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "journal-entries-update");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const body = await request.json().catch(() => ({}));
    const profileId = await getOrCreateProfile();
    const data: { title?: string; body?: string } = {};
    if (typeof body.title === "string") data.title = body.title;
    if (typeof body.body === "string") data.body = body.body;
    const entry = await updateJournalEntry(profileId, id, data);
    if (!entry) return NextResponse.json({ error: "Entry not found" }, { status: 404 });
    return NextResponse.json({ success: true, entry });
  } catch (err) {
    console.error("[api/journal/entries] PATCH error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to update entry" },
      { status: 500 },
    );
  }
}

// DELETE /api/journal/entries/[id] — delete a free-form journal entry.
export async function DELETE(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "journal-entries-delete");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { id } = await params;
    const profileId = await getOrCreateProfile();
    const deleted = await deleteJournalEntry(profileId, id);
    if (!deleted) return NextResponse.json({ error: "Entry not found" }, { status: 404 });
    return NextResponse.json({ success: true });
  } catch (err) {
    console.error("[api/journal/entries] DELETE error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to delete entry" },
      { status: 500 },
    );
  }
}
