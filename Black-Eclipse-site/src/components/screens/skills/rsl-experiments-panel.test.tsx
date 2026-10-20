// RSL experiment panel contract: the benchmark badge is honest, and "Prepare
// landing" is offered only for a tests-passed code experiment.

import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import type { TranslateFn } from "@/lib/i18n/translate";
import type { EvolutionExperiment } from "@/lib/harness/evolution-client";
import { ExperimentList } from "./experiment-list";
import { RslControlPanel } from "./rsl-control-panel";
import { RslOperatorPanel } from "./rsl-operator-panel";
import {
  CandidateEvidencePanel,
  evidenceSectionClass,
} from "./candidate-evidence-panel";
import { driftingScopes } from "./rsl-drift-badge";

const t = ((key: string, vars?: Record<string, string | number>) => {
  const labels: Record<string, string> = {
    "evolution.experiment.empty": "No experiments yet.",
    "evolution.experiment.benchmark.measured": "Measured benchmark",
    "evolution.experiment.benchmark.unmeasured": "Tests only — benchmark not measured",
    "evolution.experiment.testsPassed": "Owning tests passed",
    "evolution.experiment.testsFailed": "Owning tests failed",
    "evolution.experiment.measuredTrials": `${vars?.count ?? 0} measured trial(s)`,
    "evolution.experiment.criticalRegressions": `Critical regressions (${vars?.count ?? 0})`,
    "evolution.experiment.criticalRegression": `${vars?.taskId ?? ""}: ${vars?.before ?? ""} → ${vars?.after ?? ""}`,
    "evolution.experiment.viewEvidence": "View evidence",
    "evolution.experiment.driftCandidate": "Drift candidate",
    "evolution.experiment.prepareLanding": "Prepare landing",
    "evolution.experiment.preparing": "Preparing…",
    "evolution.experiment.prepared": `Prepared ${vars?.runId ?? ""}`,
    "evolution.experiment.promotionHint": `Review ${vars?.count ?? 0} file(s) and approve.`,
    "evolution.lesson.title": "Adopted lessons",
    "evolution.lesson.subtitle": "Verified lessons",
    "evolution.lesson.refresh": "Refresh lessons",
    "evolution.lesson.empty": "No adopted lessons yet.",
    "evolution.lesson.candidate": "Candidate id",
    "evolution.lesson.validationRun": "Validation run id",
    "evolution.lesson.cue": "Cue",
    "evolution.lesson.body": "Lesson",
    "evolution.lesson.evidence": "Evidence JSON",
    "evolution.lesson.scope": "Scope JSON",
    "evolution.lesson.adopt": "Adopt lesson",
    "evolution.lesson.adopting": "Adopting...",
    "evolution.recursive.title": "Recursive experiment",
    "evolution.recursive.subtitle": "Run one bounded set of candidates.",
    "evolution.recursive.candidate": "Parent candidate id",
    "evolution.recursive.seed": "Seed",
    "evolution.recursive.variants": "Typed variants JSON",
    "evolution.recursive.run": "Run recursive experiment",
    "evolution.recursive.running": "Running...",
    "evolution.surface.title": "Surface experiment",
    "evolution.surface.subtitle": "Benchmark a bounded snapshot.",
    "evolution.surface.base": "Base snapshot JSON",
    "evolution.surface.candidate": "Candidate snapshot JSON",
    "evolution.surface.dataset": "Dataset",
    "evolution.surface.split": "Split",
    "evolution.surface.target": "Target dimension",
    "evolution.surface.trials": "Trials",
    "evolution.surface.seed": "Seed",
    "evolution.surface.problem": "Problem statement",
    "evolution.surface.run": "Queue surface experiment",
    "evolution.surface.running": "Queueing...",
    "evolution.rsl.title": "RSL conductor",
    "evolution.rsl.subtitle": "Mode, lifecycle and daily budget.",
    "evolution.rsl.refresh": "Refresh status",
    "evolution.rsl.tick": "Run tick now",
    "evolution.rsl.ticking": "Running...",
    "evolution.rsl.loading": "Loading conductor status...",
    "evolution.propose.title": "Stage a code proposal",
    "evolution.propose.subtitle": "Validate operator-supplied operations.",
    "evolution.propose.candidate": "Candidate id",
    "evolution.propose.target": "Target path",
    "evolution.propose.ops": "Operations JSON",
    "evolution.propose.stage": "Stage proposal",
    "evolution.propose.staging": "Staging...",
  };
  return labels[key] ?? key;
}) as TranslateFn;

function experiment(overrides: Partial<EvolutionExperiment> = {}): EvolutionExperiment {
  return {
    id: "rsl-e1",
    suite: "rsl-code",
    datasetName: "owning-tests",
    datasetVersion: "1",
    status: "completed",
    trialCount: 0,
    agentVersion: "0.1.0",
    gitCommit: "abc",
    model: null,
    provider: null,
    startedAt: "2026-10-18T00:00:00.000Z",
    finishedAt: "2026-10-18T00:00:01.000Z",
    config: {},
    metadata: {
      kind: "rsl", proposalId: "evo_1", benchmark: "UNMEASURED",
      testsPassed: true, decision: "tests_passed",
      targetPath: "python/harness/foo.py",
    },
    ...overrides,
  };
}

describe("ExperimentList", () => {
  it("renders the empty state", () => {
    const html = renderToStaticMarkup(<ExperimentList experiments={[]} t={t} />);
    expect(html).toContain("No experiments yet.");
  });

  it("offers prepare landing only for a tests-passed, unmeasured code experiment", () => {
    const html = renderToStaticMarkup(
      <ExperimentList experiments={[experiment()]} t={t} onPrepare={() => undefined} />,
    );
    expect(html).toContain("Tests only — benchmark not measured");
    expect(html).toContain("Owning tests passed");
    expect(html).toContain("Prepare landing");
    expect(html).toContain("python/harness/foo.py");
  });

  it("offers view evidence for a candidate experiment", () => {
    const html = renderToStaticMarkup(
      <ExperimentList
        experiments={[experiment()]}
        t={t}
        onViewEvidence={() => undefined}
      />,
    );
    expect(html).toContain("View evidence");
  });

  it("never offers landing for a failed experiment", () => {
    const failed = experiment({
      metadata: {
        kind: "rsl", proposalId: "evo_2", benchmark: "UNMEASURED",
        testsPassed: false, decision: "tests_failed",
      },
    });
    const html = renderToStaticMarkup(
      <ExperimentList experiments={[failed]} t={t} onPrepare={() => undefined} />,
    );
    expect(html).toContain("Owning tests failed");
    expect(html).not.toContain("Prepare landing");
  });

  it("shows a measured benchmark without a landing action", () => {
    const measured = experiment({
      suite: "improvement",
      metadata: {
        kind: "rsl", proposalId: "evo_3", benchmark: "MEASURED",
        measuredTrials: 3, decision: "benchmark",
      },
    });
    const html = renderToStaticMarkup(
      <ExperimentList experiments={[measured]} t={t} onPrepare={() => undefined} />,
    );
    expect(html).toContain("Measured benchmark");
    expect(html).toContain("3 measured trial(s)");
    expect(html).not.toContain("Prepare landing");
  });

  it("shows a code benchmark's critical task regression", () => {
    const measured = experiment({
      suite: "rsl-code-benchmark",
      metadata: {
        kind: "rsl", proposalId: "evo_critical", benchmark: "MEASURED",
        measuredTrials: 2, decision: "benchmark_rejected",
        decisionRecord: {
          accepted: false,
          criticalDeltas: [{
            taskId: "safety.forbidden_tool.001", before: 1.0, after: 0.0,
          }],
        },
      },
    });
    const html = renderToStaticMarkup(
      <ExperimentList experiments={[measured]} t={t} onPrepare={() => undefined} />,
    );
    expect(html).toContain("Critical regressions (1)");
    expect(html).toContain("safety.forbidden_tool.001: 1.000 → 0.000");
  });

  it("shows the target dimension for a measured surface experiment", () => {
    const surface = experiment({
      suite: "improvement",
      metadata: {
        kind: "rsl", proposalId: "evo_surface", benchmark: "MEASURED",
        measuredTrials: 1, decision: "benchmark_rejected",
        targetDimension: "safety_score", surface: true,
      },
    });
    const html = renderToStaticMarkup(
      <ExperimentList experiments={[surface]} t={t} onPrepare={() => undefined} />,
    );
    expect(html).toContain("safety_score");
    expect(html).toContain("Measured benchmark");
    expect(html).not.toContain("Prepare landing");
  });

  it("badges a drift candidate's experiment", () => {
    const drift = experiment({
      metadata: {
        kind: "rsl", proposalId: "evo_drift", benchmark: "UNMEASURED",
        decision: "tests_passed", subjectType: "drift",
      },
    });
    const html = renderToStaticMarkup(
      <ExperimentList experiments={[drift]} t={t} onPrepare={() => undefined} />,
    );
    expect(html).toContain("Drift candidate");
  });

  it("renders the conductor status, tick and proposal controls", () => {
    const html = renderToStaticMarkup(<RslControlPanel />);
    expect(html).toContain("RSL conductor");
    expect(html).toContain("Run tick now");
    expect(html).toContain("Stage a code proposal");
    expect(html).toContain("Loading conductor status...");
  });

  it("renders the candidate evidence lookup", () => {
    const html = renderToStaticMarkup(<CandidateEvidencePanel />);
    expect(html).toContain("Candidate evidence");
    expect(html).toContain("View evidence");
    expect(html).toContain("Refresh evidence");
    expect(html).toContain("Clear");
  });

  it("selects only drifting scopes for the journey badge", () => {
    const signal = (scope: string, status: string) => ({
      scope,
      signal: {
        status, scope, window: 30, baselineWindow: 100,
        current: { n: 30, successes: 10, rate: 0.3, ciLow: 0, ciHigh: 1 },
        baseline: { n: 100, successes: 90, rate: 0.9, ciLow: 0, ciHigh: 1 },
        drop: status === "drift" ? 0.6 : null, threshold: 0.1, reasons: [],
      },
    });
    expect(driftingScopes({
      availableScopes: ["global", "code-agent", "eclipse-agent"],
      signals: [signal("global", "stable"), signal("code-agent", "drift")],
    })).toEqual(["code-agent"]);
    expect(driftingScopes(null)).toEqual([]);
  });

  it("highlights the evidence section after a drift jump", () => {
    expect(evidenceSectionClass(false)).not.toContain("ring-2");
    expect(evidenceSectionClass(true)).toContain("ring-2");
    expect(evidenceSectionClass(true)).toContain("ring-sky-400/40");
  });

  it("renders the lesson adoption and recursive operator surfaces", () => {
    const html = renderToStaticMarkup(<RslOperatorPanel />);
    expect(html).toContain("Adopted lessons");
    expect(html).toContain("Recursive experiment");
    expect(html).toContain("Surface experiment");
    expect(html).toContain("Adopt lesson");
    expect(html).toContain("Queue surface experiment");
  });
});
