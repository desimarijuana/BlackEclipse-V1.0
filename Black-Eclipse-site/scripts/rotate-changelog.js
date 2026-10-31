#!/usr/bin/env node
/*
 * The CHANGELOG rotation - the file keeps a rolling window, and the archive
 * step is a SCRIPT, not a manual edit.
 *
 * Round 3 / W7 (ADR-H288). `docs/CHANGELOG.md` documents a rolling window of
 * the most recent 7 dated sections, with older sections MOVED - never deleted -
 * into `docs/changelog/YYYY-MM.md`. That was a promise nobody kept by hand, so
 * it is now a command.
 *
 * It is SAFE to run at any time: it archives the OLDEST sections only, and it
 * never touches the current window.
 *
 * Run: `npm run rotate:changelog` (dry-run by default; `--write` to apply).
 */

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const CHANGELOG = path.join(ROOT, "docs", "CHANGELOG.md");
const ARCHIVE_DIR = path.join(ROOT, "docs", "changelog");
const KEEP = 7;

function main() {
  const write = process.argv.includes("--write");
  if (!fs.existsSync(CHANGELOG)) {
    console.error(`rotate-changelog: ${CHANGELOG} is missing.`);
    process.exit(1);
  }
  const text = fs.readFileSync(CHANGELOG, "utf8");
  // A dated section starts at a `## YYYY-MM-DD` heading.
  const marks = [];
  const re = /^## (\d{4}-\d{2}-\d{2})\s*$/gm;
  let m;
  while ((m = re.exec(text)) !== null) marks.push({ date: m[1], start: m.index });
  console.log("CHANGELOG rotation");
  console.log(`  ${marks.length} dated sections, keeping the newest ${KEEP}`);
  if (marks.length <= KEEP) {
    console.log("  [OK  ] nothing to archive.");
    return;
  }
  // Sections are NEWEST FIRST. Keep the first KEEP and archive the tail.
  const cutoff = marks[KEEP].start;
  const head = text.slice(0, cutoff);
  const archived = marks.slice(KEEP);
  const byMonth = new Map();
  for (const section of archived) {
    const month = section.date.slice(0, 7);
    if (!byMonth.has(month)) byMonth.set(month, []);
    byMonth.get(month).push(section);
  }
  for (const [month, sections] of byMonth) {
    const start = sections[0].start;
    // The block ends where the section AFTER the group begins (or EOF). Look
    // it up in the full mark list; a group's sections are contiguous.
    const lastIndex = KEEP + archived.indexOf(sections[sections.length - 1]);
    const end = lastIndex + 1 < marks.length ? marks[lastIndex + 1].start : text.length;
    const block = text.slice(start, end).trimEnd();
    const target = path.join(ARCHIVE_DIR, `${month}.md`);
    const existing = fs.existsSync(target) ? fs.readFileSync(target, "utf8").trimEnd() : "";
    const merged = existing
      ? `${existing}\n\n${block}\n`
      : `# ${month}\n\n${block}\n`;
    console.log(`  ${month}: ${sections.length} section(s)${write ? " -> archived" : " (dry run)"}`);
    if (write) {
      fs.mkdirSync(ARCHIVE_DIR, { recursive: true });
      fs.writeFileSync(target, merged, "utf8");
    }
  }
  if (write) {
    fs.writeFileSync(CHANGELOG, head, "utf8");
    console.log(`\nRotated ${archived.length} section(s) into docs/changelog/.`);
  } else {
    console.log("\nDry run. Re-run with --write to apply.");
  }
}

main();
