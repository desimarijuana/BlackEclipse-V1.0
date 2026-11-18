import { NextResponse } from "next/server";
import { guardMutation, rateLimit } from "@/lib/api-guard";
import {
  activeJob,
  removePack,
  snapshot,
  startInstall,
} from "@/lib/desktop/packs";

export const dynamic = "force-dynamic";

/**
 * GET /api/desktop/packs
 *
 * The Components panel polls this while a download runs, so it must stay
 * cheap: no network, only a few `existsSync` calls per pack.
 */
export async function GET() {
  try {
    return NextResponse.json({ ...snapshot(), job: activeJob() });
  } catch (err) {
    console.error("[api/desktop/packs] status error:", err);
    return NextResponse.json(
      { error: "Could not read the feature-pack state." },
      { status: 500 },
    );
  }
}

/**
 * POST /api/desktop/packs
 *
 * `{ action: "install", pack }` starts a background download and returns the
 * job immediately; progress is read from GET. `{ action: "remove" }` deletes
 * the pack's package directories and returns the new state.
 */
export async function POST(request: Request) {
  const blocked = guardMutation(request, "desktop-packs");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  const limited = rateLimit("desktop-packs", { limit: 8, windowMs: 60_000 });
  if (!limited.ok) {
    return NextResponse.json(
      { error: `Too many pack requests — retry in ${limited.retryAfterSec}s` },
      { status: 429 },
    );
  }

  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  const action = body.action;
  const pack = body.pack;

  try {
    if (action === "install") {
      const job = startInstall(pack);
      return NextResponse.json({ ok: true, job, ...snapshot() });
    }
    if (action === "remove") {
      removePack(pack);
      return NextResponse.json({ ok: true, ...snapshot() });
    }
    return NextResponse.json(
      { error: 'Expected { action: "install" | "remove", pack: string }' },
      { status: 400 },
    );
  } catch (err) {
    const status = (err as { status?: number }).status ?? 500;
    const message = err instanceof Error ? err.message : "Pack request failed";
    if (status >= 500) console.error("[api/desktop/packs] error:", err);
    return NextResponse.json({ error: message }, { status });
  }
}
