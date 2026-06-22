import { NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST() {
  try {
    await prisma.systemConfig.upsert({
      where: { key: "active_mode" },
      update: { value: "hybrid" },
      create: { key: "active_mode", value: "hybrid" }
    });

    // Also update system_config JSON
    const configRow = await prisma.systemConfig.findUnique({
      where: { key: "system_config" }
    });
    if (configRow) {
      try {
        const config = JSON.parse(configRow.value);
        config.system = config.system || {};
        config.system.mode = "hybrid";
        config.system.globalPause = false;
        await prisma.systemConfig.update({
          where: { key: "system_config" },
          data: { value: JSON.stringify(config) }
        });
      } catch (e) {}
    }

    return NextResponse.json({
      success: true,
      message: "JDDS operations resumed in hybrid mode."
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: error.message || "Failed to resume JDDS." },
      { status: 500 }
    );
  }
}
