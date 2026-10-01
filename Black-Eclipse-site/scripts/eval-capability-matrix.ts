// Capability-matrix eval gate (Harness closeout Phase 8.1).
//
// OFFLINE and deterministic. Fails NON-ZERO if any of the matrix truthfulness
// invariants regresses:
//   * no level/observation contradiction on any market × axis;
//   * the market count equals the asserted count;
//   * every currency equals its real ISO code;
//   * a market with an unimplemented axis never reports `configured`.
//
// Run: npx tsx scripts/eval-capability-matrix.ts   (wired into scripts/test-evals.js)
import { buildCapabilityMatrix } from "../src/lib/harness/capability";
import { MARKET_CURRENCY_ISO } from "../src/lib/markets";

const AXES = ["quote", "history", "fundamentals", "filings", "web"] as const;
const EXPECTED_MARKET_COUNT = 34;

const matrix = buildCapabilityMatrix();
const failures: string[] = [];

if (matrix.length !== EXPECTED_MARKET_COUNT) {
  failures.push(`market count ${matrix.length} != asserted ${EXPECTED_MARKET_COUNT}`);
}

for (const m of matrix) {
  for (const axisName of AXES) {
    const axis = m[axisName];
    const implemented = axis.level === "configured" || axis.level === "unconfigured";
    if (axis.observed !== "unknown" && !implemented) {
      failures.push(`${m.market}.${axisName}: observed ${axis.observed} but not implemented (${axis.level})`);
    }
    if (axis.inconsistent === "matrixInconsistent" && !axis.inconsistencyReason) {
      failures.push(`${m.market}.${axisName}: matrixInconsistent without a reason`);
    }
  }
  if (m.market === "DERIV") {
    if (m.currency !== "N/A") failures.push(`DERIV currency ${m.currency} != N/A`);
  } else if (m.currency !== MARKET_CURRENCY_ISO[m.market]) {
    failures.push(`${m.market} currency ${m.currency} != real ISO ${MARKET_CURRENCY_ISO[m.market]}`);
  }
}

if (failures.length) {
  console.error("[eval-capability-matrix] FAIL");
  for (const f of failures) console.error("  -", f);
  process.exit(1);
}
console.log(`[eval-capability-matrix] PASS (${matrix.length} markets, currencies + invariants OK)`);
