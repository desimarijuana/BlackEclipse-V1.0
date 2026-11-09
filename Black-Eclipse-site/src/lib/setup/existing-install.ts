// ── Existing-install detection ──────────────────────────────────────────────
// Onboarding must appear for a genuinely new install, never as a surprise on an
// upgrade. We look for evidence that an operator already configured or used the
// app. A brand-new JDDS has none of these keys.
//
// Deliberately conservative: if any prior signal exists, we mark the install
// "migrated" and never show the first-run gate. The user can always re-run
// setup from Settings or the CLI.

import { prisma } from "@/lib/db";

/** SystemConfig keys that only an operator interaction writes. */
const PRIOR_CONFIG_KEYS = [
  "llm_config",
  "provider_keys_v1",
  "news_feeds",
  "app_preferences",
  "eclipse_theme",
  "ui_catalog_v1",
];

export interface InstallProbe {
  isNew: boolean;
  reasons: string[];
}

export async function probeInstall(): Promise<InstallProbe> {
  const reasons: string[] = [];

  try {
    const rows = await prisma.systemConfig.findMany({
      where: { key: { in: PRIOR_CONFIG_KEYS } },
      select: { key: true },
    });
    if (rows.length > 0) {
      reasons.push(`system config: ${rows.map((r) => r.key).join(", ")}`);
    }
  } catch {
    // A missing/unreadable table is not evidence of an existing install; the
    // rest of boot will surface a real DB problem. Stay on the new-install path.
  }

  try {
    // Auth users exist only after a first-run account was created.
    const users = await prisma.$queryRawUnsafe<Array<{ n: number }>>(
      "SELECT COUNT(*) AS n FROM AuthUser",
    );
    const n = Number(users?.[0]?.n ?? 0);
    if (n > 0) reasons.push(`auth users: ${n}`);
  } catch {
    /* AuthUser table absent = no auth configured. */
  }

  return { isNew: reasons.length === 0, reasons };
}
