import type { NextConfig } from "next";

const nextConfig: NextConfig = {
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
