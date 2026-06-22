import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { mode } = body;

    const validModes = ["universe_only", "price_only", "hybrid", "suspended"];
    if (!mode || !validModes.includes(mode)) {
      return NextResponse.json(
        { error: `Invalid mode. Must be one of: ${validModes.join(", ")}` },
        { status: 400 }
      );
    }

    // Persist to PostgreSQL
    await prisma.systemConfig.upsert({
      where: { key: "active_mode" },
      update: { value: mode },
      create: { key: "active_mode", value: mode }
    });

    // Also sync the mode into the JSON system_config if it exists
    const configRow = await prisma.systemConfig.findUnique({
      where: { key: "system_config" }
    });

    let configJson: any = {};
    if (configRow) {
      try {
        configJson = JSON.parse(configRow.value);
      } catch (e) {
        configJson = {};
      }
    }
    if (!configJson.system) configJson.system = {};
    configJson.system.mode = mode;

    await prisma.systemConfig.upsert({
      where: { key: "system_config" },
      update: { value: JSON.stringify(configJson) },
      create: { key: "system_config", value: JSON.stringify(configJson) }
    });

    return NextResponse.json({ success: true, activeMode: mode });
  } catch (err) {
    console.error("[POST /admin/system/mode] Error:", err);
    return NextResponse.json(
      { error: "Failed to update configuration mode" },
      { status: 500 }
    );
  }
}
