import { describe, expect, it } from "vitest";
import { DEFAULT_CHART_PALETTE, normalizeChartPalette } from "./chart-palette";

describe("normalizeChartPalette", () => {
  it.each([null, undefined, true, 42, "#abc", [], {}])("defaults malformed input %j", (raw) => {
    expect(normalizeChartPalette(raw)).toEqual(DEFAULT_CHART_PALETTE);
  });

  it("expands shorthand and canonicalizes hex without mutating input", () => {
    const raw = { candles: { up: " #AbC " }, lines: { primary: "#123456", series: ["#FFF", "#ABCDEF"] }, heatmap: { mid: "#000" } };
    const palette = normalizeChartPalette(raw);
    expect(palette).toEqual({
      candles: { ...DEFAULT_CHART_PALETTE.candles, up: "#aabbcc" },
      lines: { primary: "#123456", series: ["#ffffff", "#abcdef", ...DEFAULT_CHART_PALETTE.lines.series.slice(2)] },
      heatmap: { ...DEFAULT_CHART_PALETTE.heatmap, mid: "#000000" },
    });
    expect(raw.candles.up).toBe(" #AbC ");
    expect(raw.lines.series).toEqual(["#FFF", "#ABCDEF"]);
  });

  it("rejects CSS, alpha hex, missing hashes and malformed channels independently", () => {
    const palette = normalizeChartPalette({
      candles: { up: "red", down: "#abcd", neutral: "ff0000" },
      lines: { primary: {}, series: ["url(x)", "#aabbccdd", "#00gg00", null, 12, "#123", "#fff"] },
      heatmap: { up: [], mid: "#aabbccdd", down: "#123" },
    });
    expect(palette).toEqual({
      ...DEFAULT_CHART_PALETTE,
      lines: { ...DEFAULT_CHART_PALETTE.lines, series: [...DEFAULT_CHART_PALETTE.lines.series.slice(0, 5), "#112233"] },
      heatmap: { ...DEFAULT_CHART_PALETTE.heatmap, down: "#112233" },
    });
  });

  it("fills sparse arrays and always produces six independent series slots", () => {
    const series = new Array(3);
    series[2] = "#abc";
    const palette = normalizeChartPalette({ lines: { series } });
    expect(palette.lines.series).toHaveLength(6);
    expect(palette.lines.series[0]).toBe(DEFAULT_CHART_PALETTE.lines.series[0]);
    expect(palette.lines.series[2]).toBe("#aabbcc");
    palette.lines.series[0] = "#000000";
    expect(normalizeChartPalette(null)).toEqual(DEFAULT_CHART_PALETTE);
    expect(normalizeChartPalette({ lines: { series: {} } })).toEqual(DEFAULT_CHART_PALETTE);
  });
});
