// ─── SEC filing-LIST capability (Phase 16 remainder) ────────────────────────
// The submissions feed (`data.sec.gov/submissions/CIK##########.json`) is the
// SEC's own filing INDEX: form, filed date, report period, accession number and
// the primary document per filing — the LIST a bulk collection needs, distinct
// from `sec_filings` (normalized statement periods). Read-only, bounded,
// newest-first (the provider's order); nothing is guessed — a field the
// provider omits stays null.
//
// The CIK map (`company_tickers.json`) is the authority for this route: it IS
// the US issuer index, so no JDDS identity read is needed, and a ticker outside
// it is honestly `not_found`. Keyless; the declared User-Agent is the SEC
// fair-access requirement.

import { safeGet, type SafeGetResult } from "@/lib/connectors/security";
import { resolveSecCik, SEC_USER_AGENT } from "@/lib/fundamentals/providers/sec-edgar";
import { unavailableClass } from "./data-bridge-result";
import type { DataBridgeResult } from "./data-bridge-types";

// The SAME contact-bearing User-Agent the fundamentals adapter declares — one
// UA for every SEC route, not two that can drift.
const SUBMISSIONS_URL = (cik: number) =>
  `https://data.sec.gov/submissions/CIK${String(cik).padStart(10, "0")}.json`;
const FETCH_TIMEOUT_MS = 10_000;
const MAX_BYTES = 8 * 1024 * 1024;
// One call returns at most this many filings — the provider's own `recent`
// index holds ~1000 entries; a caller narrowing the window collects the rest.
const MAX_FILINGS = 1_000;
const FORM_RE = /^[A-Za-z0-9/-]{1,12}$/;
const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export interface FilingListDeps {
  /** Injectable for deterministic offline tests. */
  resolveCik?: (symbol: string) => Promise<number | null>;
  get?: typeof safeGet;
}

function column(columnValue: unknown, index: number): string | null {
  if (!Array.isArray(columnValue)) return null;
  const value = columnValue[index];
  return typeof value === "string" && value ? value : null;
}

export async function secFilingListCapability(
  params: Record<string, unknown>,
  deps?: FilingListDeps,
): Promise<DataBridgeResult> {
  const symbol = String(params.symbol ?? "").trim().toUpperCase();
  if (!symbol) return unavailableClass("invalid_request", "symbol is required");
  const market = String(params.market ?? "US").trim().toUpperCase();
  if (market !== "US") {
    return unavailableClass(
      "not_covered",
      `SEC EDGAR covers US issuers only; "${market}" is not supported by this route`,
    );
  }
  const form = String(params.form ?? "").trim();
  if (form && !FORM_RE.test(form)) {
    return unavailableClass("invalid_request", `"${form}" is not a plausible SEC form type`);
  }
  const dateFrom = String(params.date_from ?? "").trim();
  const dateTo = String(params.date_to ?? "").trim();
  for (const [label, value] of [["date_from", dateFrom], ["date_to", dateTo]] as const) {
    if (value && !DATE_RE.test(value)) {
      return unavailableClass("invalid_request", `${label} must be YYYY-MM-DD`);
    }
  }

  const resolveCik = deps?.resolveCik ?? resolveSecCik;
  let cik: number | null;
  try {
    cik = await resolveCik(symbol);
  } catch {
    return unavailableClass("source_failure", "the SEC ticker index could not be read");
  }
  if (!cik) {
    return unavailableClass("not_found", `${symbol} has no SEC CIK (EDGAR covers US-listed issuers)`);
  }

  const get = deps?.get ?? safeGet;
  let res: SafeGetResult;
  try {
    res = await get({
      url: SUBMISSIONS_URL(cik),
      headers: { "user-agent": SEC_USER_AGENT },
      timeoutMs: FETCH_TIMEOUT_MS,
      maxBytes: MAX_BYTES,
    });
  } catch (err) {
    return unavailableClass(
      "source_failure",
      `SEC submissions request failed: ${err instanceof Error ? err.message : String(err)}`,
    );
  }
  if (res.status < 200 || res.status >= 300) {
    return unavailableClass("source_failure", `SEC submissions HTTP ${res.status}`);
  }

  let payload: { entityName?: unknown; filings?: { recent?: unknown } };
  try {
    payload = JSON.parse(res.text) as typeof payload;
  } catch {
    return unavailableClass("source_failure", "the SEC submissions response was not JSON");
  }
  const recent = (payload.filings?.recent ?? {}) as Record<string, unknown>;
  const total = Array.isArray(recent.accessionNumber) ? recent.accessionNumber.length : 0;
  if (total === 0) {
    return unavailableClass("no_data", `SEC EDGAR returned no filings for ${symbol}`);
  }

  const filings: Array<Record<string, unknown>> = [];
  let matched = 0;
  for (let i = 0; i < total; i += 1) {
    const formType = column(recent.form, i);
    const filed = column(recent.filingDate, i);
    if (form && (formType ?? "").toUpperCase() !== form.toUpperCase()) continue;
    if (dateFrom && (!filed || filed < dateFrom)) continue;
    if (dateTo && (!filed || filed > dateTo)) continue;
    matched += 1;
    if (filings.length >= MAX_FILINGS) continue;
    const accessionNumber = column(recent.accessionNumber, i);
    const primaryDocument = column(recent.primaryDocument, i);
    filings.push({
      form: formType,
      filed,
      period: column(recent.reportDate, i),
      accession: accessionNumber,
      // The provider's primary document, addressed inside the accession fold —
      // a real URL or null, never a constructed guess.
      document:
        primaryDocument && accessionNumber
          ? `https://www.sec.gov/Archives/edgar/data/${cik}/${accessionNumber.replace(/-/g, "")}/${primaryDocument}`
          : null,
      description: column(recent.primaryDocDescription, i),
    });
  }

  const truncated = matched > filings.length;
  return {
    status: "OK",
    symbol,
    market: "US",
    assetClass: "equity",
    cik,
    entityName: typeof payload.entityName === "string" ? payload.entityName : null,
    provider: "sec-edgar",
    retrievedAt: new Date().toISOString(),
    matched,
    count: filings.length,
    truncated,
    ...(truncated
      ? {
          note:
            `this pull reached its ${MAX_FILINGS}-filing ceiling — ` +
            "narrow the window (form / date_from / date_to) to collect the rest",
        }
      : {}),
    filings,
  };
}
