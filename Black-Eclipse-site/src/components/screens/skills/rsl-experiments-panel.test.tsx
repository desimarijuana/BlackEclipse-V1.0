// RSL experiment panel contract: the benchmark badge is honest, and "Prepare
// landing" is offered only for a tests-passed code experiment.

import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import type { TranslateFn } from "@/lib/i18n/translate";
import type { EvolutionExperiment } from "@/lib/harness/evolution-client";
import { ExperimentList } from "./rsl-experiments-panel";
import { RslControlPanel } from "./rsl-control-panel";
import { RslOperatorPanel } from "./rsl-operator-panel";

const t = ((key: string, vars?: Record<string, string | number>) => {
  const labels: Record<string, string> = {
    "evolution.experiment.empty": "No experiments yet.",
    "evolution.experiment.benchmark.measured": "Measured benchmark",
    "evolution.experiment.benchmark.unmeasured": "Tests only — benchmark not measured",
    "evolution.experiment.testsPassed": "Owning tests passed",
    "evolution.experiment.testsFailed": "Owning tests failed",
    "evolution.experiment.measuredTrials": `${vars?.count ?? 0} measured trial(s)`,
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

  it("renders the conductor status, tick and proposal controls", () => {
    const html = renderToStaticMarkup(<RslControlPanel />);
    expect(html).toContain("RSL conductor");
    expect(html).toContain("Run tick now");
    expect(html).toContain("Stage a code proposal");
    expect(html).toContain("Loading conductor status...");
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
