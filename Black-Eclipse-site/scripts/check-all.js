// The ONE honest local release gate; it mirrors `.github/workflows/ci.yml` at the
// repository ROOT step-for-step, so a green local run means a green CI run.
//
// Steps, in order:
//   1. prisma generate      (the client the app imports)
//   2. typecheck            (tsc --noEmit)
//   3. lint                 (eslint)
//   4. secret scan          (no credential is tracked or staged)
//   5. security preflight   (deploy checklist; advisory on a loopback bind)
//   6. decision record       (every ADR number names exactly one decision)
//   7. harness size budget   (the committed total + per-subsystem ceilings)
//   8. corpus gate           (the corpus vs the COMMITTED baseline)
//   9. tests                (vitest + python suite)
//  10. eval gates           (retrieval / contradiction / compaction floors)
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
// The committed-secret gate. Cheap, offline, and it fails the release if any
// tracked file is a secret artifact (.env, *.db, a private key) or contains a
// recognisable provider credential. Same check the pre-commit hook runs.
run("secret scan", "node", ["scripts/scan-secrets.js"]);
// The deploy-time security checklist. On a loopback/dev bind every check is
// advisory (WARN, exit 0); an exposed misconfiguration — a public bind or a
// production build without the required secrets — fails the release gate.
run("security preflight", "node", ["scripts/security-preflight.js"]);
// Round 3 / W7 (ADR-H288): the decision record must be unambiguous, and the
// harness must stay inside its committed size budget. Both are cheap, both
// are silent when they pass, and both fail the release gate when they do not.
run("decision record", "node", ["scripts/check-adr-numbers.js"]);
run("harness size budget", "node", ["scripts/size-budget.js"]);
// C7: observability must bite. The deterministic probe runs through the shipped
// telemetry path; the gate fails a release that breaches an SLO budget or a
// committed regression allowance.
run("SLO release gate", "node", ["scripts/slo-gate.js"]);
run("conformance gate", "node", ["scripts/conformance-gate.js"]);
run("tests (vitest + python)", "npm", ["run", "test"]);
run("eval gates", "node", ["scripts/test-evals.js"]);
// 10b. The independent-audit corpus: numeric contracts, provenance, leases,
// effects, budgets and the release gate. Release-blocking, offline.
run("agent audit corpus", "node", ["scripts/agent-audit.js"]);
// The corpus GATE: the same corpus, compared with the COMMITTED baseline. A
// critical regression (task success, safety, hallucination rate, financial
// accuracy, routing) fails the release here.
run("corpus gate (nightly vs committed baseline)", "node", [
  "scripts/rsl-nightly.js",
  "--dataset",
  "all",
  "--baseline-file",
  "python/harness/evaluation/baselines/corpus_v1.json",
]);

console.log("\n[check-all] ALL GATES PASSED");
