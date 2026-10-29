import { describe, expect, it } from "vitest";
import { buildDraftMessages, extractSpecJson } from "./draft-spec";

describe("extractSpecJson", () => {
  it("parses a bare JSON object", () => {
    expect(extractSpecJson('{"a":1}')).toEqual({ a: 1 });
  });

  it("parses a fenced JSON block", () => {
    expect(extractSpecJson('Here you go:\n```json\n{"a":{"b":2}}\n```\n')).toEqual({ a: { b: 2 } });
  });

  it("rejects non-JSON and non-objects", () => {
    expect(extractSpecJson("no json here")).toBeNull();
    expect(extractSpecJson("[1,2,3]")).toBeNull();
    expect(extractSpecJson("")).toBeNull();
    expect(extractSpecJson(null)).toBeNull();
  });
});

describe("buildDraftMessages", () => {
  it("includes the prompt, symbol and timeframe", () => {
    const messages = buildDraftMessages({ prompt: "Buy when RSI is low", symbol: "BTC-USD", timeframe: "4h" });
    expect(messages).toHaveLength(2);
    expect(messages[1].content).toContain("Buy when RSI is low");
    expect(messages[1].content).toContain("BTC-USD");
    expect(messages[1].content).toContain("4h");
  });

  it("carries the real rule DSL in the system prompt", () => {
    const [system] = buildDraftMessages({ prompt: "x" });
    expect(String(system.content)).toContain("cross_above");
    expect(String(system.content)).toContain('"type": "condition"');
    expect(String(system.content)).toContain("next_open");
  });
});
