#!/usr/bin/env node
/*
 * ADR number + shape check - the decision record must be unambiguous.
 *
 * Round 3 / W7 (ADR-H288). The harness decision series had SEVEN duplicate
 * numbers and two gaps: two different decisions could share a number, so a
 * reference to "ADR-H242" named two different things. A decision record is
 * only useful if a reference resolves to exactly one decision.
 *
 * This fails when:
 *   - a number appears twice;
 *   - the sequence has a gap that is not explicitly reserved;
 *   - an entry does not carry the canonical shape.
 *
 * It NEVER renumbers anything. Renumbering is a judgement call (which entry
 * keeps the old number, and which title fits the new one) and belongs to a
 * human; this script only reports.
 *
 * Run: `npm run check:adr` (also part of `npm run check:all`).
 */

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const DECISIONS = path.join(ROOT, "docs", "harness", "decisions.md");

/*
 * Numbers that were withdrawn during the Round 3 rework and never written.
 * A gap that is RESERVED is intentional; a gap that is not is a mistake.
 */
const RESERVED = new Set([108, 117, 124, 125, 146]);

/*
 * The canonical shape is enforced FROM THIS NUMBER ONWARD. The entries below
 * it were written over months, by several hands, and some of them do not
 * carry every section - rewriting them would mean inventing a rationale for
 * decisions this change did not make. So the legacy record is REPORTED (so
 * it is visible and countable) and the gate applies to everything written
 * from here on. A new entry that breaks the shape fails the build.
 */
const SHAPE_FROM = 295;

/* The canonical shape of an entry. */
const REQUIRED_SECTIONS = ["**Decision.**", "**Why.**", "**Consequences.**"];

function readDecisions() {
  if (!fs.existsSync(DECISIONS)) {
    console.error(`ADR check: ${DECISIONS} is missing.`);
    process.exit(1);
  }
  return fs.readFileSync(DECISIONS, "utf8");
}

function parse(text) {
  const lines = text.split(/\r?\n/);
  const entries = [];
  for (let i = 0; i < lines.length; i += 1) {
    const m = /^##\s+ADR-H(\d+)\s*[-–—]\s*(.+)$/.exec(lines[i]);
    if (!m) continue;
    const number = Number(m[1]);
    const title = m[2].trim();
    // The body of this entry: up to the next `## ADR-H` heading.
    const body = [];
    for (let j = i + 1; j < lines.length; j += 1) {
      if (/^##\s+ADR-H\d+/.test(lines[j])) break;
      body.push(lines[j]);
    }
    entries.push({ number, title, line: i + 1, body: body.join("\n") });
  }
  return entries;
}

function main() {
  const entries = parse(readDecisions());
  const problems = [];

  if (!entries.length) {
    console.error("ADR check: no ADR-H entries found.");
    process.exit(1);
  }

  // 1. Duplicates.
  const byNumber = new Map();
  for (const entry of entries) {
    const seen = byNumber.get(entry.number) || [];
    seen.push(entry);
    byNumber.set(entry.number, seen);
  }
  for (const [number, seen] of byNumber) {
    if (seen.length > 1) {
      problems.push(
        `ADR-H${number} appears ${seen.length} times (lines ${seen.map((e) => e.line).join(", ")}). ` +
          `A number must name exactly one decision.`
      );
    }
  }

  // 2. Gaps.
  const numbers = [...byNumber.keys()].sort((a, b) => a - b);
  const first = numbers[0];
  const last = numbers[numbers.length - 1];
  for (let n = first; n <= last; n += 1) {
    if (!byNumber.has(n) && !RESERVED.has(n)) {
      problems.push(
        `ADR-H${n} is missing between H${first} and H${last}. Reserve it in the script ` +
          `if it was withdrawn on purpose - a silent gap is how a reference stops resolving.`
      );
    }
  }

  // 3. Shape. Enforced from SHAPE_FROM onward; the legacy record is reported.
  const legacy = [];
  for (const entry of entries) {
    const missing = REQUIRED_SECTIONS.filter((section) => !entry.body.includes(section));
    if (!missing.length) continue;
    if (entry.number < SHAPE_FROM) {
      legacy.push(`ADR-H${entry.number} (line ${entry.line}) is missing ${missing.join(", ")}`);
      continue;
    }
    problems.push(
      `ADR-H${entry.number} (line ${entry.line}) is missing ${missing.join(", ")} - the shape is ` +
        `\`## ADR-H<n> - Title\` + ${REQUIRED_SECTIONS.join(" + ")}.`
    );
  }

  console.log("ADR record check");
  console.log(`  ${entries.length} entries, H${first}..H${last}, ${RESERVED.size} reserved`);
  if (problems.length) {
    for (const problem of problems) console.error(`  [FAIL] ${problem}`);
    console.error(`\nADR check FAILED: ${problems.length} problem(s).`);
    process.exit(1);
  }
  if (legacy.length) {
    console.log(`  [note] ${legacy.length} legacy entr(ies) below H${SHAPE_FROM} do not carry the full shape.`);
    for (const note of legacy) console.log(`         ${note}`);
  }
  console.log("  [OK  ] every number names exactly one decision, the sequence is contiguous,");
  console.log(`         and every entry from H${SHAPE_FROM} on carries Decision / Why / Consequences.`);
  console.log("\nADR check passed.");
}

main();
