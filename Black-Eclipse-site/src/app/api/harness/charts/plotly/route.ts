import { NextResponse } from "next/server";
import { createReadStream, existsSync, statSync } from "node:fs";
import { execFileSync } from "node:child_process";
import { Readable } from "node:stream";
import { findPython } from "@/lib/scraper/fetchers/python";

// GET /api/harness/charts/plotly.js — the chart library, served ONCE.
//
// The chat's charts are real charts: the engine authors them in Python and
// this library draws them in the browser as vector SVG (zoom, pan, hover, a
// legend). The library is ~4.7 MB, so it is served from the Python package
// that already ships it (never vendored into git, never fetched from a CDN -
// the app works offline) and the browser caches it.
//
// The file's location is resolved from the runtime itself, not guessed: the
// vendored interpreter, a managed site-packages directory, or a system Python
// all work. A guess-only lookup made the live chart unavailable on every
// install whose plotly lived somewhere else (macOS/Linux, a custom venv).
//
// If plotly is genuinely absent the response is an explicit 503 and the chat
// falls back to the drawn picture.
//
// This route must stay DYNAMIC: `force-static` froze the build-time answer, so
// a plotly package installed after `next build` was never seen (and a build
// performed before `postinstall` finished cached a permanent 503).
export const dynamic = "force-dynamic";

let resolvedPath: string | null | undefined;
let resolvedAt = 0;
/** A miss is retried: plotly may be installed after the app started. */
const MISS_TTL_MS = 60_000;

function candidatePaths(): string[] {
  const paths: string[] = [];
  const root = process.cwd();
  for (const base of [
    `${root}/scripts/vendor/python/Lib/site-packages/plotly/package_data`,
    `${root}/scripts/vendor/python/lib/site-packages/plotly/package_data`,
    `${root}/.black-eclipse/python/site-packages/plotly/package_data`,
  ]) {
    paths.push(`${base}/plotly.min.js`);
  }
  return paths;
}

/** Ask the interpreter that runs the chart engine where its plotly lives. */
async function fromRuntime(): Promise<string | null> {
  try {
    const py = await findPython("plotly");
    if (!py) return null;
    const out = execFileSync(
      py.cmd,
      [
        "-c",
        "import os, plotly; print(os.path.join(os.path.dirname(plotly.__file__), 'package_data', 'plotly.min.js'))",
      ],
      { encoding: "utf8", timeout: 20_000, windowsHide: true },
    );
    const file = out.trim().split(/\r?\n/).pop() ?? "";
    return file && existsSync(file) ? file : null;
  } catch {
    return null;
  }
}

async function libraryPath(): Promise<string | null> {
  const now = Date.now();
  if (resolvedPath !== undefined && (resolvedPath !== null || now - resolvedAt < MISS_TTL_MS)) {
    return resolvedPath;
  }
  for (const candidate of candidatePaths()) {
    if (existsSync(candidate)) {
      resolvedPath = candidate;
      resolvedAt = now;
      return candidate;
    }
  }
  resolvedPath = await fromRuntime();
  resolvedAt = Date.now();
  return resolvedPath;
}

export async function GET() {
  const file = await libraryPath();
  if (!file) {
    return NextResponse.json(
      { status: "UNAVAILABLE", error: "the chart library is not installed" },
      { status: 503 },
    );
  }
  const stat = statSync(file);
  const stream = Readable.toWeb(createReadStream(file)) as unknown as ReadableStream;
  return new NextResponse(stream, {
    status: 200,
    headers: {
      "Content-Type": "application/javascript; charset=utf-8",
      "Content-Length": String(stat.size),
      // The library never changes for a given install: cache it hard.
      "Cache-Control": "public, max-age=31536000, immutable",
    },
  });
}
