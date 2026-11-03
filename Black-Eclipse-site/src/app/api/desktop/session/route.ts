import { NextResponse } from "next/server";
import { promises as fs } from "fs";
import path from "path";

export const dynamic = "force-dynamic";

// Desktop-session beacon used only when the app was launched from the desktop
// shortcut (the launcher sets BE_DESKTOP_HEARTBEAT_FILE). The page reports
// "alive" on load / heartbeat and "leave" on pagehide; the launcher watches the
// file and stops the server shortly after the LAST tab closes. With the env var
// unset this route is an inert 204, so normal console/first-run usage is
// unaffected.
//
// The file is a refcount of live tabs, not one event: opening the app twice (or
// a second desktop tab) used to mean closing one tab stopped the server under
// the other one. Each page load sends its own id, so `leave` only removes that
// tab and the launcher stops when none are left.

type SessionState = {
  event?: string;
  at?: number;
  tabs?: Record<string, number>;
};

// Several tabs can beacon in the same instant. Serialize read-modify-write so
// one tab's heartbeat cannot be overwritten by another tab's `leave`.
let writeChain: Promise<void> = Promise.resolve();

async function readState(file: string): Promise<SessionState> {
  try {
    const parsed = JSON.parse(await fs.readFile(file, "utf8"));
    return parsed && typeof parsed === "object" ? (parsed as SessionState) : {};
  } catch {
    return {};
  }
}

async function record(event: string, tab: string | null) {
  const file = process.env.BE_DESKTOP_HEARTBEAT_FILE;
  if (!file) return;

  writeChain = writeChain
    .then(async () => {
      const now = Date.now();
      const prev = await readState(file);
      const tabs = { ...(prev.tabs ?? {}) };

      if (tab) {
        if (event === "leave") delete tabs[tab];
        else tabs[tab] = now;
      }

      // Bound the file for a long-lived app that opens many tabs: keep the 64
      // most recent ids. Older entries are stale by then anyway.
      const ids = Object.keys(tabs);
      if (ids.length > 64) {
        ids
          .sort((a, b) => tabs[a] - tabs[b])
          .slice(0, ids.length - 64)
          .forEach((id) => delete tabs[id]);
      }

      const payload: SessionState = { event, at: now };
      // A legacy page (cached build) sends no tab id. Preserve the old
      // single-tab semantics only while no refcounted tab exists.
      if (Object.keys(tabs).length > 0) payload.tabs = tabs;

      await fs.mkdir(path.dirname(file), { recursive: true });
      // Write-then-rename: the launcher polls this file every second and must
      // never read a half-written payload (which would look like "no tabs").
      const tmp = `${file}.tmp`;
      await fs.writeFile(tmp, JSON.stringify(payload), "utf8");
      await fs.rename(tmp, file);
    })
    .catch(() => {
      /* the launcher is gone or the path is not writable — nothing to do */
    });

  await writeChain;
}

function parse(request: Request) {
  const url = new URL(request.url);
  const event = url.searchParams.get("event") === "leave" ? "leave" : "alive";
  const raw = url.searchParams.get("tab");
  const tab = raw && /^[A-Za-z0-9_-]{1,64}$/.test(raw) ? raw : null;
  return { event, tab };
}

export async function GET(request: Request) {
  const { event, tab } = parse(request);
  await record(event, tab);
  return new NextResponse(null, { status: 204 });
}

export async function POST(request: Request) {
  const { event, tab } = parse(request);
  await record(event, tab);
  return new NextResponse(null, { status: 204 });
}
