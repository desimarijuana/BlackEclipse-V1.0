// ── Setup bundles ───────────────────────────────────────────────────────────
// A bundle is a STARTING POINT, never a hidden second configuration. Applying
// one writes the same ordinary source prefs the individual toggles write.
//
// No bundle enables an advanced/community source on its own. The Personal
// trader bundle is the only one that *offers* them, and the UI requires the
// explicit acknowledgement before flipping those toggles.

import type { BundleId, BundlesDef, SetupMode, SourceId } from "./types";
import { safeSourceDefaults } from "./defaults";

export const BUNDLES: BundlesDef[] = [
  {
    id: "research",
    label: "Research",
    description: "Open filings, macro and world events. No keys, no live prices.",
  },
  {
    id: "personal-trader",
    label: "Personal trader",
    description: "Adds community market sources for personal use only.",
  },
  {
    id: "commercial",
    label: "Commercial",
    description: "Open data only; connect a licensed market provider for prices.",
  },
  {
    id: "crypto",
    label: "Crypto",
    description: "Open data plus a crypto provider you connect.",
  },
  {
    id: "custom",
    label: "Custom",
    description: "Start from the safe defaults and choose each capability yourself.",
  },
];

export function bundleById(id: BundleId): BundlesDef | undefined {
  return BUNDLES.find((b) => b.id === id);
}

/** True when applying this bundle should ask for the advanced acknowledgement. */
export function bundleNeedsAcknowledgement(id: BundleId): boolean {
  return id === "personal-trader";
}

/**
 * The plain source map a bundle applies. Advanced sources stay off here; the
 * caller flips them only after the acknowledgement flag is set.
 */
export function bundleSources(id: BundleId, mode: SetupMode): Record<SourceId, boolean> {
  const base = safeSourceDefaults(mode);
  if (id === "research" || id === "commercial" || id === "custom") return base;

  if (id === "crypto") {
    // A crypto provider is connected later; the bundle only sets the intent by
    // leaving the safe included set on and crypto connected sources off.
    return base;
  }

  // personal-trader: keep open data on. The UI adds the advanced price sources
  // only after the acknowledgement checkbox, so the pure bundle stays safe.
  return base;
}

/** Capabilities a bundle highlights ("what you get"). */
export function bundleHighlights(id: BundleId): string[] {
  switch (id) {
    case "research":
      return ["Company filings", "US & global macro", "World events", "News headlines"];
    case "personal-trader":
      return ["Everything in Research", "Community price sources (personal use)"];
    case "commercial":
      return ["Everything in Research", "Bring a licensed market provider"];
    case "crypto":
      return ["Everything in Research", "Connect CoinMarketCap / CoinGecko"];
    case "custom":
      return ["Safe defaults", "You choose each capability"];
  }
}
