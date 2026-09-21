import { describe, it, expect } from "vitest";
import { validateRunInput, assertRunInput } from "./validation";
import { HarnessError } from "./errors";

describe("validateRunInput (front door)", () => {
  it("accepts a minimal query and normalizes ticker/market", () => {
    const result = validateRunInput({ query: "  analyze aapl  ", ticker: "aapl", market: "us" });
    expect(result.ok).toBe(true);
    expect(result.value).toEqual({ query: "analyze aapl", ticker: "AAPL", market: "US", context: undefined });
  });

  it("rejects a missing query", () => {
    const result = validateRunInput({});
    expect(result.ok).toBe(false);
    expect(result.issues).toContain("query is required");
  });

  it("rejects non-object input", () => {
    expect(validateRunInput(null).ok).toBe(false);
    expect(validateRunInput("nope").ok).toBe(false);
  });

  it("rejects an over-long query", () => {
    const result = validateRunInput({ query: "x".repeat(4001) });
    expect(result.ok).toBe(false);
    expect(result.issues[0]).toContain("too long");
  });

  it("rejects a non-object context", () => {
    const result = validateRunInput({ query: "hi", context: [1, 2, 3] });
    expect(result.ok).toBe(false);
    expect(result.issues).toContain("context must be an object");
  });

  it("assertRunInput throws a structured HarnessError", () => {
    expect(() => assertRunInput({})).toThrow(HarnessError);
    try {
      assertRunInput({});
    } catch (err) {
      expect((err as HarnessError).code).toBe("INVALID_INPUT");
    }
  });
});
