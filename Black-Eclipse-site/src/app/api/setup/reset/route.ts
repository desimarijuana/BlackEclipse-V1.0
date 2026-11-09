import path from "node:path";
import { promises as fs } from "node:fs";
import { NextResponse } from "next/server";
import { guardMutation, rateLimit } from "@/lib/api-guard";
import { invalidateSettingsCache } from "@/lib/settings-route-cache";
import { invalidateSourcePreferenceCache } from "@/lib/data-source-preferences";
import { resetOnboarding, resetSetup } from "@/lib/setup/state";

export const dynamic = "force-dynamic";

const DATA_DIR = process.env.BE_DATA_DIR
  ? path.resolve(process.env.BE_DATA_DIR)
  : process.cwd();

function markerPath(): string {
  return path.join(DATA_DIR, ".black-eclipse", "reset-request.json");
}

async function readMarker(): Promise<Record<string, unknown> | null> {
  try {
    const raw = await fs.readFile(markerPath(), "utf8");
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === "object" ? parsed : null;
  } catch {
    return null;
  }
}

const SCOPE = ["onboarding", "setup", "factory"] as const;
type Scope = (typeof SCOPE)[number];

function isScope(value: unknown): value is Scope {
  return typeof value === "string" && (SCOPE as readonly string[]).includes(value);
}

/** GET /api/setup/reset — is a factory reset scheduled? */
export async function GET() {
  const marker = await readMarker();
  return NextResponse.json({ scheduled: Boolean(marker), marker });
}

/** DELETE /api/setup/reset — cancel a scheduled factory reset. */
export async function DELETE(request: Request) {
  const blocked = guardMutation(request, "setup-reset-cancel");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    await fs.rm(markerPath(), { force: true });
    return NextResponse.json({ ok: true, scheduled: false });
  } catch (err) {
    console.error("[api/setup/reset] cancel error:", err);
    return NextResponse.json({ error: "Failed to cancel the scheduled reset" }, { status: 500 });
  }
}

/**
 * POST /api/setup/reset
 *
 * `onboarding` and `setup` are config-only and safe to run in-process.
 * `factory` must NOT delete live SQLite from this process: it writes a marker
 * that doctor.js consumes on the next boot (before the DB guard opens jdds.db),
 * after optionally taking a backup. See docs/onboarding-plan.md §13.
 */
export async function POST(request: Request) {
  const blocked = guardMutation(request, "setup-reset");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });

  const limited = rateLimit("setup-reset", { limit: 4, windowMs: 60_000 });
  if (!limited.ok) {
    return NextResponse.json(
      { error: `Too many reset requests — retry in ${limited.retryAfterSec}s` },
      { status: 429 },
    );
  }

  const body = (await request.json().catch(() => ({}))) as Record<string, unknown>;
  if (!isScope(body.scope)) {
    return NextResponse.json({ error: "Unknown reset scope" }, { status: 400 });
  }

  const scope = body.scope;

  if (scope === "onboarding") {
    try {
      await resetOnboarding();
      invalidateSettingsCache();
      invalidateSourcePreferenceCache();
      return NextResponse.json({ ok: true, reload: "/?setup=1" });
    } catch (err) {
      console.error("[api/setup/reset] onboarding error:", err);
      return NextResponse.json({ error: "Failed to restart onboarding" }, { status: 500 });
    }
  }

  if (scope === "setup") {
    if (body.confirm !== "RESET") {
      return NextResponse.json(
        { error: "Type RESET to confirm clearing setup and API keys" },
        { status: 400 },
      );
    }
    try {
      await resetSetup();
      invalidateSettingsCache();
      invalidateSourcePreferenceCache();
      return NextResponse.json({ ok: true, reload: "/?setup=1" });
    } catch (err) {
      console.error("[api/setup/reset] setup error:", err);
      return NextResponse.json({ error: "Failed to reset setup" }, { status: 500 });
    }
  }

  // Factory reset: schedule it; never touch live databases here.
  if (body.confirm !== "WIPE") {
    return NextResponse.json(
      { error: "Type WIPE to confirm the factory reset" },
      { status: 400 },
    );
  }

  const marker = {
    scope: "factory",
    requestedAt: new Date().toISOString(),
    backup: body.backup !== false,
    includeEnv: body.includeEnv === true,
    requestedBy: "settings",
  };

  try {
    await fs.mkdir(path.dirname(markerPath()), { recursive: true });
    await fs.writeFile(markerPath(), JSON.stringify(marker, null, 2), "utf8");
    return NextResponse.json({
      ok: true,
      scheduled: true,
      backup: marker.backup,
      includeEnv: marker.includeEnv,
      command: "black reset --factory",
      message:
        "Reset scheduled. Restart Eclipse to finish (or run `black reset --factory`).",
    });
  } catch (err) {
    console.error("[api/setup/reset] factory schedule error:", err);
    return NextResponse.json({ error: "Failed to schedule the factory reset" }, { status: 500 });
  }
}
