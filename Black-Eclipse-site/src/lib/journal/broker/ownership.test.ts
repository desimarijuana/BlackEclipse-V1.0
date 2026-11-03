import { describe, it, expect } from "vitest";
import { brokerOwnedFieldsIn, isValidBrokerConnectionId } from "./ownership";

describe("brokerOwnedFieldsIn", () => {
  it("flags execution fields", () => {
    expect(
      brokerOwnedFieldsIn({ entry: 100, exit: 110, stopLoss: 95, quantity: 1 }),
    ).toEqual(["entry", "exit", "stopLoss", "quantity"]);
  });

  it("allows analysis fields", () => {
    expect(
      brokerOwnedFieldsIn({
        notes: "followed the plan",
        emotion: "Calm",
        confidence: 4,
        grade: "A",
        checklist: { rule1: true },
        strategyId: "s1",
        tagNames: ["breakout"],
      }),
    ).toEqual([]);
  });

  it("treats an explicit undefined as absent (JSON cannot send it anyway)", () => {
    expect(brokerOwnedFieldsIn({ entry: undefined })).toEqual([]);
  });
});

describe("isValidBrokerConnectionId", () => {
  it("accepts generated ids", () => {
    expect(isValidBrokerConnectionId("cm1abc_DEF-123")).toBe(true);
  });

  it("rejects path traversal / empty / whitespace", () => {
    expect(isValidBrokerConnectionId("../etc/passwd")).toBe(false);
    expect(isValidBrokerConnectionId("a b")).toBe(false);
    expect(isValidBrokerConnectionId("")).toBe(false);
    expect(isValidBrokerConnectionId(42)).toBe(false);
  });
});
