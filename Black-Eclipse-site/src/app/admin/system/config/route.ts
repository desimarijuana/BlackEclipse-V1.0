import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

const DEFAULT_CONFIG = {
  crypto: {
    universeEnabled: true,
    universeSyncInterval: 3600, // seconds (default: 1 hour)
    priceEnabled: true,
    priceUpdateInterval: 120, // seconds (default: 2 min)
  },
  stocks: {
    universeEnabled: true,
    universeSyncInterval: 3600,
    priceEnabled: true,
    priceUpdateInterval: 120,
  },
  api: {
    binanceEnabled: true,
    finnhubEnabled: true,
    timeout: 4000,
    retryCount: 3
  },
  system: {
    globalPause: false,
    mode: "hybrid"
  }
};

// Migrate old config format to new format
function migrateConfig(raw: any): any {
  const config = { ...raw };
  // Migrate crypto
  if (config.crypto) {
    if (config.crypto.universeSyncSchedule && config.crypto.universeSyncInterval === undefined) {
      // Convert old schedule string to interval seconds
      const scheduleMap: Record<string, number> = { daily: 86400, weekly: 604800, monthly: 2592000 };
      config.crypto.universeSyncInterval = scheduleMap[config.crypto.universeSyncSchedule] || 3600;
      delete config.crypto.universeSyncSchedule;
    }
    if (config.crypto.enabled !== undefined && config.crypto.universeEnabled === undefined) {
      config.crypto.universeEnabled = config.crypto.enabled;
      config.crypto.priceEnabled = config.crypto.enabled;
      delete config.crypto.enabled;
    }
  }
  // Migrate stocks
  if (config.stocks) {
    if (config.stocks.universeSyncSchedule && config.stocks.universeSyncInterval === undefined) {
      const scheduleMap: Record<string, number> = { daily: 86400, weekly: 604800, monthly: 2592000 };
      config.stocks.universeSyncInterval = scheduleMap[config.stocks.universeSyncSchedule] || 3600;
      delete config.stocks.universeSyncSchedule;
    }
    if (config.stocks.enabled !== undefined && config.stocks.universeEnabled === undefined) {
      config.stocks.universeEnabled = config.stocks.enabled;
      config.stocks.priceEnabled = config.stocks.enabled;
      delete config.stocks.enabled;
    }
  }
  return config;
}

export async function GET() {
  try {
    const configRow = await prisma.systemConfig.findUnique({
      where: { key: "system_config" }
    });

    const activeModeRow = await prisma.systemConfig.findUnique({
      where: { key: "active_mode" }
    });

    const activeMode = activeModeRow?.value || "hybrid";

    let config = JSON.parse(JSON.stringify(DEFAULT_CONFIG));
    if (configRow) {
      try {
        const raw = JSON.parse(configRow.value);
        const migrated = migrateConfig(raw);
        config = {
          crypto: { ...config.crypto, ...migrated.crypto },
          stocks: { ...config.stocks, ...migrated.stocks },
          api: { ...config.api, ...migrated.api },
          system: { ...config.system, ...migrated.system },
        };
      } catch (e) {
        // use default
      }
    }

    config.system.mode = activeMode;

    // Read Run Now statuses
    const [runNowUniverse, runNowPrices] = await Promise.all([
      prisma.systemConfig.findUnique({ where: { key: "run_now_universe" } }),
      prisma.systemConfig.findUnique({ where: { key: "run_now_prices" } }),
    ]);

    return NextResponse.json({
      ...config,
      runNow: {
        universe: runNowUniverse?.value || "idle",
        prices: runNowPrices?.value || "idle",
      }
    });
  } catch (err) {
    console.error("[GET /admin/system/config] Error:", err);
    return NextResponse.json({ error: "Failed to load system config" }, { status: 500 });
  }
}

export async function POST(request: Request) {
  try {
    const body = await request.json();
    
    // Read existing config
    const configRow = await prisma.systemConfig.findUnique({
      where: { key: "system_config" }
    });

    let existingConfig = JSON.parse(JSON.stringify(DEFAULT_CONFIG));
    if (configRow) {
      try {
        const raw = JSON.parse(configRow.value);
        const migrated = migrateConfig(raw);
        existingConfig = {
          crypto: { ...existingConfig.crypto, ...migrated.crypto },
          stocks: { ...existingConfig.stocks, ...migrated.stocks },
          api: { ...existingConfig.api, ...migrated.api },
          system: { ...existingConfig.system, ...migrated.system },
        };
      } catch (e) {
        // use default
      }
    }

    const newConfig = {
      crypto: { ...existingConfig.crypto, ...body.crypto },
      stocks: { ...existingConfig.stocks, ...body.stocks },
      api: { ...existingConfig.api, ...body.api },
      system: { ...existingConfig.system, ...body.system },
    };

    // Read existing active mode from DB to preserve it
    const activeModeRow = await prisma.systemConfig.findUnique({
      where: { key: "active_mode" }
    });
    const currentActiveMode = activeModeRow?.value || "hybrid";
    newConfig.system.mode = currentActiveMode;

    // Save JSON back to PostgreSQL
    await prisma.systemConfig.upsert({
      where: { key: "system_config" },
      update: { value: JSON.stringify(newConfig) },
      create: { key: "system_config", value: JSON.stringify(newConfig) }
    });

    // Write individual keys for daemon compatibility
    const upserts = [
      prisma.systemConfig.upsert({
        where: { key: "universe_interval" },
        update: { value: String(newConfig.crypto.universeSyncInterval) },
        create: { key: "universe_interval", value: String(newConfig.crypto.universeSyncInterval) }
      }),
      prisma.systemConfig.upsert({
        where: { key: "universe_enabled" },
        update: { value: String(newConfig.crypto.universeEnabled) },
        create: { key: "universe_enabled", value: String(newConfig.crypto.universeEnabled) }
      }),
      prisma.systemConfig.upsert({
        where: { key: "price_interval" },
        update: { value: String(newConfig.crypto.priceUpdateInterval) },
        create: { key: "price_interval", value: String(newConfig.crypto.priceUpdateInterval) }
      }),
      prisma.systemConfig.upsert({
        where: { key: "price_enabled" },
        update: { value: String(newConfig.crypto.priceEnabled) },
        create: { key: "price_enabled", value: String(newConfig.crypto.priceEnabled) }
      }),
      prisma.systemConfig.upsert({
        where: { key: "crypto_enabled" },
        update: { value: String(newConfig.crypto.priceEnabled) },
        create: { key: "crypto_enabled", value: String(newConfig.crypto.priceEnabled) }
      }),
      prisma.systemConfig.upsert({
        where: { key: "stocks_enabled" },
        update: { value: String(newConfig.stocks.priceEnabled) },
        create: { key: "stocks_enabled", value: String(newConfig.stocks.priceEnabled) }
      }),
      prisma.systemConfig.upsert({
        where: { key: "api_binance_enabled" },
        update: { value: String(newConfig.api.binanceEnabled) },
        create: { key: "api_binance_enabled", value: String(newConfig.api.binanceEnabled) }
      }),
      prisma.systemConfig.upsert({
        where: { key: "api_finnhub_enabled" },
        update: { value: String(newConfig.api.finnhubEnabled) },
        create: { key: "api_finnhub_enabled", value: String(newConfig.api.finnhubEnabled) }
      }),
      prisma.systemConfig.upsert({
        where: { key: "global_pause" },
        update: { value: String(newConfig.system.globalPause) },
        create: { key: "global_pause", value: String(newConfig.system.globalPause) }
      })
    ];
    await Promise.all(upserts);

    return NextResponse.json({ success: true, config: newConfig });
  } catch (err) {
    console.error("[POST /admin/system/config] Error:", err);
    return NextResponse.json({ error: "Failed to update configuration" }, { status: 500 });
  }
}
