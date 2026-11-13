import type { NextConfig } from "next";

const isDev = process.env.NODE_ENV === "development";

// Baseline response headers for every route. They are cheap, additive and do
// not depend on the app's rendering: nosniff stops MIME confusion, SAMEORIGIN
// stops clickjacking while still allowing the app's own iframes, the referrer
// policy keeps query strings (which can carry tokens) out of third-party logs,
// and Permissions-Policy leaves camera/microphone available to this origin only
// (voice dictation) while denying geolocation.
const securityHeaders: { key: string; value: string }[] = [
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "X-Frame-Options", value: "SAMEORIGIN" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(self), microphone=(self), geolocation=()" },
];
// HSTS is only meaningful over HTTPS and only safe once the deployment actually
// terminates TLS; a loopback http:// install ignores it. No includeSubDomains:
// a LAN hostname may legitimately have siblings that are not upgraded.
if (!isDev) {
  securityHeaders.push({ key: "Strict-Transport-Security", value: "max-age=31536000" });
}

const nextConfig: NextConfig = {
  // Turbopack names a dev chunk after the MODULE it serves (e.g.
  // `src_components_screens_a6343f43._.js`), not after the bytes it holds. When
  // a module is edited, renamed or deleted, the bytes behind that same URL
  // change while the URL stays put. Marking those responses `immutable` pins
  // the browser to the OLD bytes, and the next load asks the runtime for a
  // module factory the server no longer has - the "the module factory is not
  // available. It might have been deleted in an HMR update" overlay, with a
  // blank screen behind it.
  //
  // So dev chunks REVALIDATE: the server already sends `ETag`/`Last-Modified`,
  // so a second tab gets a cheap 304 instead of re-downloading the whole
  // ~20 MB client graph, and a changed chunk is always fetched fresh.
  // Production is unaffected: real builds are content-hashed and immutable.
  headers: async () => {
    const rules: { source: string; headers: { key: string; value: string }[] }[] = [
      { source: "/:path*", headers: securityHeaders },
    ];
    if (isDev) {
      rules.push({
        source: "/_next/static/chunks/:path*",
        headers: [{ key: "Cache-Control", value: "public, max-age=0, must-revalidate" }],
      });
    }
    return rules;
  },
  experimental: {
    // The icon surface re-exports ~250 icons from a 9k-icon barrel. Without
    // this, the full icon definition set (~1.5 MB) lands in the boot chunk.
    optimizePackageImports: ["@phosphor-icons/react"],
  },
  // Dev and production builds get separate output directories. `next dev`
  // deletes `BUILD_ID`, which invalidated the cached production build and made
  // every rebuild paid a full rebuild. Next sets
  // NODE_ENV=development for `next dev` and production for build/start, so
  // dev writes to `.next-dev` while production keeps `.next`. NEXT_DIST_DIR is
  // an explicit override (the desktop channels use it).
  distDir: process.env.NEXT_DIST_DIR || (process.env.NODE_ENV === "development" ? ".next-dev" : ".next"),
  // `BE_STANDALONE=1` switches the build to a self-contained output for the
  // desktop payload (docs/desktop-app-plan.md §6). Unset by default, so the
  // browser path's build output is byte-for-byte what it was before.
  output: process.env.BE_STANDALONE === "1" ? "standalone" : undefined,
  eslint: {
    ignoreDuringBuilds: true,
  },
  // The dev tools indicator floats over the bottom-left corner and intercepts
  // pointer events, which blocks automated UI checks (Playwright) against
  // controls underneath it.
  devIndicators: false,
  serverExternalPackages: ["better-sqlite3", "@prisma/adapter-better-sqlite3", "pdfjs-dist"],
  // The code-workspace feature keeps COPIES of the repo under
  // `.black-eclipse/code-workspaces/`. They are runtime state, not source, and
  // a copy that is deleted while the build walks it used to fail the whole
  // build with "EPERM: operation not permitted, scandir ...". They are never
  // traced into the output.
  outputFileTracingExcludes: {
    "*": [".black-eclipse/**/*"],
  },
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
