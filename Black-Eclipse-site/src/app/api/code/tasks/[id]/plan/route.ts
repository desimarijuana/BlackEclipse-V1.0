import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { acceptCodePlan, type CodePlan } from "@/lib/harness/code-client";

export const dynamic = "force-dynamic";

export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  const blocked = guardMutation(request, "code-plan-accept");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  const { id } = await params;
  const body = (await request.json().catch(() => ({}))) as { steps?: CodePlan["steps"]; checkClasses?: string[] };
  try {
    const result = await acceptCodePlan(id, body.steps ?? [], body.checkClasses ?? []);
    return NextResponse.json({ success: true, result });
  } catch (err) {
    return NextResponse.json({ error: err instanceof Error ? err.message : "accept failed" }, { status: 500 });
  }
}
