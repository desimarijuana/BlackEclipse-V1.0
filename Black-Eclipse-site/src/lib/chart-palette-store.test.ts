import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DEFAULT_CHART_PALETTE } from "./chart-palette";

const key = "be_chart_palette_v2";
const values = new Map<string, string>();
let storageListener: (event: Partial<StorageEvent>) => void;
const storage = {
  getItem: vi.fn((name: string) => values.get(name) ?? null),
  setItem: vi.fn((name: string, value: string) => { values.set(name, value); }),
};

beforeEach(() => {
  vi.resetModules();
  vi.clearAllMocks();
  values.clear();
  vi.stubGlobal("window", {
    localStorage: storage,
    addEventListener: vi.fn((type: string, listener: typeof storageListener) => {
      if (type === "storage") storageListener = listener;
    }),
  });
});

afterEach(() => vi.unstubAllGlobals());

describe("chart palette storage lifecycle", () => {
  it("keeps imports SSR-safe and hydrates imperative consumers once before Settings opens", async () => {
    values.set(key, JSON.stringify({ lines: { primary: "#abc" } }));
    const { getChartPalette, useChartPaletteStore } = await import("./chart-palette-store");
    expect(storage.getItem).not.toHaveBeenCalled();
    expect(useChartPaletteStore.getInitialState().palette).toEqual(DEFAULT_CHART_PALETTE);
    expect(getChartPalette().lines.primary).toBe("#aabbcc");
    getChartPalette();
    useChartPaletteStore.getState().hydrate();
    expect(storage.getItem).toHaveBeenCalledTimes(1);
    expect(window.addEventListener).toHaveBeenCalledTimes(1);
    expect(storage.setItem).not.toHaveBeenCalled();
  });

  it("notifies on hydration and edits, and unsubscribes", async () => {
    values.set(key, JSON.stringify({ candles: { up: "#abc" } }));
    const { subscribeChartPalette, useChartPaletteStore } = await import("./chart-palette-store");
    const listener = vi.fn();
    const unsubscribe = subscribeChartPalette(listener);
    expect(listener).toHaveBeenCalledTimes(1);
    useChartPaletteStore.getState().setSection("candles", { down: "#def" });
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
    useChartPaletteStore.getState().reset();
    expect(listener).toHaveBeenCalledTimes(2);
  });

  it("hydrates before partial edits, validates setters, persists and resets only the palette", async () => {
    values.set(key, JSON.stringify({ candles: { up: "#123" } }));
    values.set("drawings", "retain");
    const { getChartPalette, useChartPaletteStore } = await import("./chart-palette-store");
    const state = useChartPaletteStore.getState();
    state.setSection("lines", { primary: "#def" });
    state.setSeriesColor(2, "#abc");
    expect(getChartPalette().candles.up).toBe("#112233");
    expect(getChartPalette().lines.series[2]).toBe("#aabbcc");
    const previous = getChartPalette();
    state.setSection("candles", "red");
    for (const index of [-1, 6, 1.5, NaN, Infinity]) state.setSeriesColor(index, "#fff");
    state.setSeriesColor(0, "invalid");
    expect(getChartPalette()).toBe(previous);
    expect(JSON.parse(values.get(key)!)).toEqual(previous);
    state.reset();
    expect(getChartPalette()).toEqual(DEFAULT_CHART_PALETTE);
    expect(JSON.parse(values.get(key)!)).toEqual(DEFAULT_CHART_PALETTE);
    expect(values.get("drawings")).toBe("retain");
  });

  it("resets a single section without touching the others", async () => {
    const { getChartPalette, useChartPaletteStore } = await import("./chart-palette-store");
    useChartPaletteStore.getState().setSection("candles", { up: "#123", down: "#456", neutral: "#789" });
    useChartPaletteStore.getState().setSection("lines", { primary: "#abc" });
    useChartPaletteStore.getState().resetSection("candles");
    expect(getChartPalette().candles).toEqual(DEFAULT_CHART_PALETTE.candles);
    expect(getChartPalette().lines.primary).toBe("#aabbcc");
    expect(getChartPalette().heatmap).toEqual(DEFAULT_CHART_PALETTE.heatmap);
  });

  it("synchronizes cross-tab changes, removal and clear without writing them back", async () => {
    const { getChartPalette, subscribeChartPalette } = await import("./chart-palette-store");
    const listener = vi.fn();
    const unsubscribe = subscribeChartPalette(listener);
    listener.mockClear();
    storageListener({ key, newValue: JSON.stringify({ heatmap: { down: "#abc" } }), storageArea: storage as unknown as Storage });
    expect(getChartPalette().heatmap.down).toBe("#aabbcc");
    expect(listener).toHaveBeenCalledTimes(1);
    storageListener({ key: "unrelated", newValue: "{}" });
    storageListener({ key, newValue: "{}", storageArea: {} as Storage });
    expect(listener).toHaveBeenCalledTimes(1);
    storageListener({ key, newValue: null });
    expect(getChartPalette()).toEqual(DEFAULT_CHART_PALETTE);
    storageListener({ key, newValue: JSON.stringify({ candles: { up: "#123" } }) });
    storageListener({ key: null, newValue: null });
    expect(getChartPalette()).toEqual(DEFAULT_CHART_PALETTE);
    storageListener({ key, newValue: "{broken" });
    expect(getChartPalette()).toEqual(DEFAULT_CHART_PALETTE);
    expect(storage.setItem).not.toHaveBeenCalled();
    unsubscribe();
  });

  it("handles corrupt storage and failed reads and writes without losing in-memory edits", async () => {
    values.set(key, "{broken");
    const { getChartPalette, useChartPaletteStore } = await import("./chart-palette-store");
    expect(getChartPalette()).toEqual(DEFAULT_CHART_PALETTE);
    useChartPaletteStore.setState({ hydrated: false });
    storage.getItem.mockImplementationOnce(() => { throw new Error("blocked"); });
    expect(() => getChartPalette()).not.toThrow();
    expect(useChartPaletteStore.getState().storageAvailable).toBe(false);
    storage.setItem.mockImplementationOnce(() => { throw new Error("quota"); });
    useChartPaletteStore.getState().setSection("candles", { up: "#123" });
    expect(getChartPalette().candles.up).toBe("#112233");
    expect(useChartPaletteStore.getState().storageAvailable).toBe(false);
    useChartPaletteStore.getState().reset();
    expect(useChartPaletteStore.getState().storageAvailable).toBe(true);
  });

  it("overlays a non-persisted preview without touching storage and clears on edit", async () => {
    const { getChartPalette, useChartPaletteStore } = await import("./chart-palette-store");
    useChartPaletteStore.getState().setPreview({ candles: { up: "#abc" } });
    expect(getChartPalette().candles.up).toBe("#aabbcc");
    expect(storage.setItem).not.toHaveBeenCalled();
    // An explicit edit ends the preview overlay and persists the edit.
    useChartPaletteStore.getState().setSection("candles", { down: "#def" });
    expect(useChartPaletteStore.getState().previewPalette).toBeNull();
    expect(getChartPalette().candles.down).toBe("#ddeeff");
    expect(getChartPalette().candles.up).toBe(DEFAULT_CHART_PALETTE.candles.up);
    expect(storage.setItem).toHaveBeenCalled();
  });

  it("notifies subscribers when a preview is set and cleared", async () => {
    const { subscribeChartPalette, useChartPaletteStore } = await import("./chart-palette-store");
    const listener = vi.fn();
    const unsubscribe = subscribeChartPalette(listener);
    listener.mockClear();
    useChartPaletteStore.getState().setPreview({ candles: { up: "#abc" } });
    expect(listener).toHaveBeenCalledTimes(1);
    useChartPaletteStore.getState().setPreview(null);
    expect(listener).toHaveBeenCalledTimes(2);
    unsubscribe();
  });

  it("does not mark server reads as hydrated or prevent later client hydration", async () => {
    const browser = window;
    vi.stubGlobal("window", undefined);
    const { getChartPalette, useChartPaletteStore } = await import("./chart-palette-store");
    expect(getChartPalette()).toEqual(DEFAULT_CHART_PALETTE);
    expect(useChartPaletteStore.getState().hydrated).toBe(false);
    values.set(key, JSON.stringify({ candles: { neutral: "#abc" } }));
    vi.stubGlobal("window", browser);
    expect(getChartPalette().candles.neutral).toBe("#aabbcc");
  });
});
