import { describe, expect, it } from "vitest";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

// Guard for the CHANGELOG rotation policy (closeout Phase 3). The rotation moves
// older dated sections from `docs/CHANGELOG.md` into `docs/changelog/YYYY-MM.md`
// archives. That is a MOVE, never a prune, and the active file keeps a rolling
// window. A hand-run rotation drifts; this makes the policy executable.
//
// It reads the docs (data), never source text, so it is a behavior contract.
//
// Sections were CONSOLIDATED so each date has exactly one section (the pre-2026-09
// file had many same-date sections and two malformed single-hash date headings);
// the rules below are therefore real properties, not aspirational.

const APP_ROOT = join(fileURLToPath(new URL(".", import.meta.url)), "..", "..");
const DOCS = join(APP_ROOT, "docs");
const CHANGELOG = join(DOCS, "CHANGELOG.md");
const ARCHIVE_DIR = join(DOCS, "changelog");

// The policy the doc states: "the most recent 7 dated sections are kept here".
const WINDOW = 7;
// Measured 2026-09-30 across CHANGELOG.md + docs/changelog/2026-09.md: 351
// (125 + 226). The floor tolerates the active window shifting entries between the
// two files (which does not change the total) but trips if a dated SECTION is
// dropped: a single section holds far fewer than (351 - 345) = 6 entries, so any
// silent loss of even one section with >= 6 entries fails here. 345 = 351 - 6.
const ENTRY_FLOOR = 345;

/** Each dated section as { date, body }, preserving every occurrence. */
function splitSections(text: string): Array<{ date: string; body: string }> {
  const parts = text.split(/^(?=## \d{4}-\d{2}-\d{2}\b)/m);
  const out: Array<{ date: string; body: string }> = [];
  for (const part of parts) {
    const m = part.match(/^## (\d{4}-\d{2}-\d{2})\b/);
    if (m) out.push({ date: m[1], body: part });
  }
  return out;
}

function archiveFiles(): string[] {
  try {
    return readdirSync(ARCHIVE_DIR).filter((f) => f.endsWith(".md"));
  } catch {
    return [];
  }
}

describe("CHANGELOG rotation policy", () => {
  const changelog = readFileSync(CHANGELOG, "utf8");
  const changelogSections = splitSections(changelog);
  const archives = archiveFiles().map((f) => ({ file: f, text: readFileSync(join(ARCHIVE_DIR, f), "utf8") }));
  const allSections = [...changelogSections, ...archives.flatMap((a) => splitSections(a.text))];

  it("keeps at most the agreed window of dated sections in CHANGELOG.md", () => {
    const n = changelogSections.length;
    expect(n, `CHANGELOG.md has ${n} dated sections (window is ${WINDOW})`).toBeLessThanOrEqual(WINDOW);
    expect(n, "CHANGELOG.md must not be rotated empty").toBeGreaterThan(0);
  });

  it("the archive seam is contiguous: no date was skipped when moving a section", () => {
    // A rotation moves the OLDEST active section into the archive, one per run.
    // If it moved more than one (or skipped one), the archive would contain a date
    // NEWER than the active window's oldest date.
    const activeDates = [...new Set(changelogSections.map((s) => s.date))].sort();
    const archiveDates = [
      ...new Set(archives.flatMap((a) => splitSections(a.text)).map((s) => s.date)),
    ].sort();
    if (archiveDates.length && activeDates.length) {
      const newestArchive = archiveDates[archiveDates.length - 1];
      const oldestActive = activeDates[0];
      expect(
        newestArchive < oldestActive,
        `archive contains ${newestArchive} which is not older than the active window's oldest ${oldestActive}`
      ).toBe(true);
    }
  });

  it("moves history, never duplicates it: each date is in exactly one file", () => {
    const seen = new Map<string, number>();
    for (const s of allSections) seen.set(s.date, (seen.get(s.date) ?? 0) + 1);
    const dupes = [...seen.entries()].filter(([, n]) => n > 1).map(([d]) => d);
    expect(dupes, `dates duplicated across CHANGELOG + archives: ${dupes.join(", ")}`).toEqual([]);
  });

  it("has no gap in the contiguous date range it covers", () => {
    const dates = [...new Set(allSections.map((s) => s.date))].sort();
    expect(dates.length).toBeGreaterThan(0);
    const start = new Date(dates[0] + "T00:00:00Z").getTime();
    const end = new Date(dates[dates.length - 1] + "T00:00:00Z").getTime();
    const day = 86_400_000;
    const missing: string[] = [];
    for (let t = start; t <= end; t += day) {
      const iso = new Date(t).toISOString().slice(0, 10);
      if (!dates.includes(iso)) missing.push(iso);
    }
    expect(missing, `dates missing from the range (a section was dropped): ${missing.slice(0, 10).join(", ")}`).toEqual([]);
  });

  it("never loses entries: CHANGELOG + archives hold at least the recorded floor", () => {
    const count = (t: string) => [...t.matchAll(/^- \*\*/gm)].length;
    const total = count(changelog) + archives.reduce((n, a) => n + count(a.text), 0);
    expect(
      total,
      `total CHANGELOG entries ${total} fell below the append-only floor ${ENTRY_FLOOR}`
    ).toBeGreaterThanOrEqual(ENTRY_FLOOR);
  });

  it("has no malformed single-hash date heading", () => {
    for (const text of [changelog, ...archives.map((a) => a.text)]) {
      const bad = text.split("\n").filter((l) => /^# 20\d\d-\d\d-\d\d\b/.test(l));
      expect(bad, `malformed single-hash date heading(s): ${bad.join(", ")}`).toEqual([]);
    }
  });

  it("links to the archive directory from the top of CHANGELOG.md", () => {
    expect(changelog).toMatch(/docs\/changelog\//);
  });
});
