import { NextResponse } from "next/server";
import { guardMutation } from "@/lib/api-guard";
import {
  clearServerTheme,
  getServerThemeState,
  setServerTheme,
} from "@/lib/theme/server";

export const dynamic = "force-dynamic";

// /api/theme — the APP-WIDE Eclipse theme (Settings › Customization).
//
// The theme lives on the server (JDDS `SystemConfig`) so every browser origin
// (localhost:3000, 127.0.0.1:3000, https://blackeclipse) and every device shows
// the SAME look. The client store keeps a per-origin `localStorage` cache for
// instant first paint but treats this as the source of truth.
//
// GET     → { theme: EclipseTheme | null, initialized: boolean }  (null = shipped default)
// PUT     { theme }  → { success, theme }    (save app-wide)
// DELETE  → { success }                       (reset to shipped default)

export async function GET() {
  try {
    return NextResponse.json(await getServerThemeState());
  } catch (err) {
    console.error("[api/theme] GET error:", err);
    return NextResponse.json({ error: "Failed to load theme" }, { status: 500 });
  }
}

export async function PUT(request: Request) {
  const blocked = guardMutation(request, "theme");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    const body = (await request.json().catch(() => ({}))) as { theme?: unknown };
    const theme = await setServerTheme(body.theme);
    return NextResponse.json({ success: true, theme });
  } catch (err) {
    console.error("[api/theme] PUT error:", err);
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Failed to save theme" },
      { status: 500 },
    );
  }
}

export async function DELETE(request: Request) {
  const blocked = guardMutation(request, "theme");
  if (blocked) return NextResponse.json(blocked.body, { status: blocked.status });
  try {
    await clearServerTheme();
    return NextResponse.json({ success: true });
  } catch (err) {
    console.error("[api/theme] DELETE error:", err);
    return NextResponse.json({ error: "Failed to reset theme" }, { status: 500 });
  }
}
