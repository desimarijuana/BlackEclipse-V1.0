// Capability-matrix contradiction gate (D7).
//
// Every row whose declared level disagrees with the observed run-ledger health
// MUST carry an explicit mismatch block naming both values and the owning config
// key. A mismatch is allowed only when the allowlist has a dated, justified
// exception for `<market>|<axis>`.
//
// Run: npx tsx scripts/capability-matrix-check.ts
//      npx tsx scripts/capability-matrix-check.ts --inject=UK|quote
import fs from "node:fs";
import path from "node:path";
import { buildCapabilityMatrix } from "../src/lib/harness/capability";
import type { ObservedHealth } from "../src/lib/harness/capability";

const AXES = ["quote", "history", "fundamentals", "filings", "web"] as const;
interface AllowlistEntry {
  key: string;
  reason: string;
  expires: string;
}
interface Allowlist {
  exceptions?: AllowlistEntry[];
}

const allowlistPath = path.join(
  process.cwd(),
  "src",
  "lib",
  "harness",
  "capability-mismatch-allowlist.json",
);
let allowlist: Allowlist = { exceptions: [] };
try {
  allowlist = JSON.parse(fs.readFileSync(allowlistPath, "utf8")) as Allowlist;
} catch {
  // A missing allowlist means NO exceptions, never a pass-all.
  allowlist = { exceptions: [] };
}
const allowed = new Map((allowlist.exceptions ?? []).map((e) => [e.key, e]));

// Optional deliberate contradiction, used by the gate's own regression test.
const injectArg = process.argv.find((a) => a.startsWith("--inject="));
const observedByCapability: Record<string, ObservedHealth> = {};
if (injectArg) {
  const key = injectArg.slice("--inject=".length).replace(":", "|");
  observedByCapability[key] = "working";
}

const matrix = buildCapabilityMatrix({ observedByCapability });
const failures: string[] = [];

for (const m of matrix) {
  for (const axisName of AXES) {
    const axis = m[axisName];
    const implemented = axis.level === "configured" || axis.level === "unconfigured";
    const contradiction =
      (!implemented && axis.observed !== "unknown") ||
      (implemented && (axis.observed === "failing" || axis.observed === "degraded"));
    if (!contradiction) continue;
    if (!axis.mismatch) {
      failures.push(
        `${m.market}.${axisName}: declared ${axis.level} vs observed ${axis.observed} ` +
          "without a mismatch block",
      );
      continue;
    }
    const key = `${m.market}|${axisName}`;
    const exception = allowed.get(key);
    if (!exception) {
      failures.push(
        `${key}: unexplained mismatch (declared ${axis.mismatch.declared}, ` +
          `observed ${axis.mismatch.observed}, config ${axis.mismatch.configKey})`,
      );
    } else if (!exception.reason || !exception.expires) {
      failures.push(`${key}: allowlist exception must carry a reason and an expiry date`);
    }
  }
}

if (failures.length) {
  console.error("[capability-matrix-check] FAIL");
  for (const f of failures) console.error("  -", f);
  process.exit(1);
}
console.log(
  `[capability-matrix-check] PASS (${matrix.length} markets; every contradiction is explained)`,
);
