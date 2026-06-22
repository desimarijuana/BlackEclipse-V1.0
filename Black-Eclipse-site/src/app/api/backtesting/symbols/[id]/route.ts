import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const symbol = await prisma.assetSymbol.findUnique({
      where: { id },
      include: {
        _count: {
          select: { candles: true }
        }
      }
    });

    if (!symbol) {
      return NextResponse.json({ error: "Symbol not found." }, { status: 404 });
    }

    return NextResponse.json({ symbol });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Failed to fetch symbol details." },
      { status: 500 }
    );
  }
}
