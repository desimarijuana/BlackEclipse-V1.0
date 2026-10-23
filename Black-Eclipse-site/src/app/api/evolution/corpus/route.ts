import { NextResponse } from "next/server";
import { getEvolutionCorpusStatus } from "@/lib/harness/evolution-client";
import { HarnessRuntimeUnavailable } from "@/lib/harness";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const result = await getEvolutionCorpusStatus();
    return NextResponse.json(result);
  } catch (err) {
    const unavailable = err instanceof HarnessRuntimeUnavailable;
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "corpus status failed" },
      { status: unavailable ? 503 : 500 },
    );
  }
}
