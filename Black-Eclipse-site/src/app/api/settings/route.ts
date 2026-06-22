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

    const configs = await prisma.systemConfig.findMany();
    const configMap = configs.reduce((acc, c) => {
      acc[c.key] = c.value;
      return acc;
    }, {} as Record<string, string>);

    return NextResponse.json({
      finnhubToken: configMap.finnhub_api_key || "",
      binanceApiKey: configMap.binance_api_key || "",
      marketauxToken: configMap.marketaux_api_key || "lgw4jOLpqAJbbCIotGst7q79s7XFWFINOPe6EoCY",
      cryptopanicToken: configMap.cryptopanic_api_key || "",
      cryptoInterval: configMap.crypto_interval_ms || "120000",
      stockInterval: configMap.stock_interval_ms || "120000",
      emailAlerts: configMap.email_alerts_enabled === "true"
    });
  } catch (err) {
    console.error("[api/settings] GET error:", err);
    return NextResponse.json({ error: "Failed to load settings" }, { status: 500 });
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
    const { finnhubToken, binanceApiKey, marketauxToken, cryptopanicToken, cryptoInterval, stockInterval, emailAlerts } = body;

    const upserts = [
      prisma.systemConfig.upsert({
        where: { key: "finnhub_api_key" },
        update: { value: finnhubToken || "" },
        create: { key: "finnhub_api_key", value: finnhubToken || "" }
      }),
      prisma.systemConfig.upsert({
        where: { key: "binance_api_key" },
        update: { value: binanceApiKey || "" },
        create: { key: "binance_api_key", value: binanceApiKey || "" }
      }),
      prisma.systemConfig.upsert({
        where: { key: "marketaux_api_key" },
        update: { value: marketauxToken || "" },
        create: { key: "marketaux_api_key", value: marketauxToken || "" }
      }),
      prisma.systemConfig.upsert({
        where: { key: "cryptopanic_api_key" },
        update: { value: cryptopanicToken || "" },
        create: { key: "cryptopanic_api_key", value: cryptopanicToken || "" }
      }),
      prisma.systemConfig.upsert({
        where: { key: "crypto_interval_ms" },
        update: { value: String(cryptoInterval || "120000") },
        create: { key: "crypto_interval_ms", value: String(cryptoInterval || "120000") }
      }),
      prisma.systemConfig.upsert({
        where: { key: "stock_interval_ms" },
        update: { value: String(stockInterval || "120000") },
        create: { key: "stock_interval_ms", value: String(stockInterval || "120000") }
      }),
      prisma.systemConfig.upsert({
        where: { key: "email_alerts_enabled" },
        update: { value: String(!!emailAlerts) },
        create: { key: "email_alerts_enabled", value: String(!!emailAlerts) }
      })
    ];

    await Promise.all(upserts);

    return NextResponse.json({ success: true });
  } catch (err) {
    console.error("[api/settings] POST error:", err);
    return NextResponse.json({ error: "Failed to save settings" }, { status: 500 });
  }
}
