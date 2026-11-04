import { NextResponse } from "next/server";
import { checkMutationAllowed } from "@/lib/api-guard";
import {
  getNewsAlertPolicy,
  setNewsAlertPolicy,
  type NewsAlertPolicy,
} from "@/lib/news/alert-policy";

export const dynamic = "force-dynamic";

// GET /api/news/alerts/policy — current background push policy.
export async function GET() {
  try {
    return NextResponse.json({ policy: await getNewsAlertPolicy() });
  } catch (err) {
    console.error("[api/news/alerts/policy] GET error:", err);
    return NextResponse.json({ error: "failed to read policy" }, { status: 500 });
  }
}

// POST /api/news/alerts/policy — partial update from Settings.
export async function POST(request: Request) {
  const guard = checkMutationAllowed(request);
  if (!guard.allowed) return NextResponse.json({ error: guard.reason }, { status: 403 });

  try {
    const body = (await request.json()) as Partial<NewsAlertPolicy>;
    const policy = await setNewsAlertPolicy(body);
    return NextResponse.json({ ok: true, policy });
  } catch (err) {
    console.error("[api/news/alerts/policy] POST error:", err);
    return NextResponse.json({ error: "failed to save policy" }, { status: 500 });
  }
}
