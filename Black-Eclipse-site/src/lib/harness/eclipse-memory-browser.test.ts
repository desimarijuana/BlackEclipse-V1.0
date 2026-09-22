import { beforeEach, describe, expect, it, vi } from "vitest";
import { clientIsOperator, listMemories, memoryHealth } from "./eclipse-memory-browser";

// The browser client must stay client-safe (fetch only) and must surface API
// errors verbatim. Operator controls are a presentation hint; the server
// re-checks authorization independently.

describe("eclipse-memory browser client", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("clientIsOperator is false outside a browser (SSR-safe)", () => {
    expect(clientIsOperator()).toBe(false);
  });

  it("memoryHealth fetches the health route", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
      ok: true,
      status: 200,
      json: async () => ({ ok: true, path: "eclipse-memory.db" }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    const health = await memoryHealth();
    expect(health.ok).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/eclipse-memory/health");
  });

  it("listMemories builds the filter query", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
      ok: true,
      status: 200,
      json: async () => ({ memories: [] }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    await listMemories({ memoryType: "preference", status: "active" });
    const url = String(fetchMock.mock.calls[0]?.[0] ?? "");
    expect(url).toContain("memoryType=preference");
    expect(url).toContain("status=active");
  });

  it("surfaces an API error message", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({
      ok: false,
      status: 503,
      json: async () => ({ error: "runtime unavailable" }),
    })) as unknown as typeof fetch);
    await expect(memoryHealth()).rejects.toThrow("runtime unavailable");
  });
});
