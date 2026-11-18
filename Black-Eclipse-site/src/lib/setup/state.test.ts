import { beforeEach, describe, expect, it, vi } from "vitest";

const setConfig = vi.fn();

vi.mock("@/lib/db", () => ({ prisma: {} }));
vi.mock("@/lib/settings", () => ({
  getConfig: async () => null,
  setConfig: (...args: unknown[]) => setConfig(...args),
  deleteConfig: async () => {},
  getLLMConfig: async () => ({ provider: "mock", model: "m", baseUrl: "http://localhost/v1", apiKey: "" }),
  LOCAL_KEY_SENTINEL: "local",
}));
vi.mock("@/lib/provider-keys", () => ({
  deleteProviderKey: async () => {},
  PROVIDER_KEYS: [],
}));
vi.mock("@/lib/legal/acceptance", () => ({
  recordRiskAcknowledgement: async () => ({ version: "2026-11-12", acceptedAt: "now" }),
  RISK_ACK_CONFIG_KEY: "risk_ack_v1",
}));
vi.mock("@/lib/legal/disclosure", () => ({ RISK_DISCLOSURE_VERSION: "2026-11-12" }));

const { completeOnboarding, describeSetupWriteError } = await import("./state");

const INPUT = {
  mode: "personal" as const,
  sources: { sec: true },
  acceptedRestrictedSources: [],
  riskAckVersion: "2026-11-12",
};

describe("describeSetupWriteError", () => {
  it("turns a busy database into an actionable sentence", () => {
    expect(describeSetupWriteError(new Error("SQLITE_BUSY: database is locked"))).toMatch(
      /close any other eclipse window/i,
    );
    expect(describeSetupWriteError(new Error("PrismaClientKnownRequestError P2010"))).toMatch(
      /database was busy/i,
    );
    // What better-sqlite3 → Prisma actually reports when the busy handler gives
    // up: "Invalid `prisma.systemConfig.upsert()` invocation: Operation has
    // timed out". Never show that to a user.
    expect(
      describeSetupWriteError(
        new Error("Invalid `prisma.systemConfig.upsert()` invocation:\n\nOperation has timed out"),
      ),
    ).toMatch(/database was busy/i);
  });

  it("names the data folder when it cannot be written", () => {
    expect(describeSetupWriteError(new Error("SQLITE_READONLY: attempt to write a readonly database"))).toMatch(
      /data folder/i,
    );
  });

  it("keeps an ordinary message intact and never returns an empty string", () => {
    expect(describeSetupWriteError(new Error("Unknown local provider preset"))).toBe(
      "Unknown local provider preset",
    );
    expect(describeSetupWriteError(null)).toBe("Could not save setup");
  });
});

describe("completeOnboarding write resilience", () => {
  beforeEach(() => {
    setConfig.mockReset();
  });

  it("retries an idempotent upsert when the database is momentarily busy", async () => {
    let calls = 0;
    setConfig.mockImplementation(async () => {
      calls += 1;
      if (calls <= 2) throw new Error("SQLITE_BUSY: database is locked");
    });

    await expect(completeOnboarding(INPUT)).resolves.toMatchObject({
      onboarding: { completed: true },
      prefs: { mode: "personal" },
    });
    // Two busy failures, then the write lands.
    expect(calls).toBeGreaterThanOrEqual(3);
  });

  it("does not retry a real validation failure", async () => {
    setConfig.mockRejectedValue(new Error("constraint failed"));
    await expect(completeOnboarding(INPUT)).rejects.toThrow("constraint failed");
    expect(setConfig).toHaveBeenCalledTimes(1);
  });
});
