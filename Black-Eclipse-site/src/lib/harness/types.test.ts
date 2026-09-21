import { describe, it, expect } from "vitest";
import { newRunId } from "./ids";

describe("newRunId", () => {
  it("produces unique, prefixed ids", () => {
    const ids = new Set(Array.from({ length: 50 }, () => newRunId()));
    expect(ids.size).toBe(50);
    for (const id of ids) expect(id).toMatch(/^run_[0-9a-f-]{36}$/);
  });
});
