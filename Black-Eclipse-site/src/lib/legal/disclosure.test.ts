import { describe, expect, it } from "vitest";
import {
  AI_OUTPUT_FULL,
  ORDER_PREVIEW_NOTICE,
  RESPONSIBILITY_SHORT,
  RESPONSIBILITY_STATEMENT,
  RISK_ACK_LABEL,
  RISK_DISCLOSURE_FULL,
  TRADE_RESPONSIBILITY_LABEL,
} from "./disclosure";

describe("legal disclosure copy", () => {
  it("states the ownership position in the full notice", () => {
    expect(RISK_DISCLOSURE_FULL).toContain(RESPONSIBILITY_STATEMENT);
    expect(RISK_DISCLOSURE_FULL).toContain("does not manage money");
    expect(RISK_DISCLOSURE_FULL).toContain("share profits or losses");
  });

  it("keeps the first-run acknowledgement short and specific", () => {
    expect(RISK_ACK_LABEL).toMatch(/research and order-entry tool/i);
    expect(RISK_ACK_LABEL).toMatch(/not my adviser or broker/i);
    expect(RISK_ACK_LABEL).toMatch(/own risk/i);
  });

  it("labels the assistant as fallible without calling the product bad", () => {
    expect(AI_OUTPUT_FULL).toContain("AI agent");
    expect(AI_OUTPUT_FULL).toContain("can be wrong");
    expect(AI_OUTPUT_FULL).toContain("make the call yourself");
    expect(AI_OUTPUT_FULL.toLowerCase()).not.toContain("guaranteed");
  });

  it("makes the order and trade responsibility explicit", () => {
    expect(ORDER_PREVIEW_NOTICE).toMatch(/send this order to your broker/i);
    expect(ORDER_PREVIEW_NOTICE).toMatch(/does not guarantee execution/i);
    expect(TRADE_RESPONSIBILITY_LABEL).toMatch(/my decision and my responsibility/i);
    expect(TRADE_RESPONSIBILITY_LABEL).toMatch(/own risk/i);
    expect(RESPONSIBILITY_SHORT).toContain("account");
  });
});
