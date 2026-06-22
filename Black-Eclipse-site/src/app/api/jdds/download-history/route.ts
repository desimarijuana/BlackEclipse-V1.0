import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { symbolId, timeframe, startDate, endDate } = body;

    if (!symbolId) {
      return NextResponse.json({ error: "Missing symbolId parameter." }, { status: 400 });
    }

    const start = startDate ? new Date(startDate) : new Date(Date.now() - 365 * 24 * 60 * 60 * 1000);
    const end = endDate ? new Date(endDate) : new Date();

    const job = await prisma.jDDSJob.create({
      data: {
        type: "historical_download",
        status: "pending",
        priority: 1, // Admin triggered downloads have high priority
        symbolId,
        timeframe: timeframe || "1d",
        startDate: start,
        endDate: end,
        progress: 0
      }
    });

    await prisma.assetSymbol.update({
      where: { id: symbolId },
      data: { dataStatus: "downloading" }
    });

    return NextResponse.json({
      success: true,
      jobId: job.id,
      message: "Admin-triggered download job queued."
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Failed to trigger admin historical download." },
      { status: 500 }
    );
  }
}
