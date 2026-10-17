import { describe, expect, it } from "vitest";
import { selectChannelActivity, type WatchedChannelMessage } from "./channel-diff";

function msg(over: Partial<WatchedChannelMessage>): WatchedChannelMessage {
  return { id: "m1", kind: "telegram", direction: "in", text: "hi", status: "ok", ...over };
}

describe("selectChannelActivity", () => {
  it("seeds on the first poll without notifying", () => {
    const { notifications, next } = selectChannelActivity([msg({})], new Set(), { seed: true });
    expect(notifications).toEqual([]);
    expect([...next]).toEqual(["m1"]);
  });

  it("notifies only for NEW inbound messages", () => {
    const seen = new Set(["m1"]);
    const feed = [msg({ id: "m2", text: "sell AAPL" }), msg({ id: "m1" }), msg({ id: "m3", direction: "out" })];
    const { notifications, next } = selectChannelActivity(feed, seen, { seed: false });
    expect(notifications.map((n) => n.messageId)).toEqual(["m2"]);
    expect(notifications[0].title).toBe("New telegram message");
    expect(notifications[0].body).toBe("sell AAPL");
    expect(next.has("m3")).toBe(true); // outbound tracked, never notified
  });

  it("titles a confirmation request distinctly", () => {
    const { notifications } = selectChannelActivity(
      [msg({ id: "m9", status: "confirmation_required" })],
      new Set(),
      { seed: false },
    );
    expect(notifications[0].title).toBe("Confirmation needed");
  });

  it("truncates a long body", () => {
    const { notifications } = selectChannelActivity([msg({ id: "mX", text: "x".repeat(500) })], new Set(), {
      seed: false,
    });
    expect(notifications[0].body.length).toBeLessThanOrEqual(121);
    expect(notifications[0].body.endsWith("…")).toBe(true);
  });
});
