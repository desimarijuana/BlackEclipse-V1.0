import { describe, expect, it } from "vitest";
import {
  evaluateConditions,
  levelTouch,
  needsCandles,
  type ConditionNode,
} from "./conditionEvaluator";

function leaf(partial: Record<string, unknown>): ConditionNode {
  return {
    compareMode: "value",
    ...partial,
  } as ConditionNode;
}

function win(entries: Array<[string, number[]]>) {
  return new Map(entries);
}

describe("conditionEvaluator", () => {
  it("value compare: > fires when current value exceeds target", () => {
    const w = win([["CLOSE()", [100, 105]]]);
    const r = evaluateConditions(
      [leaf({ indicator: "CLOSE", operator: ">", value: 100 })],
      "AND",
      w
    );
    expect(r.triggered).toBe(true);
  });

  it("value compare: < does not fire above target", () => {
    const w = win([["CLOSE()", [105]]]);
    const r = evaluateConditions(
      [leaf({ indicator: "CLOSE", operator: "<", value: 100 })],
      "AND",
      w
    );
    expect(r.triggered).toBe(false);
  });

  it(">= / <= boundaries", () => {
    const w = win([["CLOSE()", [100]]]);
    expect(
      evaluateConditions([leaf({ indicator: "CLOSE", operator: ">=", value: 100 })], "AND", w).triggered
    ).toBe(true);
    expect(
      evaluateConditions([leaf({ indicator: "CLOSE", operator: "<=", value: 100 })], "AND", w).triggered
    ).toBe(true);
    expect(
      evaluateConditions([leaf({ indicator: "CLOSE", operator: ">", value: 100 })], "AND", w).triggered
    ).toBe(false);
  });

  it("offset reads N bars back", () => {
    const w = win([["CLOSE()", [100, 200]]]);
    const r = evaluateConditions(
      [leaf({ indicator: "CLOSE", operator: ">", value: 150, offset: 1 })],
      "AND",
      w
    );
    expect(r.triggered).toBe(false); // 1 bar back = 100
  });

  it("between uses value..value2 (order-independent)", () => {
    const w = win([["RSI({\"n\":14})", [45]]]);
    const r = evaluateConditions(
      [leaf({ indicator: "RSI", params: { n: 14 }, operator: "between", value: 70, value2: 30 })],
      "AND",
      w
    );
    expect(r.triggered).toBe(true);
    const r2 = evaluateConditions(
      [leaf({ indicator: "RSI", params: { n: 14 }, operator: "between", value: 30, value2: 40 })],
      "AND",
      w
    );
    expect(r2.triggered).toBe(false);
  });

  it("rising / falling compare to the previous sample", () => {
    const w = win([["CLOSE()", [100, 102]]]);
    expect(
      evaluateConditions([leaf({ indicator: "CLOSE", operator: "rising" })], "AND", w).triggered
    ).toBe(true);
    expect(
      evaluateConditions([leaf({ indicator: "CLOSE", operator: "falling" })], "AND", w).triggered
    ).toBe(false);
  });

  it("crosses_above: prev<=targetPrev && curr>targetCurr", () => {
    const w = win([
      ["SMA({\"n\":20})", [9, 11]],
      ["SMA({\"n\":50})", [10, 10]],
    ]);
    const cond = {
      compareMode: "indicator" as const,
      indicator: "SMA",
      params: { n: 20 },
      operator: "crosses_above",
      compareIndicator: "SMA",
      compareParams: { n: 50 },
    };
    expect(evaluateConditions([cond], "AND", w).triggered).toBe(true);
    // Already above previously → not a fresh cross.
    const w2 = win([
      ["SMA({\"n\":20})", [11, 12]],
      ["SMA({\"n\":50})", [10, 10]],
    ]);
    expect(evaluateConditions([cond], "AND", w2).triggered).toBe(false);
  });

  it("crosses_below mirrors crosses_above", () => {
    const w = win([
      ["SMA({\"n\":20})", [11, 9]],
      ["SMA({\"n\":50})", [10, 10]],
    ]);
    const cond = {
      compareMode: "indicator" as const,
      indicator: "SMA",
      params: { n: 20 },
      operator: "crosses_below",
      compareIndicator: "SMA",
      compareParams: { n: 50 },
    };
    expect(evaluateConditions([cond], "AND", w).triggered).toBe(true);
  });

  it("== is a LEVEL-TOUCH: fires when diff changes sign between samples", () => {
    // 280.35 → 280.45 skips 280.40 exactly; sign flip means it passed through.
    expect(levelTouch(280.45, 280.4, 280.35, 280.4)).toBe(true);
    expect(levelTouch(280.3, 280.4, 280.35, 280.4)).toBe(false);
  });

  it("== fires on an exact hit within tolerance", () => {
    const w = win([["CLOSE()", [280.4]]]);
    const r = evaluateConditions(
      [leaf({ indicator: "CLOSE", operator: "==", value: 280.4 })],
      "AND",
      w
    );
    expect(r.triggered).toBe(true);
  });

  it("== does not fire when price stays strictly above the level", () => {
    const w = win([["CLOSE()", [280.5, 280.6]]]);
    const r = evaluateConditions(
      [leaf({ indicator: "CLOSE", operator: "==", value: 280.4 })],
      "AND",
      w
    );
    expect(r.triggered).toBe(false);
  });

  it("AND logic requires all children", () => {
    const w = win([["CLOSE()", [105]], ["VOLUME()", [1000]]]);
    const tree = [
      leaf({ indicator: "CLOSE", operator: ">", value: 100 }),
      leaf({ indicator: "VOLUME", operator: ">", value: 5000 }),
    ];
    expect(evaluateConditions(tree, "AND", w).triggered).toBe(false);
  });

  it("OR logic fires when any child fires (short-circuit)", () => {
    const w = win([["CLOSE()", [105]], ["VOLUME()", [1000]]]);
    const tree = [
      leaf({ indicator: "CLOSE", operator: ">", value: 100 }),
      leaf({ indicator: "VOLUME", operator: ">", value: 5000 }),
    ];
    const r = evaluateConditions(tree, "OR", w);
    expect(r.triggered).toBe(true);
    // Short-circuit: second leaf never evaluated.
    expect(r.details).toHaveLength(1);
  });

  it("nested groups recurse with their own logic", () => {
    const w = win([["CLOSE()", [105]], ["VOLUME()", [6000]], ["CHANGE_PCT()", [-1]]]);
    const tree = {
      children: [
        leaf({ indicator: "CLOSE", operator: ">", value: 100 }),
        {
          children: [
            leaf({ indicator: "VOLUME", operator: ">", value: 5000 }),
            leaf({ indicator: "CHANGE_PCT", operator: ">", value: 0 }),
          ],
          logic: "AND",
        },
      ],
      logic: "AND",
    };
    expect(evaluateConditions(tree, "AND", w).triggered).toBe(false);
    const treeOr = { ...tree, children: [tree.children[0], { ...(tree.children[1] as object), logic: "OR" }] };
    expect(evaluateConditions(treeOr, "AND", w).triggered).toBe(true);
  });

  it("negate flips a group's result", () => {
    const w = win([["CLOSE()", [105]]]);
    const tree = {
      children: [leaf({ indicator: "CLOSE", operator: ">", value: 100 })],
      logic: "AND" as const,
      negate: true,
    };
    expect(evaluateConditions(tree, "AND", w).triggered).toBe(false);
  });

  it("NON-FINITE GUARD: Infinity fails every comparison and sets an error", () => {
    const w = win([["SMA({\"n\":20})", [Infinity]]]);
    const r = evaluateConditions(
      [leaf({ indicator: "SMA", params: { n: 20 }, operator: ">", value: 100 })],
      "AND",
      w
    );
    expect(r.triggered).toBe(false);
    expect(r.hasError).toBe(true);
    expect(r.details[0].error).toContain("non-finite");
  });

  it("NON-FINITE GUARD: -Infinity and NaN fail too", () => {
    for (const bad of [-Infinity, NaN]) {
      const w = win([["CLOSE()", [bad]]]);
      const r = evaluateConditions(
        [leaf({ indicator: "CLOSE", operator: "<", value: 1e9 })],
        "AND",
        w
      );
      expect(r.triggered).toBe(false);
      expect(r.hasError).toBe(true);
    }
  });

  it("missing history is treated as non-finite failure, not a fire", () => {
    const w = win([["CLOSE()", []]]);
    const r = evaluateConditions(
      [leaf({ indicator: "CLOSE", operator: ">", value: 0 })],
      "AND",
      w
    );
    expect(r.triggered).toBe(false);
    expect(r.hasError).toBe(true);
  });

  it("evaluateGroup recurses into a top-level group node", () => {
    const w = win([["CLOSE()", [50]]]);
    const tree = {
      children: [leaf({ indicator: "CLOSE", operator: "<", value: 100 })],
      logic: "AND" as const,
    };
    expect(evaluateConditions(tree, "AND", w).triggered).toBe(true);
  });

  it("needsCandles: snapshot-only false, indicator true", () => {
    const snapshot = [leaf({ indicator: "CLOSE", operator: ">", value: 100 })];
    const candle = [
      leaf({
        compareMode: "indicator" as const,
        indicator: "RSI",
        params: { n: 14 },
        operator: "crosses_below",
        compareIndicator: "SMA",
        compareParams: { n: 20 },
      }),
    ];
    expect(needsCandles(snapshot)).toBe(false);
    expect(needsCandles(candle)).toBe(true);
  });
});