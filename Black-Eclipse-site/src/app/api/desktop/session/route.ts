import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";

// Desktop-session beacon used only when the app was launched from the desktop
// shortcut (the launcher sets BE_DESKTOP_HEARTBEAT_FILE). The page reports
// "alive" on load and "leave" on pagehide; the launcher watches the file and
// stops the dev server shortly after the tab closes. With the env var unset
// this route is an inert 204, so normal console/first-run usage is unaffected.
async function record(event: string) {
  const file = process.env.BE_DESKTOP_HEARTBEAT_FILE;
  if (!file) return;
  const payload = JSON.stringify({ event, at: Date.now() });
  try {
    await fs.mkdir(path.dirname(file), { recursive: true });
    await fs.writeFile(file, payload, "utf8");
  } catch {
    /* the launcher is gone or the path is not writable — nothing to do */
  }
}

export async function GET(request: Request) {
  const event = new URL(request.url).searchParams.get("event") === "leave" ? "leave" : "alive";
  await record(event);
  return new NextResponse(null, { status: 204 });
}

export async function POST(request: Request) {
  return GET(request);
}
