// The ONE honest release gate (replaces the unreachable CI workflow).
//
// WHY: the repo's workflows lived at `Black-Eclipse-site/.github/workflows/`,
// but GitHub Actions reads only `/.github/workflows` at the repository root, so
// they never ran. Rather than keep two half-gates, this runs exactly what CI was
// meant to run, locally and verifiably, and exits non-zero on the first failure.
//
// Steps, in order:
//   1. prisma generate      (the client the app imports)
//   2. typecheck            (tsc --noEmit)
//   3. lint                 (eslint)
//   4. security preflight   (deploy checklist; advisory on a loopback bind)
//   5. decision record       (every ADR number names exactly one decision)
//   6. harness size budget   (the committed total + per-subsystem ceilings)
//   7. tests                (vitest + python suite)
//   8. eval gates           (retrieval / contradiction / compaction floors)
//
// Usage: node scripts/check-all.js   (or `npm run check:all`)
const { spawnSync } = require("child_process");
const path = require("path");

const root = path.join(__dirname, "..");

function run(label, command, args) {
  console.log(`\n[check-all] ${label}: ${command} ${args.join(" ")}`);
  const result = spawnSync(command, args, { stdio: "inherit", cwd: root, shell: process.platform === "win32" });
  if ((result.status ?? 1) !== 0) {
    console.error(`[check-all] FAILED at: ${label}`);
    process.exit(result.status ?? 1);
  }
}

const npx = process.platform === "win32" ? "npx.cmd" : "npx";

run("prisma generate", npx, ["prisma", "generate"]);
run("typecheck", npx, ["tsc", "--noEmit"]);
run("lint", npx, ["eslint", "."]);
// The deploy-time security checklist. On a loopback/dev bind every check is
// advisory (WARN, exit 0); an exposed misconfiguration — a public bind or a
// production build without the required secrets — fails the release gate.
run("security preflight", "node", ["scripts/security-preflight.js"]);
// Round 3 / W7 (ADR-H288): the decision record must be unambiguous, and the
// harness must stay inside its committed size budget. Both are cheap, both
// are silent when they pass, and both fail the release gate when they do not.
run("decision record", "node", ["scripts/check-adr-numbers.js"]);
run("harness size budget", "node", ["scripts/size-budget.js"]);
run("tests (vitest + python)", "npm", ["run", "test"]);
run("eval gates", "node", ["scripts/test-evals.js"]);

console.log("\n[check-all] ALL GATES PASSED");
