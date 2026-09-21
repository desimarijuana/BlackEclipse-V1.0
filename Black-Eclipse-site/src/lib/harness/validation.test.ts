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

  it("accepts and bounds attached documents", () => {
    const result = validateRunInput({
      query: "summarize this",
      documents: [{ name: "a.md", text: "# Heading" }],
    });
    expect(result.ok).toBe(true);
    expect(result.value?.documents).toEqual([{ name: "a.md", text: "# Heading" }]);
  });

  it("rejects a document without a name or text", () => {
    expect(validateRunInput({ query: "hi", documents: [{ text: "x" }] }).ok).toBe(false);
    expect(validateRunInput({ query: "hi", documents: [{ name: "a.md" }] }).ok).toBe(false);
  });

  it("caps the combined document size", () => {
    const documents = Array.from({ length: 5 }, (_, i) => ({
      name: `d${i}.txt`,
      text: "x".repeat(20_000),
    }));
    const result = validateRunInput({ query: "hi", documents });
    expect(result.ok).toBe(false);
    expect(result.issues.some((i) => i.includes("char limit"))).toBe(true);
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
