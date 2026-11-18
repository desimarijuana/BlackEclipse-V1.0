import { beforeEach, describe, expect, it, vi } from "vitest";

const saveProviderKey = vi.fn();
const setLLMConfig = vi.fn();
const completeOnboarding = vi.fn();
const invalidateSettingsCache = vi.fn();
const invalidateSourcePreferenceCache = vi.fn();

vi.mock("@/lib/api-guard", () => ({ guardMutation: () => null }));
vi.mock("@/lib/agent/presets", () => ({
  getLLMPreset: (id: string) => ({
    id,
    baseUrl: "https://api.openai.com/v1",
    model: "gpt-4o-mini",
    envVar: "OPENAI_API_KEY",
  }),
}));
vi.mock("@/lib/provider-keys", () => ({
  saveProviderKey: (...args: unknown[]) => saveProviderKey(...args),
  listProviderKeyStatus: async () => [],
}));
vi.mock("@/lib/settings", () => ({
  getConfig: async () => null,
  setLLMConfig: (...args: unknown[]) => setLLMConfig(...args),
}));
vi.mock("@/lib/settings-route-cache", () => ({
  invalidateSettingsCache: () => invalidateSettingsCache(),
}));
vi.mock("@/lib/data-source-preferences", () => ({
  invalidateSourcePreferenceCache: () => invalidateSourcePreferenceCache(),
}));
vi.mock("@/lib/setup/state", () => ({
  completeOnboarding: (...args: unknown[]) => completeOnboarding(...args),
  getAiStatus: async () => ({ provider: "mock", model: "m", baseUrl: "", hasKey: false, configured: false }),
  readOnboardingState: async () => null,
  readSourcePreferences: async () => null,
  markMigrated: async () => {},
  setupSourcePreferences: async () => ({}),
}));
vi.mock("@/lib/setup/existing-install", () => ({ probeInstall: async () => ({ isNew: true, reasons: [] }) }));
vi.mock("@/lib/legal/acceptance", () => ({
  riskAcknowledgementStatus: async () => ({ requiredVersion: "2026-11-12", accepted: false }),
}));
vi.mock("@/lib/legal/disclosure", () => ({ RISK_DISCLOSURE_VERSION: "2026-11-12" }));
vi.mock("@/lib/auth/config", () => ({ authRequired: () => false }));

const { POST } = await import("./route");

const ACK = { version: "2026-11-12" };

function request(body: Record<string, unknown>): Request {
  return new Request("http://127.0.0.1:3100/api/setup", {
    method: "POST",
    headers: { "content-type": "application/json", host: "127.0.0.1:3100" },
    body: JSON.stringify(body),
  });
}

async function post(body: Record<string, unknown>) {
  const res = await POST(request(body));
  return { status: res.status, body: (await res.json()) as Record<string, unknown> };
}

describe("POST /api/setup", () => {
  beforeEach(() => {
    saveProviderKey.mockReset();
    setLLMConfig.mockReset();
    completeOnboarding.mockReset();
    invalidateSettingsCache.mockReset();
    invalidateSourcePreferenceCache.mockReset();
    completeOnboarding.mockResolvedValue({
      prefs: { version: 1, mode: "personal", sources: {}, acceptedRestrictedSources: [], updatedAt: "" },
      onboarding: { completed: true },
    });
  });

  it("records the setup and reports an AI failure as a warning, never blocking it", async () => {
    // The provider vault write fails (an unwritable key file, privacy mode, …).
    // Finishing setup must still be possible: the wizard would otherwise be
    // stuck forever, with nothing written.
    saveProviderKey.mockRejectedValue(new Error("Could not read local key file"));
    const res = await post({
      mode: "personal",
      sources: { sec: true },
      ai: { kind: "key", presetId: "openai", apiKey: "sk-test-0123456789", model: "gpt-4o-mini" },
      riskAck: ACK,
    });

    expect(res.status).toBe(200);
    expect(res.body.completed).toBe(true);
    expect(res.body.warning).toMatch(/local key file/i);
    expect(completeOnboarding).toHaveBeenCalledTimes(1);
    expect(invalidateSettingsCache).toHaveBeenCalled();
  });

  it("does not require an AI choice at all", async () => {
    const res = await post({ mode: "personal", sources: { sec: true }, ai: { kind: "skip" }, riskAck: ACK });
    expect(res.status).toBe(200);
    expect(res.body.warning).toBeUndefined();
    expect(setLLMConfig).toHaveBeenCalledWith({ provider: "mock", apiKey: "" });
    expect(completeOnboarding).toHaveBeenCalledTimes(1);
  });

  it("still refuses a stale risk acknowledgement before writing anything", async () => {
    const res = await post({
      mode: "personal",
      sources: { sec: true },
      ai: { kind: "skip" },
      riskAck: { version: "2020-01-01" },
    });
    expect(res.status).toBe(400);
    expect(res.body.error).toMatch(/risk notice/i);
    expect(completeOnboarding).not.toHaveBeenCalled();
    expect(setLLMConfig).not.toHaveBeenCalled();
  });

  it("still refuses an advanced source without its acknowledgement", async () => {
    const res = await post({
      mode: "personal",
      sources: { tradingview: true },
      ai: { kind: "skip" },
      riskAck: ACK,
    });
    expect(res.status).toBe(400);
    expect(completeOnboarding).not.toHaveBeenCalled();
  });
});
