import { beforeEach, describe, expect, it, vi } from "vitest";

const findUnique = vi.fn();
const probeInstall = vi.fn();

vi.mock("@/lib/db", () => ({
  prisma: { systemConfig: { findUnique: (...args: unknown[]) => findUnique(...args) } },
}));

vi.mock("./existing-install", () => ({
  probeInstall: (...args: unknown[]) => probeInstall(...args),
}));

const { onboardingGateState } = await import("./gate");

describe("onboardingGateState", () => {
  beforeEach(() => {
    findUnique.mockReset();
    probeInstall.mockReset();
  });

  it("reports an unfinished install as incomplete", async () => {
    findUnique.mockResolvedValue({ value: JSON.stringify({ completed: false, mode: "personal" }) });
    await expect(onboardingGateState()).resolves.toBe("incomplete");
  });

  it("reports a recorded install as complete without probing", async () => {
    findUnique.mockResolvedValue({ value: JSON.stringify({ completed: true }) });
    await expect(onboardingGateState()).resolves.toBe("complete");
    expect(probeInstall).not.toHaveBeenCalled();
  });

  it("never re-shows the wizard for a corrupt flag", async () => {
    findUnique.mockResolvedValue({ value: "{not json" });
    await expect(onboardingGateState()).resolves.toBe("complete");
  });

  it("uses the existing-install probe when no flag is stored", async () => {
    findUnique.mockResolvedValue(null);
    probeInstall.mockResolvedValue({ isNew: true, reasons: [] });
    await expect(onboardingGateState()).resolves.toBe("incomplete");

    probeInstall.mockResolvedValue({ isNew: false, reasons: ["system config: llm_config"] });
    await expect(onboardingGateState()).resolves.toBe("complete");
  });

  it("renders the app when the read fails (never block on an error)", async () => {
    findUnique.mockRejectedValue(new Error("no such table: SystemConfig"));
    await expect(onboardingGateState()).resolves.toBe("unknown");
  });
});
