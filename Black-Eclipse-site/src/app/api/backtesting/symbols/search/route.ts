import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  try {
    const { searchParams } = new URL(request.url);
    const query = searchParams.get("query") || "";

    if (!query) {
      return NextResponse.json({ symbols: [] });
    }

    const symbols = await prisma.assetSymbol.findMany({
      where: {
        OR: [
          { symbol: { contains: query, mode: "insensitive" } },
          { displayName: { contains: query, mode: "insensitive" } },
        ],
        isActive: true,
      },
      take: 15,
      orderBy: { symbol: "asc" },
    });

    return NextResponse.json({ symbols });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Failed to search symbols." },
      { status: 500 }
    );
  }
}
