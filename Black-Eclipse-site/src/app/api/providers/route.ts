import { NextResponse } from "next/server";
import { buildCatalog } from "@/lib/connectors/catalog";

export const dynamic = "force-dynamic";

// GET /api/providers — the browsable provider catalog grouped by category.
// Status is derived from the real environment, never guessed.
export async function GET() {
  try {
    return NextResponse.json(buildCatalog());
  } catch (err) {
    console.error("[api/providers] GET error:", err);
    return NextResponse.json({ error: "Failed to build provider catalog" }, { status: 500 });
  }
}
