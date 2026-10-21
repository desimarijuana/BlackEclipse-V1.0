#!/usr/bin/env node
/*
 * The harness size budget - the TOTAL ceiling, enforced.
 *
 * Round 3 / W7 (ADR-H288). `python/tests/test_size_budget.py` already
 * ratchets the PER-MODULE size of the harness: a file may not grow past its
 * pinned budget. That bounds a file's growth but not the TREE's - a harness
 * can keep every file under its pin and still double by adding files.
 *
 * This is the missing half: a committed budget for the whole harness, plus a
 * per-directory budget for the biggest subsystems. It fails when the total
 * grows, when a subsystem's total grows, or when a NEW file pushes the tree
 * past its ceiling.
 *
 * A budget is only meaningful if it can be RAISED deliberately - so the
 * budget file is committed, and lowering it is as normal as raising it. The
 * direction that matters is that it must not grow silently.
 *
 * Run: `npm run check:size` (also part of `npm run check:all`).
 */

const fs = require("fs");
const path = require("path");

const ROOT = path.resolve(__dirname, "..");
const HARNESS = path.join(ROOT, "python", "harness");
const BUDGET_FILE = path.join(__dirname, "size-budget.json");

function countLines(file) {
  const text = fs.readFileSync(file, "utf8");
  if (text.length === 0) return 0;
  let count = 0;
  let index = 0;
  while (index < text.length) {
    const next = text.indexOf("\n", index);
    if (next === -1) {
      count += 1;
      break;
    }
    count += 1;
    index = next + 1;
  }
  return count;
}

function walk(dir, out) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === "__pycache__" || entry.name.startsWith(".")) continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full, out);
    else if (entry.name.endsWith(".py")) out.push(full);
  }
  return out;
}

function main() {
  if (!fs.existsSync(BUDGET_FILE)) {
    console.error(`Size budget: ${BUDGET_FILE} is missing.`);
    process.exit(1);
  }
  const budget = JSON.parse(fs.readFileSync(BUDGET_FILE, "utf8"));
  const files = walk(HARNESS, []);
  const lines = new Map();
  let total = 0;
  const byDir = new Map();
  for (const file of files) {
    const n = countLines(file);
    const rel = path.relative(ROOT, file).split(path.sep).join("/");
    lines.set(rel, n);
    total += n;
    const dir = path.relative(HARNESS, path.dirname(file)).split(path.sep).join("/") || ".";
    byDir.set(dir, (byDir.get(dir) || 0) + n);
  }

  const problems = [];
  if (total > budget.totalLines) {
    problems.push(
      `the harness is ${total} lines, over the ${budget.totalLines}-line ceiling ` +
        `by ${total - budget.totalLines}. Split something, or raise the budget in ` +
        `scripts/size-budget.json ON PURPOSE.`
    );
  }
  for (const [dir, ceiling] of Object.entries(budget.directories || {})) {
    const actual = byDir.get(dir) || 0;
    if (actual > ceiling) {
      problems.push(
        `python/harness/${dir} is ${actual} lines, over its ${ceiling}-line ceiling by ` +
          `${actual - ceiling}.`
      );
    }
  }

  console.log("Harness size budget");
  console.log(`  ${files.length} modules, ${total} lines (ceiling ${budget.totalLines})`);
  for (const [dir, ceiling] of Object.entries(budget.directories || {})) {
    const actual = byDir.get(dir) || 0;
    console.log(`  ${dir}: ${actual} / ${ceiling}`);
  }
  if (problems.length) {
    for (const problem of problems) console.error(`  [FAIL] ${problem}`);
    console.error(`\nSize budget FAILED: ${problems.length} problem(s).`);
    process.exit(1);
  }
  console.log("  [OK  ] the harness is within its total and per-subsystem budgets.");
  console.log("\nSize budget passed.");
}

main();
