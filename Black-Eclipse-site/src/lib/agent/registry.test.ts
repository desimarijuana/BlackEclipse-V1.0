import { describe, it, expect, vi, afterEach } from "vitest";
import { statusFromEvent, unwrapEventPayload, getAgentProvider } from "./registry";

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

describe("eclipseAgent chat — a refused request", () => {
  afterEach(() => vi.unstubAllGlobals());

  it("does not repeat a request the front door refused, and keeps the code", async () => {
    // The old 4 000-char cap made a long message fail with a bare
    // "Something went wrong". A refused request must fail ONCE, with the
    // front door's code, instead of being sent again down the fallback path.
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ error: "message is too long", code: "INVALID_INPUT" }), {
        status: 400,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      getAgentProvider().chat([{ role: "user", content: "a long message" }], undefined, {
        onEvent: () => {},
      }),
    ).rejects.toMatchObject({ code: "INVALID_INPUT", status: 400 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("still falls back to the one-shot path when the server fails", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(JSON.stringify({ error: "runtime unavailable", code: "RUNTIME_UNAVAILABLE" }), {
        status: 503,
        headers: { "content-type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(
      getAgentProvider().chat([{ role: "user", content: "hello" }], undefined, {
        onEvent: () => {},
      }),
    ).rejects.toMatchObject({ code: "RUNTIME_UNAVAILABLE", status: 503 });
    // A refused request is not repeated — the same request would fail the
    // same way, and the run never started.
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("falls back to the one-shot path when the streaming endpoint is missing", async () => {
    // An older front door has no /stream route: the one-shot path still works.
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/stream")) {
        return new Response(JSON.stringify({ error: "not found" }), { status: 404 });
      }
      return new Response(JSON.stringify({ content: "the answer" }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    const reply = await getAgentProvider().chat([{ role: "user", content: "hello" }], undefined, {
      onEvent: () => {},
    });
    expect(reply).toBe("the answer");
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
