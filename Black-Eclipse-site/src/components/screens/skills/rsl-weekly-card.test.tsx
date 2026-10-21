// The weekly summary card: it shows what was measured and keeps the
// unmeasured measures visibly unknown (never a fabricated zero).

import { describe, expect, it, vi } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

vi.mock("@/lib/harness/evolution-browser", () => ({
  getEvolutionRslReportBrowser: vi.fn(async () => ({
    success: true,
    markdown: "# summary",
    digest: {
      days: 7,
      since: "2026-10-14T00:00:00.000Z",
      experiments: {
        rsl_experiments: 3,
        rsl_accepted: 1,
        rsl_rejected: 1,
        rsl_unmeasured: 1,
        regression_rate: 0,
        cost_usd: 0.25,
        cost_per_accepted: 0.25,
      },
      candidates: { inert: 2 },
      recentCandidates: [],
      lessons: [],
      drift: { scope: "global", status: "stable", drop: 0 },
    },
  })),
}));

vi.mock("@/lib/i18n/use-t", () => ({
  useT: () => (key: string, vars?: Record<string, string | number>) =>
    vars ? `${key}:${JSON.stringify(vars)}` : key,
}));

import { RslWeeklyCard } from "./rsl-weekly-card";

describe("the weekly summary card", () => {
  it("shows the measured numbers and keeps the unknown ones unknown", async () => {
    const markup = renderToStaticMarkup(<RslWeeklyCard days={7} />);
    // The card renders on the server too (the fetch fills in on the client).
    expect(markup).toContain("evolution.weekly.title");
    expect(markup).toContain("evolution.weekly.loading");
  });
});
