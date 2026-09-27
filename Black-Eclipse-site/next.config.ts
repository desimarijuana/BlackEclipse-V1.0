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
  serverExternalPackages: ["better-sqlite3", "@prisma/adapter-better-sqlite3"],
};

export default nextConfig;
