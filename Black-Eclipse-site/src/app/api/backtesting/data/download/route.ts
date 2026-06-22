import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { symbolId, symbol, timeframe, startDate, endDate } = body;

    let targetSymbolId = symbolId;
    
    // If symbolId is not provided, look it up by symbol name
    if (!targetSymbolId && symbol) {
      const symObj = await prisma.assetSymbol.findFirst({
        where: { symbol: symbol.toUpperCase() }
      });
      if (symObj) {
        targetSymbolId = symObj.id;
      }
    }

    if (!targetSymbolId) {
      return NextResponse.json({ error: "Missing symbol identifier." }, { status: 400 });
    }

    const timeframeStr = timeframe || "1d";
    const start = startDate ? new Date(startDate) : new Date(Date.now() - 365 * 24 * 60 * 60 * 1000);
    const end = endDate ? new Date(endDate) : new Date();

    // Check if job already exists
    const existingJob = await prisma.jDDSJob.findFirst({
      where: {
        symbolId: targetSymbolId,
        timeframe: timeframeStr,
        status: { in: ["pending", "running"] }
      }
    });

    if (existingJob) {
      return NextResponse.json({
        message: "Job already running.",
        jobId: existingJob.id,
        status: existingJob.status,
        progress: existingJob.progress
      });
    }

    // Create job
    const job = await prisma.jDDSJob.create({
      data: {
        type: "historical_download",
        status: "pending",
        priority: 2, // High priority manual download
        symbolId: targetSymbolId,
        timeframe: timeframeStr,
        startDate: start,
        endDate: end,
        progress: 0
      }
    });

    // Update symbol status
    await prisma.assetSymbol.update({
      where: { id: targetSymbolId },
      data: { dataStatus: "downloading" }
    });

    return NextResponse.json({
      message: "Download job queued successfully.",
      jobId: job.id,
      status: job.status,
      progress: job.progress
    });

  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Failed to trigger download job." },
      { status: 500 }
    );
  }
}
