import { describe, expect, it } from "vitest";
import {
  MAX_VISUALS,
  addVisual,
  inspectDataUrl,
  removeVisual,
  totalVisualBytes,
  updateVisualCaption,
  visualSummary,
  visualTeachingPrompt,
} from "./visuals";
import type { StrategyVisual } from "./types";

const PNG =
  "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==";

describe("reading an image", () => {
  it("accepts a png data URL and measures it", () => {
    const inspected = inspectDataUrl(PNG);
    expect(inspected.ok).toBe(true);
    expect(inspected.mime).toBe("image/png");
    expect(inspected.bytes).toBeGreaterThan(0);
  });

  it("refuses a remote URL (it can change under us)", () => {
    expect(inspectDataUrl("https://example.com/setup.png").ok).toBe(false);
    expect(inspectDataUrl("https://example.com/setup.png").error).toMatch(/PNG, JPEG/);
  });

  it("refuses an unsupported mime", () => {
    const gif = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw==";
    const inspected = inspectDataUrl(gif);
    expect(inspected.ok).toBe(false);
    expect(inspected.error).toMatch(/PNG, JPEG or WebP/);
  });
});

describe("attaching teaching images", () => {
  it("stores the caption, mime and size", () => {
    const result = addVisual([], { dataUrl: PNG, caption: "  enter after the retest  " });
    expect(result.error).toBeNull();
    expect(result.visual).toMatchObject({
      caption: "enter after the retest",
      mime: "image/png",
    });
    expect(result.visual!.id).toMatch(/^vis_/);
    expect(result.visuals).toHaveLength(1);
  });

  it("caps the number of images", () => {
    let visuals: StrategyVisual[] = [];
    for (let i = 0; i < MAX_VISUALS; i += 1) {
      const res = addVisual(visuals, { dataUrl: PNG, caption: `shot ${i}` });
      visuals = res.visuals;
    }
    const overflow = addVisual(visuals, { dataUrl: PNG, caption: "one too many" });
    expect(overflow.error).toContain(`${MAX_VISUALS}`);
    expect(overflow.visuals).toHaveLength(MAX_VISUALS);
  });

  it("refuses an image over 2 MB", () => {
    const huge = `data:image/png;base64,${"A".repeat(2_800_000)}`;
    const result = addVisual([], { dataUrl: huge, caption: "big" });
    expect(result.visual).toBeNull();
    expect(result.error).toMatch(/2 MB/);
  });

  it("does not silently drop a bad image", () => {
    const result = addVisual([], { dataUrl: "not-an-image", caption: "x" });
    expect(result.error).toBeTruthy();
    expect(result.visuals).toEqual([]);
  });

  it("removes and re-captions", () => {
    const added = addVisual([], { dataUrl: PNG, caption: "first" }).visual!;
    const renamed = updateVisualCaption([added], added.id, "second");
    expect(renamed[0].caption).toBe("second");
    expect(removeVisual(renamed, added.id)).toEqual([]);
  });
});

describe("teaching the bot", () => {
  it("says the images are guidance, never market data", () => {
    const added = addVisual([], { dataUrl: PNG, caption: "failed breakout to avoid" }).visual!;
    const prompt = visualTeachingPrompt([added]);
    expect(prompt).toContain("failed breakout to avoid");
    expect(prompt).toMatch(/not live market data/i);
    expect(prompt).toMatch(/data wins/i);
  });

  it("is empty when there is nothing to teach", () => {
    expect(visualTeachingPrompt([])).toBe("");
    expect(visualSummary([])).toMatch(/No reference images/);
  });

  it("summarises count and size", () => {
    const added = addVisual([], { dataUrl: PNG, caption: "x" }).visual!;
    expect(visualSummary([added])).toContain("1 reference image");
    expect(totalVisualBytes([added])).toBe(added.bytes);
  });
});
