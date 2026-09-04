import { NextResponse } from "next/server";
import { buildSnapshot } from "@/lib/economics/snapshot";

export const dynamic = "force-dynamic";

// In-memory SWR cache — central-bank rates and CPI prints move slowly.
const CACHE_TTL_MS = 10 * 60 * 1000;
let cache: { t: number; data: Awaited<ReturnType<typeof buildSnapshot>> } | null = null;
let rebuildInFlight = false;

function startBackgroundRebuild() {
  if (rebuildInFlight) return;
  rebuildInFlight = true;
  buildSnapshot()
    .then((data) => { cache = { t: Date.now(), data }; })
    .catch((err) => console.error("[api/economics/snapshot] background rebuild:", err))
    .finally(() => { rebuildInFlight = false; });
}

// GET /api/economics/snapshot — key central-bank rates + key prints with vintage.
export async function GET() {
  try {
    if (cache) {
      if (Date.now() - cache.t < CACHE_TTL_MS) return NextResponse.json(cache.data);
      startBackgroundRebuild();
      return NextResponse.json(cache.data);
    }
    const data = await buildSnapshot();
    cache = { t: Date.now(), data };
    return NextResponse.json(data);
  } catch (err) {
    console.error("[api/economics/snapshot] GET error:", err);
    return NextResponse.json({ metrics: [], builtAt: new Date().toISOString() }, { status: 500 });
  }
}