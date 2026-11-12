import { NextResponse } from "next/server";
import { listSkills } from "@/lib/harness/clients/skills-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

// GET /api/skills — the Skills Library. Python owns the registry; this proxies.
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const sp = url.searchParams;
    const num = (key: string): number | undefined => {
      const raw = sp.get(key);
      if (raw === null || raw.trim() === "") return undefined;
      const parsed = Number(raw);
      return Number.isFinite(parsed) ? parsed : undefined;
    };
    const data = await listSkills({
      status: sp.get("status") || undefined,
      q: sp.get("q") || undefined,
      category: sp.get("category") || undefined,
      risk: sp.get("risk") || undefined,
      sort: (sp.get("sort") as "name" | "status" | "risk" | "updated" | null) || undefined,
      limit: num("limit"),
      offset: num("offset"),
    });
    return NextResponse.json({ success: true, ...data });
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "skill list failed" },
      { status: unavailable ? 503 : 500 }
    );
  }
}
