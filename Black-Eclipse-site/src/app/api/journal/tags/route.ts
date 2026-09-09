import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { prisma } from "@/lib/db";
import { getOrCreateProfile, listTags } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// GET /api/journal/tags — list tags.
export async function GET() {
  try {
    const profileId = await getOrCreateProfile();
    const tags = await listTags(profileId);
    return NextResponse.json({ tags });
  } catch (err) {
    console.error("[api/journal/tags] GET error:", err);
    return NextResponse.json({ error: "Failed to load tags" }, { status: 500 });
  }
}

// POST /api/journal/tags — create a tag.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "journal-tags");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json().catch(() => ({}));
    const profileId = await getOrCreateProfile();
    const name = typeof body.name === "string" ? body.name.trim() : "";
    if (!name) {
      return NextResponse.json({ error: "name is required" }, { status: 400 });
    }
    const tag = await prisma.tag.upsert({
      where: { profileId_name: { profileId, name } },
      update: {},
      create: { profileId, name },
    });
    return NextResponse.json({ success: true, tag });
  } catch (err) {
    console.error("[api/journal/tags] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to create tag" },
      { status: 500 }
    );
  }
}
