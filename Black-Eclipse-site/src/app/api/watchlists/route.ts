import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { auth } from "@/lib/auth";
import { headers } from "next/headers";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const session = await auth.api.getSession({
      headers: await headers(),
    });

    if (!session || !session.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const watchlists = await prisma.watchlist.findMany({
      where: { userId: session.user.id },
      orderBy: { createdAt: "desc" }
    });

    // Hydrate prices for all watchlists
    const hydratedWatchlists = await Promise.all(
      watchlists.map(async (w) => {
        let assetList: Array<{ symbol: string; type: "crypto" | "stock" }> = [];
        try {
          assetList = typeof w.assets === "string" ? JSON.parse(w.assets) : (w.assets as any);
          if (!Array.isArray(assetList)) assetList = [];
        } catch {
          assetList = [];
        }

        const hydratedAssets = await Promise.all(
          assetList.map(async (asset) => {
            if (asset.type === "crypto") {
              const crypto = await prisma.cryptoAsset.findUnique({
                where: { symbol: asset.symbol },
                include: { price: true }
              });
              return {
                symbol: asset.symbol,
                type: "crypto",
                price: crypto?.price?.price ?? 0,
                changePercent: crypto?.price?.change24h ?? 0,
                volume: crypto?.price?.volume ?? 0
              };
            } else {
              const stock = await prisma.stockAsset.findUnique({
                where: { symbol: asset.symbol },
                include: { price: true }
              });
              return {
                symbol: asset.symbol,
                type: "stock",
                name: stock?.name ?? asset.symbol,
                price: stock?.price?.price ?? 0,
                changePercent: stock?.price?.changePercent ?? 0,
                marketCap: stock?.price?.marketCap ?? 0
              };
            }
          })
        );

        return {
          id: w.id,
          name: w.name,
          assets: hydratedAssets,
          createdAt: w.createdAt
        };
      })
    );

    return NextResponse.json(hydratedWatchlists);
  } catch (err) {
    console.error("[api/watchlists] GET error:", err);
    return NextResponse.json({ error: "Failed to fetch watchlists" }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const session = await auth.api.getSession({
      headers: await headers(),
    });

    if (!session || !session.user) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await request.json();
    const { action, name, id, symbol, type } = body;

    // Action 1: Create Watchlist
    if (action === "create") {
      if (!name || typeof name !== "string") {
        return NextResponse.json({ error: "Watchlist name is required" }, { status: 400 });
      }

      const newW = await prisma.watchlist.create({
        data: {
          userId: session.user.id,
          name,
          assets: JSON.stringify([])
        }
      });
      return NextResponse.json(newW);
    }

    // Action 2: Add Asset to Watchlist
    if (action === "add") {
      if (!id || !symbol || !type) {
        return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
      }

      const watchlist = await prisma.watchlist.findUnique({
        where: { id }
      });

      if (!watchlist || watchlist.userId !== session.user.id) {
        return NextResponse.json({ error: "Watchlist not found" }, { status: 404 });
      }

      let assetList: Array<{ symbol: string; type: string }> = [];
      try {
        assetList = typeof watchlist.assets === "string" ? JSON.parse(watchlist.assets) : (watchlist.assets as any);
        if (!Array.isArray(assetList)) assetList = [];
      } catch {
        assetList = [];
      }

      // Check if already exists
      if (assetList.some(a => a.symbol === symbol.toUpperCase())) {
        return NextResponse.json({ error: "Asset already in watchlist" }, { status: 400 });
      }

      assetList.push({ symbol: symbol.toUpperCase(), type });

      const updated = await prisma.watchlist.update({
        where: { id },
        data: {
          assets: JSON.stringify(assetList)
        }
      });

      return NextResponse.json(updated);
    }

    // Action 3: Remove Asset from Watchlist
    if (action === "remove") {
      if (!id || !symbol) {
        return NextResponse.json({ error: "Missing required fields" }, { status: 400 });
      }

      const watchlist = await prisma.watchlist.findUnique({
        where: { id }
      });

      if (!watchlist || watchlist.userId !== session.user.id) {
        return NextResponse.json({ error: "Watchlist not found" }, { status: 404 });
      }

      let assetList: Array<{ symbol: string; type: string }> = [];
      try {
        assetList = typeof watchlist.assets === "string" ? JSON.parse(watchlist.assets) : (watchlist.assets as any);
        if (!Array.isArray(assetList)) assetList = [];
      } catch {
        assetList = [];
      }

      const filteredList = assetList.filter(a => a.symbol !== symbol.toUpperCase());

      const updated = await prisma.watchlist.update({
        where: { id },
        data: {
          assets: JSON.stringify(filteredList)
        }
      });

      return NextResponse.json(updated);
    }

    // Action 4: Delete Watchlist
    if (action === "delete") {
      if (!id) {
        return NextResponse.json({ error: "Watchlist ID is required" }, { status: 400 });
      }

      const watchlist = await prisma.watchlist.findUnique({
        where: { id }
      });

      if (!watchlist || watchlist.userId !== session.user.id) {
        return NextResponse.json({ error: "Watchlist not found" }, { status: 404 });
      }

      await prisma.watchlist.delete({
        where: { id }
      });

      return NextResponse.json({ success: true });
    }

    return NextResponse.json({ error: "Invalid action" }, { status: 400 });
  } catch (err) {
    console.error("[api/watchlists] POST error:", err);
    return NextResponse.json({ error: "Internal Server Error" }, { status: 500 });
  }
}
