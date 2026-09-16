import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { guardExpensiveMutation } from "@/lib/api-guard";
import { runAgent } from "@/lib/agent/loop";
import { OpenAICompatibleProvider } from "@/lib/agent/openai-provider";
import { rowToEvent, upgradeEventLocation } from "@/lib/investor-eye/state";
import { EXPLAIN_SYSTEM_PROMPT, explainPromptFor } from "@/lib/investor-eye/event-record";

export const dynamic = "force-dynamic";
export const maxDuration = 90;

/**
 * POST /api/investor-eye/explain   body: { id: string }
 *
 * "Explain this event" — runs the read-only world analyst over ONE event's
 * structured record. Grounded: the model receives the event as data (see
 * `event-record.ts`) and can call the Investor Eye tools, so it cites the feed
 * instead of free-associating.
 *
 * Returns 503 when no LLM is configured; the UI then says so rather than
 * pretending to work.
 */
export async function POST(request: Request) {
  const blocked = guardExpensiveMutation(request, "investor-eye-explain", { limit: 12, windowMs: 5 * 60_000 });
  if (blocked) {
    return NextResponse.json(blocked.body, { status: blocked.status, headers: blocked.headers });
  }

  try {
    const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
    const id = typeof body.id === "string" ? body.id : "";
    if (!id) return NextResponse.json({ error: "id is required" }, { status: 400 });

    const provider = new OpenAICompatibleProvider();
    if (!provider.isConfigured()) {
      return NextResponse.json(
        { error: "no LLM provider configured", hint: "Configure a provider in Settings → AI Agent." },
        { status: 503 },
      );
    }

    const row = await prisma.geopoliticalEvent.findFirst({ where: { OR: [{ id }, { dedupKey: id }] } });
    if (!row) return NextResponse.json({ error: "Event not found." }, { status: 404 });

    const event = upgradeEventLocation(rowToEvent(row));
    const result = await runAgent(provider, EXPLAIN_SYSTEM_PROMPT, explainPromptFor(event), {
      maxIterations: 5,
    });

    return NextResponse.json({
      success: true,
      answer: result.answer,
      toolCalls: result.toolCalls,
      eventId: event.id ?? event.dedupKey,
    });
  } catch (err) {
    console.error("[api/investor-eye/explain] error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Explanation failed" },
      { status: 500 },
    );
  }
}
