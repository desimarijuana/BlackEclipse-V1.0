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
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.join(__dirname, "..");
const appPrefix = "Black-Eclipse-site/";
// Above this many changed source files the narrowing stops paying for itself —
// treat it as a broad change and run the whole vitest suite.
const BROAD_CHANGE = 40;

const run = (cmd, args) =>
  spawnSync(cmd, args, {
    cwd: root,
    stdio: "inherit",
    shell: process.platform === "win32",
  });

const status = spawnSync("git", ["status", "--porcelain"], { cwd: root, encoding: "utf8" });
if (status.status !== 0) {
  // No git (tarball install) means the changed set is unknowable; be honest and
  // fall back to the full suite rather than silently testing nothing.
  console.log("[fast] not a git work tree - running the full vitest suite instead.");
  process.exit(run("npx", ["vitest", "run"]).status ?? 1);
}

// `git status` is run from the app dir but still prints paths relative to the
// repository root, so strip the app prefix. Paths outside the app are not ours.
const files = status.stdout
  .split("\n")
  .map((line) => line.slice(3).trim())
  .filter(Boolean)
  .map((line) => (line.includes(" -> ") ? line.split(" -> ")[1] : line))
  .map((file) => (file.startsWith(appPrefix) ? file.slice(appPrefix.length) : file))
  .filter((file) => !file.startsWith("Black-Eclipse-site/"));

const under = (prefix, ...exts) =>
  files.filter((file) => file.startsWith(prefix) && exts.some((ext) => file.endsWith(ext)));

const ts = under("src/", ".ts", ".tsx");
const py = under("python/", ".py");
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

// Python modules are not mapped file-to-test here: the suite is small enough
// that a changed harness module is worth the full run, and a partial run would
// create false confidence about the shared runtime.
if (py.length > 0) {
  console.log(`[fast] python suite (${py.length} changed .py file${py.length === 1 ? "" : "s"})`);
  if ((run("node", ["scripts/test-python.js"]).status ?? 1) !== 0) process.exit(1);
}

if (memory.length > 0) {
  console.log("[fast] eval floors (eclipse_memory changed)");
  if ((run("node", ["scripts/test-evals.js"]).status ?? 1) !== 0) process.exit(1);
}

console.log("");
console.log("[fast] fast lane passed. Run `npm run test` before reporting the change complete.");
