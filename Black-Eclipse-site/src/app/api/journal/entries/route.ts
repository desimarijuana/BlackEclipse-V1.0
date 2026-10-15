import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getOrCreateProfile, listJournalEntries, createJournalEntry } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// GET /api/journal/entries — list free-form journal entries.
export async function GET() {
  try {
    const profileId = await getOrCreateProfile();
    const entries = await listJournalEntries(profileId);
    return NextResponse.json({ entries });
  } catch (err) {
    console.error("[api/journal/entries] GET error:", err);
    return NextResponse.json({ error: "Failed to load entries" }, { status: 500 });
  }
}

// POST /api/journal/entries — create a free-form journal entry.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "journal-entries");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json().catch(() => ({}));
    const title = typeof body.title === "string" ? body.title.trim() : "";
    const content = typeof body.body === "string" ? body.body : "";
    if (!title && !content) {
      return NextResponse.json({ error: "title or body is required" }, { status: 400 });
    }
    const profileId = await getOrCreateProfile();
    const entry = await createJournalEntry(profileId, { title: title || "Untitled", body: content });
    return NextResponse.json({ success: true, entry });
  } catch (err) {
    console.error("[api/journal/entries] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to create entry" },
      { status: 500 },
    );
  }
}
