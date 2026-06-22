import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { symbolId, csvText, timeframe } = body;

    if (!symbolId || !csvText) {
      return NextResponse.json({ error: "Missing symbolId or csvText parameter." }, { status: 400 });
    }

    const symbol = await prisma.assetSymbol.findUnique({
      where: { id: symbolId }
    });

    if (!symbol) {
      return NextResponse.json({ error: "Target symbol not found in universe." }, { status: 404 });
    }

    const activeTimeframe = timeframe || "1d";
    const lines = csvText.split("\n");
    const candles: any[] = [];
    const seenDates = new Set<string>();

    // CSV Parse
    const headers = lines[0].toLowerCase().split(",").map((h: string) => h.trim());
    const dateIdx = headers.indexOf("date");
    const openIdx = headers.indexOf("open");
    const highIdx = headers.indexOf("high");
    const lowIdx = headers.indexOf("low");
    const closeIdx = headers.indexOf("close");
    const volumeIdx = headers.indexOf("volume");

    if (dateIdx === -1 || openIdx === -1 || highIdx === -1 || lowIdx === -1 || closeIdx === -1) {
      return NextResponse.json({ error: "CSV must contain date, open, high, low, close headers." }, { status: 400 });
    }

    for (let i = 1; i < lines.length; i++) {
      const line = lines[i].trim();
      if (!line) continue;

      const parts = line.split(",").map((p: string) => p.trim());
      if (parts.length < 5) continue;

      const rawDateStr = parts[dateIdx];
      const parsedDate = new Date(rawDateStr);
      if (isNaN(parsedDate.getTime())) continue;

      const dateKey = parsedDate.toISOString();
      if (seenDates.has(dateKey)) continue; // Remove duplicates

      const open = parseFloat(parts[openIdx]);
      const high = parseFloat(parts[highIdx]);
      const low = parseFloat(parts[lowIdx]);
      const close = parseFloat(parts[closeIdx]);
      const volume = volumeIdx !== -1 && parts[volumeIdx] ? parseFloat(parts[volumeIdx]) : 0;

      // Validation
      if (isNaN(open) || isNaN(high) || isNaN(low) || isNaN(close)) continue;
      if (open <= 0 || high <= 0 || low <= 0 || close <= 0) continue;
      // High/low bounding checks
      if (high < Math.max(open, close) || low > Math.min(open, close)) continue;

      seenDates.add(dateKey);

      candles.push({
        symbolId: symbol.id,
        timeframe: activeTimeframe,
        timestamp: parsedDate,
        open,
        high,
        low,
        close,
        volume,
        source: "CSV Import",
        quality: "clean"
      });
    }

    if (candles.length === 0) {
      return NextResponse.json({ error: "No valid rows found in CSV." }, { status: 400 });
    }

    // Sort by date ascending
    candles.sort((a, b) => a.timestamp.getTime() - b.timestamp.getTime());

    // Detect missing candles
    let missingCount = 0;
    const intervalMsMap: Record<string, number> = {
      "1m": 60 * 1000,
      "5m": 5 * 60 * 1000,
      "15m": 15 * 60 * 1000,
      "1h": 60 * 60 * 1000,
      "1d": 24 * 60 * 60 * 1000
    };
    const expectedStepMs = intervalMsMap[activeTimeframe] || 24 * 60 * 60 * 1000;

    for (let i = 1; i < candles.length; i++) {
      const diff = candles[i].timestamp.getTime() - candles[i - 1].timestamp.getTime();
      // Allow slight variance, e.g. weekends for stocks
      if (diff > expectedStepMs * 1.5) {
        // Estimate missing count (excluding weekends for daily stocks if possible, but keep simple step count)
        const gapSteps = Math.floor(diff / expectedStepMs) - 1;
        if (gapSteps > 0 && gapSteps < 500) {
          missingCount += gapSteps;
        }
      }
    }

    // Bulk insert candles to PostgreSQL
    const chunkSize = 1000;
    for (let i = 0; i < candles.length; i += chunkSize) {
      const chunk = candles.slice(i, i + chunkSize);
      await prisma.historicalCandle.createMany({
        data: chunk,
        skipDuplicates: true
      });
    }

    // Update symbol status
    await prisma.assetSymbol.update({
      where: { id: symbol.id },
      data: {
        dataStatus: "ready",
        isBacktestEnabled: true,
        lastSyncedAt: new Date()
      }
    });

    return NextResponse.json({
      success: true,
      importedCount: candles.length,
      missingGapsDetected: missingCount,
      message: `Successfully imported ${candles.length} candles. Detected ${missingCount} potential missing candle gaps.`
    });

  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Failed to parse and import CSV data." },
      { status: 500 }
    );
  }
}
