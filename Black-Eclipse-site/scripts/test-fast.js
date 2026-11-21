// Fast feedback lane: typecheck, then only the tests reachable from the files
// you actually edited in your working tree.
//
// WHY this exists: `npm run test` is 554 vitest files + the Python harness suite
// + the eval floors. Measured on a dev machine, vitest alone is ~160s and the
// breakdown is import 1325s (summed across workers) vs tests 67s — i.e. the cost
// is re-importing the agent tool registry for tests your change cannot affect.
// While iterating, only the affected tests are informative.
//
// This is NOT a replacement for the gate. `npm run test` + `npx tsc --noEmit`
// are still required before a change is reported complete (AGENTS.md); this
// just shortens the loop in between. It prints that reminder when it passes.
//
// Usage: npm run test:fast
const path = require("path");
const fs = require("fs");
const { spawnSync } = require("child_process");
const { changedFiles, under } = require("./lib/changed-files");

const root = path.join(__dirname, "..");
// Above this many changed source files the narrowing stops paying for itself —
// treat it as a broad change and run the whole vitest suite.
const BROAD_CHANGE = 40;

const run = (cmd, args) =>
  spawnSync(cmd, args, {
    cwd: root,
    stdio: "inherit",
    shell: process.platform === "win32",
  });

const changed = changedFiles();
if (!changed.ok) {
  // No git (tarball install) means the changed set is unknowable; be honest and
  // fall back to the full suite rather than silently testing nothing.
  console.log("[fast] not a git work tree - running the full vitest suite instead.");
  process.exit(run("npx", ["vitest", "run"]).status ?? 1);
}

const ts = under(changed.files, "src/", ".ts", ".tsx");
const py = under(changed.files, "python/", ".py");
const memory = py.filter((file) => file.startsWith("python/harness/eclipse_memory/"));

// Typecheck first: 16s on this machine, and it catches the class of break the
// tests miss (a changed type rippling into a file no test imports).
console.log("[fast] tsc --noEmit");
if ((run("npx", ["tsc", "--noEmit"]).status ?? 1) !== 0) {
  process.exit(1);
}

if (ts.length === 0) {
  console.log("[fast] no src changes - skipping vitest.");
} else if (ts.length > BROAD_CHANGE) {
  console.log(`[fast] ${ts.length} src files changed (broad) - running the full vitest suite.`);
  if ((run("npx", ["vitest", "run"]).status ?? 1) !== 0) process.exit(1);
} else {
  console.log(`[fast] vitest related (${ts.length} changed src file${ts.length === 1 ? "" : "s"})`);
  if ((run("npx", ["vitest", "related", ...ts, "--run", "--passWithNoTests"]).status ?? 1) !== 0) {
    process.exit(1);
  }
}

// Python modules are not mapped by "which test imports me" (that would cost a
// collection pass); they are mapped by name, which is how this suite is laid
// out: `harness/market/yahoo.py` is covered by `test_yahoo*.py`. Running the
// WHOLE Python suite from one changed module was measured at 26 minutes - far
// past what a fast lane is for. If nothing matches, say so instead of pretending
// the module is covered; `npm run verify` runs the domain in full.
if (py.length > 0) {
  const testsDir = path.join(root, "python", "tests");
  const testFiles = fs
    .readdirSync(testsDir, { recursive: true })
    .map((entry) => String(entry))
    .filter((entry) => /(^|[\\/])test_.*\.py$/.test(entry));

  const related = new Set();
  for (const file of py) {
    const stem = path.basename(file, ".py");
    if (stem === "__init__") continue;
    for (const test of testFiles) {
      if (path.basename(test).includes(stem)) related.add(path.join("python/tests", path.basename(test)));
    }
  }

  if (related.size === 0) {
    console.log(`[fast] ${py.length} python file(s) changed, no test named after them - run \`npm run verify\`.`);
  } else {
    console.log(`[fast] python tests matched by name (${related.size})`);
    if ((run("node", ["scripts/test-python.js", ...related]).status ?? 1) !== 0) process.exit(1);
  }
}

if (memory.length > 0) {
  console.log("[fast] eval floors (eclipse_memory changed)");
  if ((run("node", ["scripts/test-evals.js"]).status ?? 1) !== 0) process.exit(1);
}

console.log("");
console.log("[fast] fast lane passed. Run `npm run test` before reporting the change complete.");
