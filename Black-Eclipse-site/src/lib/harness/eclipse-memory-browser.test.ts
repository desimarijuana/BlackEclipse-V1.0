import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  clientIsOperator, listMemories, memoryHealth, memoryLifecycle, memoryProfile,
  memoryProviderSearch, memoryProviderStatus, memoryRetention,
  memorySemanticStatus, rebuildProfile, restoreMemory,
  sessionSearch, sessionSearchHealth,
  listChatSessions, listProfiles, forkChatSession,
} from "./eclipse-memory-browser";

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

  it("memoryProfile passes a scopeId query", async () => {
    const fetchMock = vi.fn(async (_url: string) => ({
      ok: true,
      status: 200,
      json: async () => ({ success: true, snapshot: { selectedIds: [] }, prompt: "" }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    await memoryProfile("u1");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/eclipse-memory/profile?scopeId=u1");
  });

  it("rebuildProfile posts to the profile rebuild route", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
      ok: true,
      status: 200,
      json: async () => ({ success: true, rebuilt: true, snapshot: { selectedIds: [] }, prompt: "" }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    await rebuildProfile();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/eclipse-memory/profile/rebuild");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
  });

  it("sessionSearch builds the query with filters", async () => {
    const fetchMock = vi.fn(async (_url: string) => ({
      ok: true,
      status: 200,
      json: async () => ({ available: true, engine: "fts5", results: [], hasMore: false }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    await sessionSearch({ q: "reporting currency", limit: 5 });
    const url = String(fetchMock.mock.calls[0]?.[0]);
    expect(url.startsWith("/api/session-search?")).toBe(true);
    expect(url).toContain("q=reporting+currency");
    expect(url).toContain("limit=5");
  });

  it("sessionSearchHealth fetches the health route", async () => {
    const fetchMock = vi.fn(async (_url: string) => ({
      ok: true,
      status: 200,
      json: async () => ({ fts5: true, indexed: 3, retentionDays: 90, historyEnabled: true, indexingEnabled: true }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    const health = await sessionSearchHealth();
    expect(health.fts5).toBe(true);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/session-search/health");
  });

  it("memoryProviderStatus fetches the provider status route", async () => {
    const fetchMock = vi.fn(async (_url: string) => ({
      ok: true,
      status: 200,
      json: async () => ({
        success: true, externalEnabled: false, providerCount: 1, nativeCount: 1,
        externalCount: 0, available: ["native"], providers: [], note: "",
      }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    const status = await memoryProviderStatus();
    expect(status.nativeCount).toBe(1);
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/memory-providers/status");
  });

  it("memoryProviderSearch posts the query with the external flag", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
      ok: true,
      status: 200,
      json: async () => ({ success: true, native: { provider: "native", results: [], degraded: false, detail: null }, external: [], decisions: [] }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    await memoryProviderSearch({ query: "reporting currency", allowExternal: true, limit: 4 });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/memory-providers/search");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
    const body = JSON.parse(String(fetchMock.mock.calls[0]?.[1]?.body));
    expect(body.query).toBe("reporting currency");
    expect(body.allowExternal).toBe(true);
  });

  it("listChatSessions fetches the sessions route", async () => {
    const fetchMock = vi.fn(async (_url: string) => ({
      ok: true, status: 200, json: async () => ({ sessions: [{ id: "s1" }] }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    const sessions = await listChatSessions({ limit: 5 });
    expect(sessions).toHaveLength(1);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("/api/sessions?");
  });

  it("forkChatSession posts to the fork route", async () => {
    const fetchMock = vi.fn(async (_url: string, _init?: RequestInit) => ({
      ok: true, status: 200, json: async () => ({ session: { id: "s2" } }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    await forkChatSession("s1");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/sessions/s1/fork");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
  });

  it("listProfiles fetches the profiles route", async () => {
    const fetchMock = vi.fn(async (_url: string) => ({
      ok: true, status: 200, json: async () => ({ profiles: [{ id: "work" }] }),
    }));
    vi.stubGlobal("fetch", fetchMock as unknown as typeof fetch);
    const profiles = await listProfiles();
    expect(profiles[0].id).toBe("work");
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/profiles");
  });
});
