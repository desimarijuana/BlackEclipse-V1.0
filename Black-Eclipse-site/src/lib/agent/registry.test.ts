import { describe, it, expect } from "vitest";
import { statusFromEvent, unwrapEventPayload } from "./registry";

// Regression: the runtime wraps events in a full envelope
// (`{ type, data: { text } }`). Reading `data.text` off the envelope silently
// yielded "" for every token, so the answer never streamed — it appeared whole
// at the end. These tests pin the unwrap that fixed it.

describe("unwrapEventPayload", () => {
  it("unwraps a runtime event envelope to its inner data", () => {
    const envelope = {
      id: "evt_1",
      runId: "run_1",
      type: "model.delta",
      seq: 4,
      data: { text: "I'll pull the latest", finalizing: false },
      transient: true,
    };
    const payload = unwrapEventPayload(envelope);
    expect(payload.text).toBe("I'll pull the latest");
  });

  it("leaves a front-door client.* event untouched", () => {
    const payload = unwrapEventPayload({ output: "final answer", status: "completed" });
    expect(payload.output).toBe("final answer");
  });

  it("carries the event type through for envelope payloads", () => {
    const payload = unwrapEventPayload({ type: "tool.requested", data: { name: "market_get_quote" } });
    expect(payload.name).toBe("market_get_quote");
    expect(payload.eventType).toBe("tool.requested");
  });

  it("does not mistake an array data field for an envelope", () => {
    const payload = unwrapEventPayload({ data: [1, 2, 3], text: "keep" });
    expect(payload.text).toBe("keep");
  });
});

describe("statusFromEvent", () => {
  it("maps tool events to a labelled status with the tool name", () => {
    const status = statusFromEvent("tool.requested", { name: "market_get_quote" });
    expect(status?.phase).toBe("tool");
    expect(status?.label).toContain("market_get_quote");
  });

  it("maps model.delta to writing", () => {
    expect(statusFromEvent("model.delta", { text: "x" })?.phase).toBe("writing");
  });

  it("returns null for an unknown event", () => {
    expect(statusFromEvent("something.else", {})).toBeNull();
  });
});
