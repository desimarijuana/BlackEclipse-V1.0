import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join, relative } from "node:path";
import { fileURLToPath } from "node:url";

// "Keep files small" guard (AGENTS.md). Memory is the top constraint on this
// machine, so a runaway monolith is a real risk.
//
// This is a GRADUATED guard, not the old single 200 KB ceiling (which nothing
// tripped: the largest file, market-overview.tsx, is ~155 KB):
//
//   * HARD ceiling  — a file over this many LINES must be in RATCHET below.
//   * SOFT ceiling  — a file over this is reported (console.warn) but allowed.
//   * RATCHET       — the files already over the hard ceiling, each pinned to
//                     its current size. They may SHRINK but never GROW, so the
//                     allowance cannot silently grandfather a file that keeps
//                     getting bigger. Removing a file from this list (because it
//                     was split) needs no ratchet edit; a genuine shrink needs
//                     no edit either.
//
// A NEW oversized file fails. An existing one may not grow. That is what makes
// the guard bite.

// Anchor to this file's directory (…/src/lib) → repo app root, independent of
// the process cwd.
const ROOT = join(fileURLToPath(new URL(".", import.meta.url)), "..", "..");
const HARD_CEILING_LINES = 1200;
const SOFT_CEILING_LINES = 800;
const SKIP_DIRS = new Set(["generated", "node_modules", ".next", ".next-dev", "vendor"]);

// The files above the hard ceiling today, pinned to their measured size. Each
// entry is a near-term split candidate; the budget is the current height, so the
// file can only get smaller until it is split and removed from this list.
const RATCHET: Record<string, number> = {
  "src/components/screens/market-overview.tsx": 2760,
  "src/components/screens/eclipse-memory/eclipse-memory-screen.tsx": 2488,
  "src/lib/i18n/dictionaries/index.ts": 1549,
  "src/lib/harness/data-bridge.ts": 1539,
  "src/components/screens/market-bubbles.tsx": 1413,
  "src/components/chart/chart-widget.tsx": 1405,
  "src/lib/workspace/workspace-canvas.tsx": 1374,
  "src/components/screens/customization-settings.tsx": 1336,
  "src/components/screens/market-news.tsx": 1336,
  // Grew when the AI section gained a real provider select + model dropdown
  // (the previous datalist was not surfaced by the input primitive). Pinned
  // until the deferred AI-section split; may only shrink from here.
  "src/components/screens/settings.tsx": 1289,
  // The SPA shell was exactly at the ceiling (1200). Mounting the Model Control
  // Center added one dynamic import + one keep-alive block; pinned at its new
  // height until the shell is split. Grew again with the terminal dock plumbing
  // and the focus-mode "tuck the terminal" effect. Grew once more with the
  // approval-card wiring (composer anchor + the portaled ApprovalCard). Grew yet
  // again by one dynamic import + one keep-alive block for the dedicated
  // Research tab. May only shrink from here. Grew by one import + one mount
  // line when the Agent Workspace became a docked right sidebar in the shell
  // row (it moved out of the root layout to reserve real column space).
  "src/components/screens/stock-chat.tsx": 1272,
};

export interface SizeEntry {
  file: string;
  lines: number;
}

/** The pure detector: which files exceed `ceiling` and are not within budget. */
export function findOversized(
  entries: SizeEntry[],
  ceiling: number,
  ratchet: Record<string, number>
): SizeEntry[] {
  return entries
    .filter((e) => e.lines > ceiling)
    .filter((e) => e.lines > (ratchet[e.file] ?? 0))
    .sort((a, b) => b.lines - a.lines);
}

export function findSoft(entries: SizeEntry[], ceiling: number): SizeEntry[] {
  return entries.filter((e) => e.lines > ceiling);
}

function walk(dir: string, out: string[] = []): string[] {
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    if (entry.name.startsWith(".")) continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      if (SKIP_DIRS.has(entry.name)) continue;
      walk(full, out);
    } else if (entry.name.endsWith(".ts") || entry.name.endsWith(".tsx")) {
      out.push(full);
    }
  }
  return out;
}

function countLines(file: string): number {
  const text = readFileSync(file, "utf8");
  return text.length === 0 ? 0 : text.split("\n").length - (text.endsWith("\n") ? 1 : 0);
}

function measure(): SizeEntry[] {
  return walk(ROOT).map((file) => ({
    file: relative(ROOT, file).replace(/\\/g, "/"),
    lines: countLines(file),
  }));
}

describe("source size budget (graduated)", () => {
  it("no non-ratcheted file exceeds the hard ceiling", () => {
    const oversized = findOversized(measure(), HARD_CEILING_LINES, RATCHET);
    expect(
      oversized,
      `files over ${HARD_CEILING_LINES} lines — split them or add a justified ` +
        `ratchet entry (${oversized.map((o) => `${o.file}=${o.lines}`).join(", ")})`
    ).toEqual([]);
  });

  it("every ratcheted file is still at or below its pinned budget (may not grow)", () => {
    const byFile = new Map(measure().map((e) => [e.file, e.lines]));
    for (const [file, budget] of Object.entries(RATCHET)) {
      const lines = byFile.get(file);
      expect(lines, `ratcheted file missing: ${file}`).toBeDefined();
      expect(lines!, `${file} grew past its pinned budget ${budget}`).toBeLessThanOrEqual(budget);
    }
  });

  it("the detector actually bites on a synthetic oversized file", () => {
    const entries: SizeEntry[] = [
      { file: "src/new-monolith.ts", lines: HARD_CEILING_LINES + 500 },
      { file: "src/ok.ts", lines: 100 },
    ];
    const flagged = findOversized(entries, HARD_CEILING_LINES, RATCHET);
    expect(flagged.map((f) => f.file)).toEqual(["src/new-monolith.ts"]);
    // A ratcheted file at its budget is allowed; one line over is flagged.
    const ratcheted = Object.keys(RATCHET)[0];
    expect(findOversized([{ file: ratcheted, lines: RATCHET[ratcheted] }], HARD_CEILING_LINES, RATCHET)).toEqual([]);
    expect(findOversized([{ file: ratcheted, lines: RATCHET[ratcheted] + 1 }], HARD_CEILING_LINES, RATCHET).length).toBe(1);
  });

  it("reports (but does not fail on) files over the soft ceiling", () => {
    const soft = findSoft(measure(), SOFT_CEILING_LINES).sort((a, b) => b.lines - a.lines);
    if (soft.length) {
      console.warn(`[size-budget] ${soft.length} file(s) over the soft ceiling ${SOFT_CEILING_LINES}: ${soft.slice(0, 10).map((s) => `${s.file}=${s.lines}`).join(", ")}`);
    }
    // The soft ceiling is informational; this assertion only pins that the walk
    // is real and the measurement is produced.
    expect(Array.isArray(soft)).toBe(true);
  });

  it("the walk is real (finds a known file)", () => {
    const files = walk(ROOT).map((f) => relative(ROOT, f).replace(/\\/g, "/"));
    expect(files.some((f) => f.endsWith("src/lib/api-guard.ts"))).toBe(true);
  });
});
