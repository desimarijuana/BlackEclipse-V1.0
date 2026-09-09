import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { prisma } from "@/lib/db";
import { getOrCreateProfile, listStrategies } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// GET /api/journal/strategies — list strategies with rules.
export async function GET() {
  try {
    const profileId = await getOrCreateProfile();
    const strategies = await listStrategies(profileId);
    return NextResponse.json({ strategies });
  } catch (err) {
    console.error("[api/journal/strategies] GET error:", err);
    return NextResponse.json({ error: "Failed to load strategies" }, { status: 500 });
  }
}

// POST /api/journal/strategies — create a strategy with rules.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "journal-strategies");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json().catch(() => ({}));
    const profileId = await getOrCreateProfile();
    const name = typeof body.name === "string" ? body.name.trim() : "";
    if (!name) {
      return NextResponse.json({ error: "name is required" }, { status: 400 });
    }
    const strategy = await prisma.strategy.create({
      data: {
        profileId,
        name,
        description: typeof body.description === "string" ? body.description : null,
        markets: Array.isArray(body.markets) ? JSON.stringify(body.markets) : "[]",
        confirmation: typeof body.confirmation === "string" ? body.confirmation : null,
        entry: typeof body.entry === "string" ? body.entry : null,
        rules: Array.isArray(body.rules)
          ? { create: body.rules.map((r: string) => ({ text: String(r) })) }
          : undefined,
      },
      include: { rules: true },
    });
    return NextResponse.json({ success: true, strategy });
  } catch (err) {
    console.error("[api/journal/strategies] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to create strategy" },
      { status: 500 }
    );
  }
}
