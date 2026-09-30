import { describe, it, expect, vi, beforeEach } from "vitest";

// Front-door contract for POST /api/settings. It persists LLM config, news feeds
// and preferences, so it must be operator-gated, validate feed URLs against the
// SSRF guard, and never echo the stored API key.

const setLLMConfig = vi.fn();
const setNewsFeeds = vi.fn();
const setPreferences = vi.fn();

vi.mock("@/lib/settings", () => ({
  getLLMConfig: vi.fn(async () => ({ provider: "openai", baseUrl: "https://api.openai.com/v1", model: "gpt", apiKey: "secret-key-value" })),
  setLLMConfig: (...a: unknown[]) => setLLMConfig(...a),
  getNewsFeeds: vi.fn(async () => []),
  setNewsFeeds: (...a: unknown[]) => setNewsFeeds(...a),
  getPreferences: vi.fn(async () => ({})),
  setPreferences: (...a: unknown[]) => setPreferences(...a),
  getIntegrationsStatus: vi.fn(async () => ({})),
}));

import { GET, POST } from "@/app/api/settings/route";

function req(body: unknown, origin = "http://localhost:3000"): Request {
  return new Request("http://localhost:3000/api/settings", {
    method: "POST",
    headers: { "content-type": "application/json", ...(origin ? { origin } : {}) },
    body: JSON.stringify(body),
  });
}

describe("GET /api/settings", () => {
  it("never returns the stored API key value", async () => {
    const res = await GET();
    const text = await res.text();
    expect(text).not.toContain("secret-key-value");
    expect(JSON.parse(text).llm.hasApiKey).toBe(true);
  });
});

describe("POST /api/settings", () => {
  beforeEach(() => { setLLMConfig.mockReset(); setNewsFeeds.mockReset(); setPreferences.mockReset(); });

  it("refuses a cross-origin mutation before writing", async () => {
    const res = await POST(req({ preferences: { theme: "dark" } }, "http://evil.example"));
    expect(res.status).toBe(403);
    expect(setPreferences).not.toHaveBeenCalled();
  });

  it("rejects an unsafe feed URL with 400", async () => {
    const res = await POST(req({ newsFeeds: [{ url: "http://127.0.0.1/feed" }] }));
    expect(res.status).toBe(400);
    expect(setNewsFeeds).not.toHaveBeenCalled();
  });

  it("saves preferences and masks the key in the response", async () => {
    setPreferences.mockResolvedValueOnce(undefined);
    const res = await POST(req({ preferences: { theme: "dark" } }));
    expect(res.status).toBe(200);
    const text = await res.text();
    expect(text).not.toContain("secret-key-value");
    expect(setPreferences).toHaveBeenCalled();
  });
});
