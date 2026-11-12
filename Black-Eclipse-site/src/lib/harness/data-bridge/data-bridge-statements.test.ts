import { describe, expect, it } from "vitest";
import {
  STATEMENT_CACHE_VERSION,
  readCachedStatements,
  staleStatementsResult,
  statementPeriodAge,
} from "./data-bridge-statements";

const identity = { symbol: "AAPL", market: "US", currency: "USD", assetClass: "equity" };
const now = new Date();

function row(periods: unknown[], cacheVersion = STATEMENT_CACHE_VERSION, fetchedAt = now) {
  return {
    payload: JSON.stringify({ periods, primarySource: "legacy-cache", cacheVersion }),
    primarySource: "legacy-cache",
    fetchedAt,
  };
}

describe("statement period-age contract (D2)", () => {
  it("an FY2018 payload is STALE even when its fetch timestamp is fresh", () => {
    const read = readCachedStatements(
      row([{ endDate: "2018-09-29", fiscalYear: 2018 }]),
      identity,
      false,
    );
    expect(read.fresh).toBeUndefined();
    expect(read.stale?.periodEnd).toBe("2018-09-29");
    expect(read.stale?.periodAgeDays).toBeGreaterThan(548);
  });

  it("a recent annual period is served fresh", () => {
    const recent = new Date(Date.now() - 90 * 24 * 3600 * 1000)
      .toISOString()
      .slice(0, 10);
    const read = readCachedStatements(row([{ endDate: recent }]), identity, false);
    expect(read.fresh?.status).toBe("OK");
    expect(read.stale).toBeUndefined();
  });

  it("an old cache-key version is not re-served", () => {
    const recent = new Date().toISOString().slice(0, 10);
    const read = readCachedStatements(row([{ endDate: recent }], 1), identity, false);
    expect(read.fresh).toBeUndefined();
    expect(read.stale).toBeDefined();
  });

  it("the stale result is programmatically rejectable", () => {
    const read = readCachedStatements(
      row([{ endDate: "2018-09-29" }]),
      identity,
      false,
    )!;
    const result = staleStatementsResult(read.stale!);
    expect(result.stale).toBe(true);
    expect(result.qualityVerdict).toBe("STALE");
    expect(result.reasonCode).toBe("DATA_STALE");
    expect(result.periodEnd).toBe("2018-09-29");
  });

  it("quarterly periods use the 150-day tolerance", () => {
    const age = statementPeriodAge([
      { endDate: "2026-03-31", period: "Q1" },
      { endDate: "2025-12-31", period: "Q4" },
    ]);
    expect(age.maxAgeDays).toBe(150);
  });
});
