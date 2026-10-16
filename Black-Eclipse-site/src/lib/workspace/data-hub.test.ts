import { describe, it, expect } from "vitest";

// DataHub is a client module ('use client'), but the hub class itself is plain
// TS. We test the provenance envelope handling: a topic may report the SERVER's
// provenance, and the hub must pass it through unchanged rather than inferring
// LIVE/UNAVAILABLE. Raw payloads keep the existing inference behavior.
//
// React hooks are imported by the module but only invoked by useTopic, so
// importing here in a node environment is safe.

import { dataHub, registerTopic, type HubTopic } from "./data-hub";

function register(id: string, payload: unknown, ttl = 60_000): void {
  const topic: HubTopic = { id, ttl, fetch: async () => payload };
  registerTopic(topic);
}

describe("DataHub provenance envelopes", () => {
  it("passes a server-reported CUSTOM provenance through unchanged", async () => {
    register("t:custom", { data: { rows: 1 }, source: "CUSTOM", sourceId: "My Market API" });
    await dataHub.refresh("t:custom");
    const entry = dataHub.get("t:custom");
    expect(entry.source).toBe("CUSTOM");
    expect(entry.sourceId).toBe("My Market API");
    expect(entry.data).toEqual({ rows: 1 });
  });

  it("marks a null-envelope topic UNAVAILABLE", async () => {
    register("t:unavail", { data: null, source: "UNAVAILABLE" });
    await dataHub.refresh("t:unavail");
    expect(dataHub.get("t:unavail").source).toBe("UNAVAILABLE");
    expect(dataHub.get("t:unavail").data).toBeNull();
  });

  it("infers LIVE for a raw payload first fetch", async () => {
    register("t:raw", [{ a: 1 }]);
    await dataHub.refresh("t:raw");
    const entry = dataHub.get("t:raw");
    expect(entry.source).toBe("LIVE");
    expect(entry.data).toEqual([{ a: 1 }]);
  });

  it("does not unwrap a plain payload that merely contains a data key", async () => {
    register("t:datakey", { data: { nested: true } });
    await dataHub.refresh("t:datakey");
    const entry = dataHub.get("t:datakey");
    // No valid DataSource tag → treated as raw data, not an envelope.
    expect(entry.data).toEqual({ data: { nested: true } });
    expect(entry.source).toBe("LIVE");
  });

  it("reports UNAVAILABLE when the fetch throws", async () => {
    registerTopic({
      id: "t:throws",
      ttl: 60_000,
      fetch: async () => {
        throw new Error("boom");
      },
    });
    await dataHub.refresh("t:throws");
    const entry = dataHub.get("t:throws");
    expect(entry.source).toBe("UNAVAILABLE");
    expect(entry.error).toBe("boom");
  });

  it("passes HISTORICAL provenance through", async () => {
    register("t:hist", { data: [1, 2], source: "HISTORICAL" });
    await dataHub.refresh("t:hist");
    expect(dataHub.get("t:hist").source).toBe("HISTORICAL");
  });
});

describe("DataHub visibility catch-up", () => {
  it("refreshVisible refreshes subscribed topics and skips dormant ones", async () => {
    let subCalls = 0;
    let dormantCalls = 0;
    registerTopic({ id: "t:v-sub", ttl: 60_000, fetch: async () => { subCalls += 1; return [1]; } });
    registerTopic({ id: "t:v-dormant", ttl: 60_000, fetch: async () => { dormantCalls += 1; return [2]; } });

    const unsub = dataHub.subscribe("t:v-sub", () => {});
    await new Promise((r) => setTimeout(r, 0));
    expect(subCalls).toBe(1); // initial fetch on subscribe

    dataHub.refreshVisible();
    await new Promise((r) => setTimeout(r, 0));
    expect(subCalls).toBe(2); // refreshed because it has a listener
    expect(dormantCalls).toBe(0); // never fetched — nobody is watching it

    unsub();
  });
});
