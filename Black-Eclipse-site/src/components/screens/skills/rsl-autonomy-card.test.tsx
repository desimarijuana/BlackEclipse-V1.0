// The autonomy card only enables an apply when the level, kill switch and daily
// budget allow it; the runtime still re-checks evidence and a refusal is shown.

import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type {
  EvolutionAutonomyStatus,
  EvolutionHarnessState,
} from "@/lib/harness/evolution-client";

vi.mock("@/lib/i18n/use-t", () => ({
  useT: () => (key: string, vars?: Record<string, string | number>) =>
    vars ? `${key}:${JSON.stringify(vars)}` : key,
}));

import { RslAutonomyCardView } from "./rsl-autonomy-card";

const STATUS: EvolutionAutonomyStatus = {
  success: true,
  level: "supervised",
  autoEligible: true,
  riskCeiling: "low",
  autoMinLift: 0.02,
  autoMaxPerDay: 1,
  activationsToday: 0,
  killSwitch: { paused: false, at: null, reason: "" },
};

const CANDIDATE: EvolutionHarnessState = {
  id: "state_1",
  parentStateId: null,
  scope: "global",
  snapshotDigest: "digest",
  candidateId: "evo_1",
  acceptedRunId: "run_1",
  utility: 0.9,
  metrics: {},
  status: "candidate",
  createdAt: "2026-10-23T00:00:00.000Z",
  promotedAt: null,
};

function render(overrides: Partial<Parameters<typeof RslAutonomyCardView>[0]> = {}) {
  return renderToStaticMarkup(
    <RslAutonomyCardView
      status={STATUS}
      candidates={[CANDIDATE]}
      error={null}
      busy={false}
      applyingId={null}
      refusedStateIds={[]}
      lastResult={null}
      onRefresh={() => {}}
      onToggleKill={() => {}}
      onApply={() => {}}
      {...overrides}
    />,
  );
}

function applyButton(markup: string): string {
  const match = markup.match(/<button[^>]*>evolution\.autonomy\.apply<\/button>/);
  return match?.[0] ?? "";
}

describe("the autonomy card", () => {
  it("enables apply only while level, kill switch and budget allow", () => {
    const enabled = render();
    expect(enabled).toContain(
      'evolution.autonomy.level:{&quot;level&quot;:&quot;supervised&quot;}',
    );
    expect(enabled).toContain('evolution.autonomy.budget:{&quot;used&quot;:0,&quot;max&quot;:1}');
    expect(applyButton(enabled)).not.toContain('disabled=""');
  });

  it("disables apply when the kill switch is paused", () => {
    const markup = render({
      status: { ...STATUS, killSwitch: { paused: true, at: "now", reason: "stop" } },
    });
    expect(markup).toContain("evolution.autonomy.paused");
    expect(applyButton(markup)).toContain('disabled=""');
  });

  it("disables apply when the daily budget is exhausted or autonomy is off", () => {
    const spent = render({
      status: { ...STATUS, activationsToday: 1, autoMaxPerDay: 1 },
    });
    expect(spent).toContain("evolution.autonomy.notEligible");
    expect(applyButton(spent)).toContain('disabled=""');

    const off = render({
      status: { ...STATUS, level: "off", autoEligible: false },
    });
    expect(applyButton(off)).toContain('disabled=""');
  });

  it("shows the server's refusal reasons instead of hiding them", () => {
    const markup = render({
      refusedStateIds: ["state_1"],
      lastResult: {
        success: true,
        applied: false,
        reason: "policy_refused",
        stateId: "state_1",
        decision: {
          allowed: false,
          level: "supervised",
          riskClass: "L1",
          reasons: ["no_paired_evidence", "lift_below_floor"],
          requiresOperator: true,
          autoMinLift: 0.02,
          autoMaxPerDay: 1,
          activationsToday: 0,
        },
      },
    });
    expect(markup).toContain(
      'evolution.autonomy.refused:{&quot;reasons&quot;:&quot;no_paired_evidence, lift_below_floor&quot;}',
    );
    expect(applyButton(markup)).toContain('disabled=""');
  });
});
