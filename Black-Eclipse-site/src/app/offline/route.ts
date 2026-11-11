// `/offline` — the page the service worker shows when the local app is not
// running. It is a plain HTML response (no React, no client bundle) so it keeps
// working when nothing else does, and it is rendered with the user's saved
// app-wide theme.
//
// `public/sw.js` precaches this URL; this route only has to produce the current
// theme's version of it. `cache-control: no-store` keeps the cached copy honest
// — the worker refreshes it from here after a successful load.

import fs from "node:fs";
import path from "node:path";
import { DEFAULT_ECLIPSE_THEME } from "@/lib/theme/tokens";
import { getServerTheme } from "@/lib/theme/server";
import { renderOfflinePage } from "@/lib/offline/page";

export const dynamic = "force-dynamic";

const WORDMARK = path.join(process.cwd(), "public", "branding", "LOGO-WORDMARK.svg");

function readWordmark(): string {
  try {
    return fs.readFileSync(WORDMARK, "utf8");
  } catch {
    // A missing wordmark degrades to the monogram badge in the page builder.
    return "";
  }
}

export async function GET() {
  let theme = DEFAULT_ECLIPSE_THEME;
  try {
    theme = (await getServerTheme()) ?? DEFAULT_ECLIPSE_THEME;
  } catch {
    // The DB may be unavailable exactly when this page is needed; the shipped
    // theme is a faithful fallback.
  }
  return new Response(renderOfflinePage({ theme, wordmark: readWordmark() }), {
    status: 200,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
    },
  });
}
