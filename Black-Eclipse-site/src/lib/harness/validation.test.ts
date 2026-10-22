import { describe, it, expect } from "vitest";
import { validateRunInput, assertRunInput, MAX_QUERY_LENGTH } from "./validation";
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

  it("accepts a long query — a turn is whatever the person pasted", () => {
    // The old 4 000-char cap rejected ordinary long prompts with a generic
    // "Something went wrong". The cap now only bounds one request body.
    const result = validateRunInput({ query: "x".repeat(50_000) });
    expect(result.ok).toBe(true);
    expect(result.value?.query.length).toBe(50_000);
  });

  it("rejects an over-long query", () => {
    const result = validateRunInput({ query: "x".repeat(MAX_QUERY_LENGTH + 1) });
    expect(result.ok).toBe(false);
    expect(result.issues[0]).toContain("too long");
  });

  it("keeps a long prior turn intact as history", () => {
    // A message the composer accepted must not be silently cut down when it
    // comes back as history on the next turn.
    const result = validateRunInput({
      query: "follow up",
      history: [{ role: "user", content: "y".repeat(50_000) }],
    });
    expect(result.ok).toBe(true);
    expect(result.value?.history?.[0].content.length).toBe(50_000);
  });

  it("drops the OLDEST turns (never slices one) when the history is over budget", () => {
    const history = Array.from({ length: 12 }, (_, i) => ({
      role: "user" as const,
      content: String(i).padEnd(50_000, "x"),
    }));
    const result = validateRunInput({ query: "follow up", history });
    expect(result.ok).toBe(true);
    const kept = result.value?.history ?? [];
    // The newest turn is kept; the oldest ones are dropped whole.
    expect(kept.length).toBeLessThan(history.length);
    expect(kept[kept.length - 1].content).toBe(history[history.length - 1].content);
    // No turn was sliced: every kept turn is a full turn.
    for (const turn of kept) expect(turn.content.length).toBe(50_000);
  });

  it("rejects a non-object context", () => {
    const result = validateRunInput({ query: "hi", context: [1, 2, 3] });
    expect(result.ok).toBe(false);
    expect(result.issues).toContain("context must be an object");
  });

  it("skips empty history turns instead of rejecting the request", () => {
    // A cancelled/failed assistant turn persists as content:"". It must not
    // brick later messages: the run is accepted with that turn dropped.
    const result = validateRunInput({
      query: "follow up",
      history: [
        { role: "user", content: "first question" },
        { role: "assistant", content: "" },
        { role: "user", content: "  " },
        { role: "assistant", content: "a real answer" },
      ],
    });
    expect(result.ok).toBe(true);
    expect(result.value?.history).toEqual([
      { role: "user", content: "first question" },
      { role: "assistant", content: "a real answer" },
    ]);
  });

  it("still rejects a malformed history role", () => {
    const result = validateRunInput({ query: "hi", history: [{ role: "system", content: "x" }] });
    expect(result.ok).toBe(false);
  });

  it("accepts and bounds attached documents", () => {    const result = validateRunInput({
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
      text: "x".repeat(100_000),
    }));
    const result = validateRunInput({ query: "hi", documents });
    expect(result.ok).toBe(false);
    expect(result.issues.some((i) => i.includes("char limit"))).toBe(true);
  });

  it("carries truncation provenance through to the run payload", () => {
    const result = validateRunInput({
      query: "hi",
      documents: [{ name: "deck.pdf", text: "first part", truncated: true, originalChars: 90_000 }],
    });
    expect(result.ok).toBe(true);
    expect(result.value?.documents).toEqual([
      { name: "deck.pdf", text: "first part", truncated: true, originalChars: 90_000 },
    ]);
  });

  it("marks a document the validator itself shortened", () => {
    const result = validateRunInput({
      query: "hi",
      documents: [{ name: "big.txt", text: "y".repeat(100_500) }],
    });
    expect(result.ok).toBe(true);
    const doc = result.value?.documents?.[0];
    expect(doc?.text.length).toBe(100_000);
    expect(doc?.truncated).toBe(true);
    expect(doc?.originalChars).toBe(100_500);
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
