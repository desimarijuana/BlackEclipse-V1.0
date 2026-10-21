import { describe, it, expect, vi, beforeEach } from "vitest";

// The chart engine's browser client.
//
// The contract it keeps: a chart is DATA going in, a COMPUTED figure coming
// out, and a failure is an error the UI can show — never a silent empty
// chart.

import { renderChart } from "@/lib/harness/charts";

const okFigure = {
  kind: "line",
  label: "computed",
  isEvidence: false,
  artifact: "chart-line-abc.png",
  sha256: "abc",
  bytes: 1234,
  width: 960,
  height: 440,
  theme: "eclipse-dark",
  title: "Equity curve",
  series: [{ name: "NAV", points: 2 }],
  summary: "line chart of NAV",
};

beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => ({
      ok: true,
      status: 200,
      json: async () => ({
        status: "OK",
        figure: okFigure,
        artifact: { id: "art_1", name: "chart-line-abc.png", bytes: 1234, sha256: "abc" },
      }),
    })),
  );
});

describe("renderChart", () => {
  it("posts the spec and returns the computed figure", async () => {
    const rendered = await renderChart({
      kind: "line",
      categories: ["Jan", "Feb"],
      series: [{ name: "NAV", data: [100, 104] }],
    });
    expect(rendered.figure.label).toBe("computed");
    expect(rendered.figure.isEvidence).toBe(false);
    expect(rendered.artifact.id).toBe("art_1");
  });

  it("raises the runtime's refusal message", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({
        ok: false,
        status: 400,
        json: async () => ({
          detail: { code: "CHART_SPEC_INVALID", message: "a pie chart needs one label per value" },
        }),
      })),
    );
    await expect(renderChart({ kind: "pie", labels: ["a"], values: [1, 2] })).rejects.toThrow(
      /one label per value/,
    );
  });

  it("fails loudly when the engine returns no figure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => ({ ok: true, status: 200, json: async () => ({ status: "OK" }) })),
    );
    await expect(renderChart({ kind: "line" })).rejects.toThrow(/no figure/i);
  });
});
