import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Dev and production builds get separate output directories. `next dev`
  // deletes `BUILD_ID`, which invalidated the cached production build and made
  // every `black eclipse` / `npm run up` pay a full rebuild. Next sets
  // NODE_ENV=development for `next dev` and production for build/start, so
  // dev writes to `.next-dev` while production keeps `.next`. NEXT_DIST_DIR is
  // an explicit override.
  distDir: process.env.NEXT_DIST_DIR || (process.env.NODE_ENV === "development" ? ".next-dev" : ".next"),
  eslint: {
    ignoreDuringBuilds: true,
  },
  // The dev tools indicator floats over the bottom-left corner and intercepts
  // pointer events, which blocks automated UI checks (Playwright) against
  // controls underneath it.
  devIndicators: false,
  // A local hostname alias (e.g. http://blackeclipse, added to the Windows
  // hosts file and fronted by `scripts/local-proxy.js`) makes the browser's
  // dev origin differ from the dev server's own address, which Next would
  // otherwise flag as cross-origin for /_next/* and HMR. Listing it here keeps
  // dev requests same-origin. Dev only; unused by production builds.
  allowedDevOrigins: ["blackeclipse", "blackeclipse.local", "*.blackeclipse.local"],
  serverExternalPackages: ["better-sqlite3", "@prisma/adapter-better-sqlite3", "pdfjs-dist"],
  // Dev only. On a memory-constrained host a cold `next dev` compile of the
  // ~19k-module graph can take longer than webpack's default 120s client
  // chunk-load timeout. When that happens the browser gives up on a route chunk
  // and Next surfaces it as a `ChunkLoadError` / "Invalid or unexpected token"
  // overlay — which looks like a syntax error but is really a slow compile.
  // A longer dev budget lets a slow first load resolve instead of failing hard;
  // production chunks are prebuilt and unaffected.
  webpack: (config, { dev }) => {
    if (dev) config.output.chunkLoadTimeout = 300_000;
    return config;
  },
};

export default nextConfig;
