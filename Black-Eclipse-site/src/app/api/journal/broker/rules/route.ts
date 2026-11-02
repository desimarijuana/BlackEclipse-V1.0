import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { getOrCreateProfile } from "@/lib/journal/data";
import { createAttributionRule, listAttributionRules } from "@/lib/journal/broker/links";

export const dynamic = "force-dynamic";

// GET /api/journal/broker/rules — magic/comment/symbol → strategy/setup/tags.
export async function GET() {
  try {
    const profileId = await getOrCreateProfile();
    const rules = await listAttributionRules(profileId);
    return NextResponse.json({ rules });
  } catch (err) {
    console.error("[api/journal/broker/rules] GET error:", err);
    return NextResponse.json({ error: "Failed to load attribution rules" }, { status: 500 });
  }
}

// POST /api/journal/broker/rules — add an attribution rule.
export async function POST(request: Request) {
  const blocked = guardMutation(request, "journal-broker-rule");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = await request.json().catch(() => ({}));
    const hasMatcher =
      body.magic != null ||
      (typeof body.commentMatch === "string" && body.commentMatch.trim()) ||
      (typeof body.symbolMatch === "string" && body.symbolMatch.trim());
    if (!hasMatcher) {
      return NextResponse.json(
        { error: "A rule needs at least one matcher (magic, commentMatch or symbolMatch)" },
        { status: 400 },
      );
    }
    const profileId = await getOrCreateProfile();
    const rule = await createAttributionRule(profileId, {
      connectionId: typeof body.connectionId === "string" ? body.connectionId : null,
      magic: body.magic != null ? Number(body.magic) : null,
      commentMatch: typeof body.commentMatch === "string" ? body.commentMatch : null,
      symbolMatch: typeof body.symbolMatch === "string" ? body.symbolMatch : null,
      strategyId: typeof body.strategyId === "string" ? body.strategyId : null,
      setupId: typeof body.setupId === "string" ? body.setupId : null,
      tagNames: Array.isArray(body.tagNames)
        ? body.tagNames.filter((x: unknown): x is string => typeof x === "string")
        : null,
      priority: typeof body.priority === "number" ? body.priority : 0,
    });
    return NextResponse.json({ success: true, rule });
  } catch (err) {
    console.error("[api/journal/broker/rules] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to create attribution rule" },
      { status: 500 },
    );
  }
}
