import { describe, it, expect, vi, beforeEach } from "vitest";

// Front-door contract for POST /api/provider-keys. It is the SECRET VAULT front
// door: it must be operator-gated, reject an unknown key, and never echo a value.

const saveProviderKey = vi.fn();
const deleteProviderKey = vi.fn();

vi.mock("@/lib/provider-keys", () => ({
  providerKeyDef: (envVar: string) => (envVar === "OPENAI_API_KEY" ? { envVar, label: "OpenAI", publicValue: false } : undefined),
  listProviderKeyStatus: vi.fn(async () => []),
  saveProviderKey: (...a: unknown[]) => saveProviderKey(...a),
  deleteProviderKey: (...a: unknown[]) => deleteProviderKey(...a),
  resolveProviderKey: vi.fn(async () => null),
  applyStoredKeysToEnv: vi.fn(async () => undefined),
}));

import { POST } from "@/app/api/provider-keys/route";

function req(body: unknown, origin = "http://localhost:3000"): Request {
  return new Request("http://localhost:3000/api/provider-keys", {
    method: "POST",
    headers: { "content-type": "application/json", ...(origin ? { origin } : {}) },
    body: JSON.stringify(body),
  });
}

describe("POST /api/provider-keys", () => {
  beforeEach(() => saveProviderKey.mockReset());

  it("refuses a cross-origin save before touching the vault", async () => {
    const res = await POST(req({ envVar: "OPENAI_API_KEY", value: "sk-abcdefgh" }, "http://evil.example"));
    expect(res.status).toBe(403);
    expect(saveProviderKey).not.toHaveBeenCalled();
  });

  it("rejects an unknown provider key with 400", async () => {
    const res = await POST(req({ envVar: "NOPE", value: "sk-abcdefgh" }));
    expect(res.status).toBe(400);
  });

  it("rejects a too-short secret with 400", async () => {
    const res = await POST(req({ envVar: "OPENAI_API_KEY", value: "abc" }));
    expect(res.status).toBe(400);
  });

  it("saves a valid key and never echoes the value", async () => {
    saveProviderKey.mockResolvedValueOnce(undefined);
    const res = await POST(req({ envVar: "OPENAI_API_KEY", value: "sk-abcdefgh" }));
    expect(res.status).toBe(200);
    expect(await res.text()).not.toContain("sk-abcdefgh");
    expect(saveProviderKey).toHaveBeenCalledWith("OPENAI_API_KEY", "sk-abcdefgh");
  });
});
