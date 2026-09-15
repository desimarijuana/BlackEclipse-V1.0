import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { rowToEvent } from "@/lib/investor-eye/state";

export const dynamic = "force-dynamic";

// GET /api/investor-eye/events/:id — one event with its entity links.
export async function GET(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  try {
    const row = await prisma.geopoliticalEvent.findFirst({
      where: { OR: [{ id }, { dedupKey: id }] },
      include: { entities: true },
    });
    if (!row) return NextResponse.json({ error: "not_found" }, { status: 404 });
    const event = rowToEvent(row);
    return NextResponse.json({
      event,
      entities: row.entities.map((e) => ({
        kind: e.kind,
        entityId: e.entityId,
        name: e.name,
        lon: e.lon ?? undefined,
        lat: e.lat ?? undefined,
      })),
    });
  } catch (err) {
    console.error("[api/investor-eye/events/:id] error:", err);
    return NextResponse.json({ error: "unavailable" }, { status: 200 });
  }
}
