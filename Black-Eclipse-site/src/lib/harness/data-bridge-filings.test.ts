import { describe, it, expect, vi, beforeEach } from "vitest";

// Phase 16 remainder: the SEC filing-LIST capability (`sec_filing_list`), wired
// through the REAL dispatcher (`fetchCapability`). The SEC adapter, the CIK map
// and the outbound transport are mocked, so the tests assert the bridge's own
// mapping, filtering and failure classes offline.

const resolveSecCik = vi.fn();
const safeGet = vi.fn();

vi.mock("@/lib/db", () => ({ prisma: { sourceHealth: { upsert: vi.fn() } } }));
vi.mock("@/lib/fundamentals/providers/sec-edgar", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/fundamentals/providers/sec-edgar")>();
  return {
    ...actual,
    fetchSecCompanyFacts: vi.fn(),
    resolveSecCik: (...a: unknown[]) => resolveSecCik(...a),
  };
});
vi.mock("@/lib/connectors/security", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/connectors/security")>();
  return { ...actual, safeGet: (...a: unknown[]) => safeGet(...a) };
});

import { fetchCapability } from "./data-bridge";

const CIK = 320193;

function submissionsPayload(filings: Array<Record<string, unknown>>): string {
  const columns: Record<string, string[]> = {
    accessionNumber: [],
    filingDate: [],
    reportDate: [],
    form: [],
    primaryDocument: [],
    primaryDocDescription: [],
  };
  for (const f of filings) {
    columns.accessionNumber.push(String(f.accession ?? ""));
    columns.filingDate.push(String(f.filed ?? ""));
    columns.reportDate.push(String(f.period ?? ""));
    columns.form.push(String(f.form ?? ""));
    columns.primaryDocument.push(String(f.document ?? ""));
    columns.primaryDocDescription.push(String(f.description ?? ""));
  }
  return JSON.stringify({ cik: CIK, entityName: "Apple Inc.", filings: { recent: columns } });
}

function ok(text: string) {
  return { status: 200, contentType: "application/json", url: "https://data.sec.gov/x", text, bytes: text.length };
}

beforeEach(() => {
  resolveSecCik.mockReset();
  safeGet.mockReset();
  resolveSecCik.mockResolvedValue(CIK);
});

describe("fetchCapability — sec_filing_list (Phase 16)", () => {
  it("returns the filing list with real document URLs and nulls for omitted fields", async () => {
    safeGet.mockResolvedValue(
      ok(
        submissionsPayload([
          {
            form: "10-K",
            filed: "2024-11-01",
            period: "2024-09-28",
            accession: "0000320193-24-000123",
            document: "aapl-20240928.htm",
            description: "Annual report",
          },
          { form: "8-K", filed: "2024-08-01", accession: "0000320193-24-000100" },
        ]),
      ),
    );

    const result = await fetchCapability("sec_filing_list", { symbol: "aapl" });
    expect(result.status).toBe("OK");
    expect(result.cik).toBe(CIK);
    expect(result.entityName).toBe("Apple Inc.");
    expect(result.count).toBe(2);
    expect(result.truncated).toBe(false);

    const filings = result.filings as Array<Record<string, unknown>>;
    expect(filings[0]).toMatchObject({
      form: "10-K",
      filed: "2024-11-01",
      period: "2024-09-28",
      description: "Annual report",
    });
    expect(filings[0].document).toBe(
      `https://www.sec.gov/Archives/edgar/data/${CIK}/000032019324000123/aapl-20240928.htm`,
    );
    // An omitted primary document is null — never a constructed guess.
    expect(filings[1].document).toBeNull();
    expect(filings[1].period).toBeNull();

    // The CIK comes from the map, and the request carries the declared UA.
    expect(resolveSecCik).toHaveBeenCalledWith("AAPL");
    const call = safeGet.mock.calls[0][0] as { headers: Record<string, string> };
    expect(call.headers["user-agent"]).toContain("BlackEclipse");
  });

  it("filters by form and date window without inventing rows", async () => {
    safeGet.mockResolvedValue(
      ok(
        submissionsPayload([
          { form: "10-K", filed: "2024-11-01", accession: "a1" },
          { form: "10-Q", filed: "2024-08-01", accession: "a2" },
          { form: "10-K", filed: "2022-10-28", accession: "a3" },
        ]),
      ),
    );
    const result = await fetchCapability("sec_filing_list", {
      symbol: "AAPL",
      form: "10-K",
      date_from: "2024-01-01",
      date_to: "2024-12-31",
    });
    expect(result.matched).toBe(1);
    expect((result.filings as unknown[]).length).toBe(1);
  });

  it("distinguishes an unknown ticker (not_found) from an unreadable index (source_failure)", async () => {
    resolveSecCik.mockResolvedValue(null);
    const missing = await fetchCapability("sec_filing_list", { symbol: "ZZZZ" });
    expect(missing.failureClass).toBe("not_found");

    resolveSecCik.mockRejectedValue(new Error("index down"));
    const down = await fetchCapability("sec_filing_list", { symbol: "AAPL" });
    expect(down.failureClass).toBe("source_failure");
    expect(safeGet).not.toHaveBeenCalled();
  });

  it("refuses a non-US market and malformed parameters before any fetch", async () => {
    const jp = await fetchCapability("sec_filing_list", { symbol: "NVDA", market: "JP" });
    expect(jp.failureClass).toBe("not_covered");

    const badForm = await fetchCapability("sec_filing_list", { symbol: "NVDA", form: "10 K!" });
    expect(badForm.failureClass).toBe("invalid_request");

    const badDate = await fetchCapability("sec_filing_list", { symbol: "NVDA", date_from: "01/2024" });
    expect(badDate.failureClass).toBe("invalid_request");

    expect(safeGet).not.toHaveBeenCalled();
  });

  it("reports the per-call ceiling when more filings match than fit", async () => {
    const many = Array.from({ length: 1_200 }, (_, i) => ({
      form: "8-K",
      filed: "2024-01-01",
      accession: `a${i}`,
    }));
    safeGet.mockResolvedValue(ok(submissionsPayload(many)));

    const result = await fetchCapability("sec_filing_list", { symbol: "AAPL" });
    expect(result.count).toBe(1000);
    expect(result.matched).toBe(1200);
    expect(result.truncated).toBe(true);
    expect(String(result.note)).toContain("narrow the window");
  });

  it("a provider HTTP failure is source_failure, never an empty list", async () => {
    safeGet.mockResolvedValue({ status: 503, contentType: null, url: "https://data.sec.gov/x", text: "", bytes: 0 });
    const result = await fetchCapability("sec_filing_list", { symbol: "AAPL" });
    expect(result.failureClass).toBe("source_failure");
    expect(result.status).toBe("UNAVAILABLE");
  });
});
