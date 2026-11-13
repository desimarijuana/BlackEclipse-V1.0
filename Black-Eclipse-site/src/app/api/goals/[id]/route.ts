import { NextResponse } from "next/server";
import { getGoal, type GoalView } from "@/lib/harness/clients/autonomy-client";

export const dynamic = "force-dynamic";

export async function GET(_request: Request, context: { params: Promise<{ id: string }> }) {
  const { id } = await context.params;
  try {
    const goal: GoalView = await getGoal(id);
    return NextResponse.json({ success: true, goal });
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "goal not found" },
      { status: 404 },
    );
  }
}
