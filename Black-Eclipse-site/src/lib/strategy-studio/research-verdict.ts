// ── Research verdict ────────────────────────────────────────────────────────
// Turns the three robustness runs into a short, honest verdict page. Every
// threshold used here is printed in the check's own label, so nothing is hidden
// behind an unexplained "pass". Missing measurements are "unknown", never a pass.

import type { ResearchResult } from "@/lib/backtest/backtest-client";

export type CheckState = "pass" | "fail" | "unknown";

export interface ResearchCheck {
  id: string;
  label: string;
  /** `check` contributes to the verdict; `info` is reported, never scored. */
  kind: "check" | "info";
  state: CheckState;
  detail: string;
}

export interface ResearchSummary {
  checks: ResearchCheck[];
  overall: "robust" | "fragile" | "inconclusive";
  notes: string[];
}

export type SuiteResults = Partial<
  Record<"walkForward" | "monteCarlo" | "robustness", ResearchResult>
>;

function num(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

export function summarizeResearch(results: SuiteResults): ResearchSummary {
  const checks: ResearchCheck[] = [];
  const notes: string[] = [];

  const wf = results.walkForward;
  if (wf) {
    const oos = num(wf.outOfSampleAggregate?.sharpe);
    const ins = num(wf.inSampleAggregate?.sharpe);
    checks.push({
      id: "oos-sharpe",
      label: "Out-of-sample Sharpe is positive",
      kind: "check",
      state: oos == null ? "unknown" : oos > 0 ? "pass" : "fail",
      detail:
        oos == null
          ? "the walk-forward result did not report an out-of-sample Sharpe"
          : `OOS Sharpe ${oos.toFixed(2)}`,
    });
    checks.push({
      id: "oos-retention",
      label: "OOS keeps at least half the in-sample Sharpe",
      kind: "check",
      state: oos == null || ins == null ? "unknown" : oos >= ins * 0.5 ? "pass" : "fail",
      detail:
        oos == null || ins == null
          ? "both in-sample and out-of-sample Sharpe are needed"
          : `IS ${ins.toFixed(2)} → OOS ${oos.toFixed(2)}`,
    });
    if (num(wf.outOfSampleAggregate?.trade_count) === 0) {
      notes.push("The walk-forward produced no out-of-sample trades; treat the verdict as untested.");
    }
  } else {
    notes.push("Walk-forward has not been run.");
  }

  const mc = results.monteCarlo;
  if (mc) {
    const ruin = num(mc.probabilityOfRuin);
    checks.push({
      id: "ruin",
      label: "Simulated probability of ruin is below 5%",
      kind: "check",
      state: ruin == null ? "unknown" : ruin < 5 ? "pass" : "fail",
      detail: ruin == null ? "the Monte-Carlo result did not report a ruin probability" : `P(ruin) ${ruin.toFixed(1)}%`,
    });
    checks.push({
      id: "worst-drawdown",
      label: "Worst simulated drawdown",
      kind: "info",
      state: "unknown",
      detail:
        num(mc.worstDrawdown) == null
          ? "not reported"
          : `${num(mc.worstDrawdown)!.toFixed(2)}%`,
    });
    checks.push({
      id: "probability-of-loss",
      label: "Probability of a losing run",
      kind: "info",
      state: "unknown",
      detail: num(mc.probabilityOfLoss) == null ? "not reported" : `${num(mc.probabilityOfLoss)!.toFixed(1)}%`,
    });
  } else {
    notes.push("Monte-Carlo has not been run.");
  }

  const rb = results.robustness;
  if (rb) {
    checks.push({
      id: "robustness-verdict",
      label: "Robustness verdict is robust",
      kind: "check",
      state: rb.verdict === "robust" ? "pass" : rb.verdict === "fragile" ? "fail" : "unknown",
      detail: rb.verdict ? `engine verdict: ${rb.verdict}` : "the engine did not return a verdict",
    });
    for (const conclusion of rb.conclusions ?? []) notes.push(conclusion);
  } else {
    notes.push("Robustness has not been run.");
  }

  const scored = checks.filter((check) => check.kind === "check");
  const failed = scored.some((check) => check.state === "fail");
  // A verdict of "robust" requires the whole suite AND every scored check to
  // pass. A partial run is inconclusive, never a pass by omission.
  const complete = Boolean(results.walkForward && results.monteCarlo && results.robustness);
  const allScoredPassed = scored.length > 0 && scored.every((check) => check.state === "pass");
  const overall: ResearchSummary["overall"] = failed
    ? "fragile"
    : complete && allScoredPassed
      ? "robust"
      : "inconclusive";

  return { checks, overall, notes };
}
