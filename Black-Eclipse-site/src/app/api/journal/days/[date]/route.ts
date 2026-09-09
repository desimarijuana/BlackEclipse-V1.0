import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import { prisma } from "@/lib/db";
import { getOrCreateProfile } from "@/lib/journal/data";

export const dynamic = "force-dynamic";

// GET /api/journal/days/[date] — get a day's journal (review + emotion + trades).
export async function GET(_request: Request, { params }: { params: Promise<{ date: string }> }) {
  try {
    const { date } = await params;
    const profileId = await getOrCreateProfile();
    const dayDate = new Date(date.slice(0, 10) + "T00:00:00Z");
    const day = await prisma.journalDay.findUnique({
      where: { profileId_date: { profileId, date: dayDate } },
      include: {
        review: true,
        emotion: true,
        trades: {
          include: {
            strategy: { select: { name: true } },
            setup: { select: { name: true } },
            tags: { include: { tag: { select: { name: true } } } },
          },
          orderBy: { entryTime: "asc" },
        },
      },
    });
    return NextResponse.json({ day });
  } catch (err) {
    console.error("[api/journal/days] GET error:", err);
    return NextResponse.json({ error: "Failed to load day" }, { status: 500 });
  }
}

// POST /api/journal/days/[date] — upsert a day's review + emotion.
export async function POST(request: Request, { params }: { params: Promise<{ date: string }> }) {
  const blocked = guardMutation(request, "journal-days");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const { date } = await params;
    const body = await request.json().catch(() => ({}));
    const profileId = await getOrCreateProfile();
    const dayDate = new Date(date.slice(0, 10) + "T00:00:00Z");
    const day = await prisma.journalDay.upsert({
      where: { profileId_date: { profileId, date: dayDate } },
      update: {},
      create: { profileId, date: dayDate },
    });

    const reviewData = {
      marketBias: typeof body.marketBias === "string" ? body.marketBias : null,
      tradingPlan: typeof body.tradingPlan === "string" ? body.tradingPlan : null,
      marketsWatching: Array.isArray(body.marketsWatching) ? JSON.stringify(body.marketsWatching) : null,
      keyLevels: typeof body.keyLevels === "string" ? body.keyLevels : null,
      wentWell: typeof body.wentWell === "string" ? body.wentWell : null,
      wentWrong: typeof body.wentWrong === "string" ? body.wentWrong : null,
      followedStrategy: typeof body.followedStrategy === "string" ? body.followedStrategy : null,
      biggestMistake: typeof body.biggestMistake === "string" ? body.biggestMistake : null,
      lesson: typeof body.lesson === "string" ? body.lesson : null,
      tomorrow: typeof body.tomorrow === "string" ? body.tomorrow : null,
    };
    const emotionData = {
      state: typeof body.state === "string" ? body.state : null,
      confidence: typeof body.confidence === "number" ? body.confidence : null,
      discipline: typeof body.discipline === "number" ? body.discipline : null,
      notes: typeof body.notes === "string" ? body.notes : null,
    };

    const review = await prisma.dailyReview.upsert({
      where: { dayId: day.id },
      update: reviewData,
      create: { dayId: day.id, ...reviewData },
    });
    const emotion = await prisma.dailyEmotion.upsert({
      where: { dayId: day.id },
      update: emotionData,
      create: { dayId: day.id, ...emotionData },
    });

    return NextResponse.json({ success: true, review, emotion });
  } catch (err) {
    console.error("[api/journal/days] POST error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to save day" },
      { status: 500 }
    );
  }
}
