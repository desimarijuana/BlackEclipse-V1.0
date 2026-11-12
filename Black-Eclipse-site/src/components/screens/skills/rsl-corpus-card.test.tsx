// The corpus card shows the committed totals, the real oracle/exemption split
// and the manifest verdict. Rotation is a preview; there is no apply control.

import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import type {
  EvolutionCorpusStatus,
  EvolutionRotationPreview,
} from "@/lib/harness/clients/evolution-client";

vi.mock("@/lib/i18n/use-t", () => ({
  useT: () => (key: string, vars?: Record<string, string | number>) =>
    vars ? `${key}:${JSON.stringify(vars)}` : key,
}));

import { RslCorpusCardView } from "./rsl-corpus-card";

const STATUS: EvolutionCorpusStatus = {
  success: true,
  manifest: {
    manifestVersion: "1.0.0",
    recordedAt: "2026-10-23T00:00:00.000Z",
    taskCount: 338,
    datasetCount: 14,
    bySplit: { validation: 244, optimization: 88, held_out: 6 },
    oracleCount: 263,
    oracleExemptCount: 75,
    oracleCoverage: 0.778107,
    canaryCount: 0,
    liveOnly: 10,
    datasets: [],
  },
  verification: { ok: true, checked: 14, mismatches: [] },
  audit: { ok: true, counts: { tasks: 338 }, errorCount: 0 },
};

const PREVIEW: EvolutionRotationPreview = {
  success: true,
  quarter: "2026Q4",
  applied: false,
  plan: {
    ok: true,
    quarter: "2026Q4",
    seed: "2026Q4:rotation",
    count: 1,
    returned: 0,
    moves: [{
      datasetFile: "finance_v3.json",
      taskId: "finance.v3.opt.cagr.001",
      version: 2,
      from: "optimization",
      to: "held_out",
    }],
  },
};

function render(overrides: Partial<Parameters<typeof RslCorpusCardView>[0]> = {}) {
  return renderToStaticMarkup(
    <RslCorpusCardView
      status={STATUS}
      error={null}
      quarter="2026Q4"
      count={4}
      preview={null}
      previewing={false}
      previewError={null}
      onRefresh={() => {}}
      onQuarterChange={() => {}}
      onCountChange={() => {}}
      onPreview={() => {}}
      {...overrides}
    />,
  );
}

describe("the corpus card", () => {
  it("renders the frozen counts, oracle coverage and exemptions", () => {
    const markup = render();
    expect(markup).toContain('evolution.corpus.tasks:{&quot;count&quot;:338,&quot;datasets&quot;:14}');
    expect(markup).toContain('&quot;split&quot;:&quot;validation&quot;,&quot;count&quot;:244');
    expect(markup).toContain('&quot;split&quot;:&quot;optimization&quot;,&quot;count&quot;:88');
    expect(markup).toContain('&quot;split&quot;:&quot;held_out&quot;,&quot;count&quot;:6');
    expect(markup).toContain('&quot;covered&quot;:263');
    expect(markup).toContain('evolution.corpus.exempt:{&quot;count&quot;:75}');
    expect(markup).toContain("evolution.corpus.verified");
    expect(markup).toContain("evolution.corpus.auditOk");
  });

  it("says mismatch and audit gaps when verification fails", () => {
    const markup = render({
      status: {
        ...STATUS,
        verification: { ok: false, checked: 14, mismatches: [{ dataset: "x" }] },
        audit: { ok: false, counts: {}, errorCount: 3 },
      },
    });
    expect(markup).toContain('evolution.corpus.unverified:{&quot;count&quot;:1}');
    expect(markup).toContain('evolution.corpus.auditFail:{&quot;count&quot;:3}');
  });

  it("shows a rotation preview without any apply control", () => {
    const markup = render({ preview: PREVIEW });
    expect(markup).toContain('evolution.corpus.plan:{&quot;count&quot;:1,&quot;returned&quot;:0}');
    expect(markup).toContain("finance.v3.opt.cagr.001");
    expect(markup).toContain("evolution.corpus.previewOnly");
  });
});
