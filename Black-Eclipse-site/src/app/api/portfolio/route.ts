import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";
import { auth } from "@/lib/auth";
import { headers } from "next/headers";

export const dynamic = "force-dynamic";

async function resolveUser(): Promise<string | null> {
  try {
    const session = await auth.api.getSession({
      headers: await headers(),
    });
    if (session?.user?.id) {
      return session.user.id;
    }
  } catch (e) {
    // ignore
  }
  const reqHeaders = await headers();
  return reqHeaders.get("x-user-id") || null;
}

export async function GET() {
  try {
    const userId = await resolveUser();

    if (!userId) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    // Load or create default profile
    let profile = await prisma.portfolioProfile.findFirst({
      where: { userId },
      include: {
        transactions: true,
        snapshots: {
          orderBy: { timestamp: "asc" }
        },
        alerts: true
      }
    });

    let isNewProfile = false;
    if (!profile) {
      isNewProfile = true;
      profile = await prisma.portfolioProfile.create({
        data: {
          userId,
          name: "Main Portfolio",
          currency: "USD",
          taxMethod: "FIFO"
        },
        include: {
          transactions: true,
          snapshots: true,
          alerts: true
        }
      });
    }

    const userRow = await prisma.user.findUnique({
      where: { id: userId }
    });

    if (userRow?.email === "admin@blackeclipse.com" && isNewProfile) {
      // Clear previous database transactions, alerts, and snapshots for admin to ensure clean seeding
      await prisma.portfolioTransaction.deleteMany({ where: { profileId: profile.id } });
      await prisma.portfolioSnapshot.deleteMany({ where: { profileId: profile.id } });
      await prisma.portfolioAlert.deleteMany({ where: { profileId: profile.id } });

      const sampleTxs = [
        { type: "BUY", symbol: "BTC", quantity: 0.85, price: 58500.00, fee: 15.00, date: new Date("2026-05-10T12:00:00Z") },
        { type: "BUY", symbol: "ETH", quantity: 6.5, price: 2890.00, fee: 12.00, date: new Date("2026-05-12T14:30:00Z") },
        { type: "BUY", symbol: "SOL", quantity: 80.00, price: 115.00, fee: 3.50, date: new Date("2026-05-15T09:15:00Z") },
        { type: "SELL", symbol: "SOL", quantity: 20.00, price: 155.00, fee: 2.00, date: new Date("2026-05-20T16:00:00Z") },
        { type: "BUY", symbol: "LINK", quantity: 150.00, price: 14.20, fee: 1.50, date: new Date("2026-05-22T10:00:00Z") },
        { type: "BUY", symbol: "ADA", quantity: 2000.00, price: 0.45, fee: 2.00, date: new Date("2026-05-25T11:00:00Z") },
      ];
      
      const createdTxs = [];
      for (const tx of sampleTxs) {
        const dbTx = await prisma.portfolioTransaction.create({
          data: {
            profileId: profile.id,
            ...tx
          }
        });
        createdTxs.push(dbTx);
      }
      profile.transactions = createdTxs;

      // Seed historical snapshots (30 days)
      const now = new Date();
      const snapshotsData = [];
      let baseVal = 75000;
      let costBasis = 68000;
      for (let i = 30; i >= 0; i--) {
        const ts = new Date(now.getTime() - i * 24 * 60 * 60 * 1000);
        baseVal += (Math.random() - 0.45) * 2000;
        snapshotsData.push({
          profileId: profile.id,
          netAssetVal: parseFloat(baseVal.toFixed(2)),
          costBasis: costBasis,
          realizedPnL: 800.00,
          timestamp: ts
        });
      }
      await prisma.portfolioSnapshot.createMany({
        data: snapshotsData
      });

      // Seed sample alerts
      const sampleAlerts = [
        { symbol: "BTC", type: "PRICE_ABOVE", target: 72000.00 },
        { symbol: "ETH", type: "PRICE_BELOW", target: 2700.00 },
        { symbol: "SOL", type: "PRICE_ABOVE", target: 180.00 },
      ];
      const createdAlerts = [];
      for (const alert of sampleAlerts) {
        const dbAlert = await prisma.portfolioAlert.create({
          data: {
            profileId: profile.id,
            symbol: alert.symbol,
            type: alert.type,
            target: alert.target,
            isActive: true
          }
        });
        createdAlerts.push(dbAlert);
      }
      profile.alerts = createdAlerts;
    }

    return NextResponse.json(profile);
  } catch (err) {
    console.error("[GET /api/portfolio] Error:", err);
    return NextResponse.json({ error: "Failed to load portfolio" }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const userId = await resolveUser();

    if (!userId) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const body = await request.json();
    const { action, type, symbol, quantity, price, fee, date, notes, currency, taxMethod } = body;

    // Load active profile
    let profile = await prisma.portfolioProfile.findFirst({
      where: { userId }
    });

    if (!profile) {
      profile = await prisma.portfolioProfile.create({
        data: {
          userId,
          name: "Main Portfolio"
        }
      });
    }

    if (action === "update_settings") {
      const updated = await prisma.portfolioProfile.update({
        where: { id: profile.id },
        data: {
          currency: currency || profile.currency,
          taxMethod: taxMethod || profile.taxMethod
        }
      });
      return NextResponse.json({ success: true, profile: updated });
    }

    if (action === "add_transaction") {
      const tx = await prisma.portfolioTransaction.create({
        data: {
          profileId: profile.id,
          type,
          symbol: symbol.toUpperCase(),
          quantity: parseFloat(quantity),
          price: parseFloat(price),
          fee: parseFloat(fee) || 0,
          date: new Date(date),
          notes
        }
      });

      // Write snapshot point
      await prisma.portfolioSnapshot.create({
        data: {
          profileId: profile.id,
          netAssetVal: 0, // Computed dynamically frontend
          costBasis: 0,
          realizedPnL: 0,
          timestamp: new Date()
        }
      });

      return NextResponse.json({ success: true, transaction: tx });
    }

    if (action === "add_alert") {
      const alert = await prisma.portfolioAlert.create({
        data: {
          profileId: profile.id,
          symbol: symbol.toUpperCase(),
          type,
          target: parseFloat(price)
        }
      });
      return NextResponse.json({ success: true, alert });
    }

    return NextResponse.json({ error: "Invalid action" }, { status: 400 });
  } catch (err) {
    console.error("[POST /api/portfolio] Error:", err);
    return NextResponse.json({ error: "Failed to process portfolio action" }, { status: 500 });
  }
}

export async function DELETE(request: Request) {
  try {
    const userId = await resolveUser();

    if (!userId) {
      return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
    }

    const { searchParams } = new URL(request.url);
    const txId = searchParams.get("txId");
    const alertId = searchParams.get("alertId");
    const symbol = searchParams.get("symbol");

    if (txId) {
      await prisma.portfolioTransaction.delete({
        where: { id: txId }
      });
      return NextResponse.json({ success: true });
    }

    if (alertId) {
      await prisma.portfolioAlert.delete({
        where: { id: alertId }
      });
      return NextResponse.json({ success: true });
    }

    if (symbol) {
      // Delete all transactions for this symbol
      const profile = await prisma.portfolioProfile.findFirst({
        where: { userId }
      });
      if (profile) {
        await prisma.portfolioTransaction.deleteMany({
          where: { profileId: profile.id, symbol }
        });
      }
      return NextResponse.json({ success: true });
    }

    return NextResponse.json({ error: "Missing delete criteria" }, { status: 400 });
  } catch (err) {
    console.error("[DELETE /api/portfolio] Error:", err);
    return NextResponse.json({ error: "Failed to delete item" }, { status: 500 });
  }
}

