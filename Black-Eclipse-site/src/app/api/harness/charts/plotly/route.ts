import { NextResponse } from "next/server";
import { createReadStream, existsSync, statSync } from "node:fs";
import { Readable } from "node:stream";

// GET /api/harness/charts/plotly.js — the chart library, served ONCE.
//
// The chat's charts are real charts: the engine authors them in Python and
// this library draws them in the browser as vector SVG (zoom, pan, hover, a
// legend). The library is ~4.7 MB, so it is served from the Python package
// that already ships it (never vendored into git, never fetched from a CDN -
// the app works offline) and the browser caches it.
//
// The file is read from the runtime's own environment: the vendored interpreter
// or the managed site-packages. If it is missing, the response is an explicit
// 503 and the chat falls back to the drawn picture.

export const dynamic = "force-static";
export const revalidate = false;

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

export async function GET() {
  for (const path of candidatePaths()) {
    if (!existsSync(path)) continue;
    const stat = statSync(path);
    const stream = Readable.toWeb(createReadStream(path)) as unknown as ReadableStream;
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
  return NextResponse.json(
    { status: "UNAVAILABLE", error: "the chart library is not installed" },
    { status: 503 },
  );
}
