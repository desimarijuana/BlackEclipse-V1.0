import { beforeEach, describe, expect, it, vi } from "vitest";
import { clientIsOperator, listMemories, memoryHealth, memoryLifecycle, memoryRetention, memorySemanticStatus, restoreMemory } from "./eclipse-memory-browser";

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

  it("memoryLifecycle builds the view query", async () => {
    const fetchMock = vi.fn(async (_url: string) => ({
      ok: true,
      status: 200,
      json: async () => ({ counts: { active: 0 }, views: {}, budget: { limit: 0, active: 0, unlimited: true, full: false, remaining: null } }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    await memoryLifecycle("never-used");
    const url = String(fetchMock.mock.calls[0]?.[0] ?? "");
    expect(url).toContain("/api/eclipse-memory/lifecycle");
    expect(url).toContain("view=never-used");
  });

  it("restoreMemory posts to the restore action", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
      ok: true,
      status: 200,
      json: async () => ({ success: true, memory: {} }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    await restoreMemory("mem_1");
    const url = String(fetchMock.mock.calls[0]?.[0] ?? "");
    expect(url).toContain("/memories/mem_1/restore");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
  });

  it("memoryRetention fetches the retention route", async () => {
    const fetchMock = vi.fn(async (_url: string) => ({
      ok: true,
      status: 200,
      json: async () => ({ retentionDays: 30, automaticExpiryEnabled: true, explicitMemoriesExempt: true, lastSweep: null }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    const status = await memoryRetention();
    expect(status.automaticExpiryEnabled).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/eclipse-memory/retention");
  });

  it("memorySemanticStatus fetches the semantic-status route", async () => {
    const fetchMock = vi.fn(async (_url: string) => ({
      ok: true,
      status: 200,
      json: async () => ({ mode: "lexical", lexicalActive: true, semanticEnabled: false, semanticAvailable: true, backend: "char-ngram", detectorVersion: "semantic-v1", reason: "disabled" }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    const status = await memorySemanticStatus();
    expect(status.mode).toBe("lexical");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/eclipse-memory/semantic-status");
  });
});
