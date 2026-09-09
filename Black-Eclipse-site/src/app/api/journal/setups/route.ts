import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { prisma } from "@/lib/db";
import { getOrCreateProfile, listSetups } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// GET /api/journal/setups — list setups.
export async function GET() {
  try {
    const profileId = await getOrCreateProfile();
    const setups = await listSetups(profileId);
    return NextResponse.json({ setups });
  } catch (err) {
    console.error("[api/journal/setups] GET error:", err);
    return NextResponse.json({ error: "Failed to load setups" }, { status: 500 });
  }
}

// POST /api/journal/setups — create a setup.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "journal-setups");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json().catch(() => ({}));
    const profileId = await getOrCreateProfile();
    const name = typeof body.name === "string" ? body.name.trim() : "";
    if (!name) {
      return NextResponse.json({ error: "name is required" }, { status: 400 });
    }
    const setup = await prisma.setup.upsert({
      where: { profileId_name: { profileId, name } },
      update: {},
      create: { profileId, name },
    });
    return NextResponse.json({ success: true, setup });
  } catch (err) {
    console.error("[api/journal/setups] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to create setup" },
      { status: 500 }
    );
  }
}
