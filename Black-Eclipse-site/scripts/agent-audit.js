// The independent audit corpus: the regression cases that came out of the
// pre-launch review. The manifest is versioned; adding a check means adding a
// pytest module and a manifest entry. This is a release-blocking gate.
const { spawnSync } = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");

const manifestPath = path.join(
  __dirname,
  "..",
  "python",
  "harness",
  "evaluation",
  "corpus",
  "agent_audit_v1.json",
);
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
const files = manifest.checks.map((check) => check.test);
if (!files.length) {
  console.error("[agent-audit] the corpus manifest has no checks");
  process.exit(1);
}
console.log(
  `[agent-audit] ${manifest.id} v${manifest.version}: ${files.length} checks`,
);

const runner = path.join(__dirname, "test-python.js");
const result = spawnSync(process.execPath, [runner, ...files], {
  stdio: "inherit",
  env: process.env,
});
if (result.error) {
  console.error("[agent-audit] could not run the corpus:", result.error.message);
  process.exit(1);
}
process.exit(result.status ?? 1);
