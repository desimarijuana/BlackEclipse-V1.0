#!/usr/bin/env tsx
// Generates docs/data-sources.md from the ONE setup catalog. Run with
// `npm run docs:data-sources`; CI runs the --check form so the page cannot drift.
import { readFileSync, writeFileSync } from "node:fs";
import path from "node:path";
import { SOURCES, commercialSentence } from "../src/lib/setup/source-catalog";

const OUT = path.join(process.cwd(), "docs", "data-sources.md");

const TIER_LABEL = {
  included: "Included — open data, no account",
  connected: "Connect your own — your key/account",
  advanced: "Advanced / community — personal use only, off by default",
} as const;

function render(): string {
  const lines: string[] = [
    "---",
    "title: Data Sources & Licensing",
    "status: Current",
    `last-verified: ${new Date().toISOString().slice(0, 10)}`,
    "---",
    "",
    "# Data Sources & Licensing",
    "",
    "> Generated from `src/lib/setup/source-catalog.ts`. Do not edit by hand; run",
    "> `npm run docs:data-sources`. This is an informational snapshot, not legal",
    "> advice. Verify each provider's current terms before a paid launch.",
    "",
    "## What the three tiers mean",
    "",
    "- **Included** — ships with Eclipse, no account, redistributable with the stated condition.",
    "- **Connect your own** — the user supplies their own key/account; the provider's terms apply to them.",
    "- **Advanced / community** — personal-use sources. Off by default; never part of a commercial default.",
    "",
  ];

  for (const tier of ["included", "connected", "advanced"] as const) {
    const rows = SOURCES.filter((s) => s.tier === tier);
    if (rows.length === 0) continue;
    lines.push(`## ${TIER_LABEL[tier]}`, "");
    lines.push("| Source | Commercial | What it powers | Default | Terms |");
    lines.push("|---|---|---|---|---|");
    for (const s of rows) {
      const terms = s.termsUrl ? `[terms](${s.termsUrl})` : "—";
      lines.push(
        `| ${s.label} | ${commercialSentence(s.commercial)} | ${s.powers.join(", ")} | ${s.defaultOn ? "On" : "Off"} | ${terms} |`,
      );
    }
    lines.push("");
  }

  lines.push(
    "## Attribution",
    "",
    "The app displays provider attribution on the screens that use the data. Keep it visible:",
    "",
    "- FRED — “Courtesy of FRED, Federal Reserve Bank of St. Louis”",
    "- World Bank — CC BY 4.0",
    "- Eurostat / ECB",
    "- GDELT — The GDELT Project",
    "- NASA FIRMS",
    "- CoinGecko — “Data provided by CoinGecko” (paid plan)",
    "",
    "## Changing a source",
    "",
    "Add or edit it in `src/lib/setup/source-catalog.ts`, then run",
    "`npm run docs:data-sources`. Enforcement lives in",
    "`src/lib/data-source-preferences.ts`; a new toggle is not real until its",
    "fetch path consults it.",
    "",
  );
  return lines.join("\n");
}

const next = render();
// The front matter stamps TODAY when the page is written, so comparing it
// verbatim makes `--check` fail on any repository that was not regenerated that
// morning - a gate that cannot stay green. It also contradicts the docs rule
// that `last-verified` only moves when the page is re-read. Normalise it on both
// sides: real drift still fails, a passing day does not.
const withoutDate = (text: string) =>
  text.replace(/^last-verified: .*$/m, "last-verified: <date>");

const check = process.argv.includes("--check");
if (check) {
  let current = "";
  try {
    current = readFileSync(OUT, "utf8");
  } catch {
    console.error("[data-sources] docs/data-sources.md is missing; run npm run docs:data-sources");
    process.exit(1);
  }
  if (withoutDate(current) !== withoutDate(next)) {
    console.error("[data-sources] docs/data-sources.md is out of date; run npm run docs:data-sources");
    process.exit(1);
  }
  console.log("[data-sources] up to date");
} else {
  writeFileSync(OUT, next, "utf8");
  console.log(`[data-sources] wrote ${OUT}`);
}
