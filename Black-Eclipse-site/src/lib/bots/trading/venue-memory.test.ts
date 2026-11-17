import { describe, expect, it } from "vitest";
import {
  VENUE_STORAGE_KEY,
  loadLastVenue,
  pickInitialVenue,
  rememberVenue,
  type StorageLike,
} from "./venue-memory";

function storage(): StorageLike & { map: Map<string, string> } {
  const map = new Map<string, string>();
  return {
    map,
    getItem: (key) => map.get(key) ?? null,
    setItem: (key, value) => {
      map.set(key, value);
    },
  };
}

describe("last-used venue memory", () => {
  it("remembers and reads the venue", () => {
    const store = storage();
    rememberVenue({ id: "brk_1", mode: "demo" }, store);
    expect(loadLastVenue(store)).toEqual({ id: "brk_1", mode: "demo" });
    expect(store.map.get(VENUE_STORAGE_KEY)).toContain("brk_1");
  });

  it("ignores corrupt or empty storage instead of crashing", () => {
    const store = storage();
    store.map.set(VENUE_STORAGE_KEY, "{not json");
    expect(loadLastVenue(store)).toBeNull();
    store.map.set(VENUE_STORAGE_KEY, JSON.stringify({ id: "" }));
    expect(loadLastVenue(store)).toBeNull();
    expect(loadLastVenue(null)).toBeNull();
  });

  it("never overwrites an explicit current choice", () => {
    expect(
      pickInitialVenue({
        currentId: "brk_current",
        mode: "demo",
        remembered: { id: "brk_1", mode: "demo" },
        available: [
          { id: "brk_current", mode: "demo" },
          { id: "brk_1", mode: "demo" },
        ],
      }),
    ).toBe("brk_current");
  });

  it("preselects the remembered venue when it still exists in the mode", () => {
    expect(
      pickInitialVenue({
        mode: "demo",
        remembered: { id: "brk_1", mode: "demo" },
        available: [{ id: "brk_1", mode: "demo" }],
      }),
    ).toBe("brk_1");
  });

  it("refuses a remembered venue from another mode or one that is gone", () => {
    expect(
      pickInitialVenue({
        mode: "live",
        remembered: { id: "brk_demo", mode: "demo" },
        available: [{ id: "brk_demo", mode: "demo" }],
      }),
    ).toBe("");
    expect(
      pickInitialVenue({
        mode: "demo",
        remembered: { id: "brk_deleted", mode: "demo" },
        available: [{ id: "brk_other", mode: "demo" }],
      }),
    ).toBe("");
  });

  it("never preselects a venue in shadow mode", () => {
    expect(
      pickInitialVenue({
        mode: "shadow",
        remembered: { id: "brk_1", mode: "demo" },
        available: [{ id: "brk_1", mode: "demo" }],
      }),
    ).toBe("");
  });
});
