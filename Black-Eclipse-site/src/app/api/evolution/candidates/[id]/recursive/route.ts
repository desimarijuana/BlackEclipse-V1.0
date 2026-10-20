import { NextResponse } from "next/server";
import { runEvolutionRecursive } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";
import type { EvolutionRecursiveVariant } from "@/lib/harness/evolution-client";

export const dynamic = "force-dynamic";

export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  try {
    const body = (await request.json()) as {
      variants: EvolutionRecursiveVariant[];
      seed?: number;
    };
    const result = await runEvolutionRecursive(id, body);
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "recursive experiment failed" },
      { status: unavailable ? 503 : 400 },
    );
  }
}
