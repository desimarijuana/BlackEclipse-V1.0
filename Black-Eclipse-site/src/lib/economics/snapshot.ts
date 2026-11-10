// Global Macro Snapshot — key central-bank rates and key US prints, each with
// its "as of" vintage. Values come from free public endpoints (no key needed):
//   • Policy rates + yields from FRED CSV mirror (fredgraph.csv — public).
//   • CPI/GDP/unemployment from FRED public CSV too (CPIAUCSL, GDPC1, UNRATE).
// If a fetch fails, the entry is marked unavailable — never fabricated.

import { isHtmlPayload } from "./fetch";
import { enrichMetrics, type WebMetricSpec } from "./enrichment";
import { readJsonConfig } from "./state-cache";

export type SnapshotState = "LIVE" | "WEB" | "CACHED" | "UNAVAILABLE";

export interface SnapshotMetric {
  id: string;
  label: string;
  region: string;         // grouping: 'North America' | 'Europe' | 'Asia-Pacific' | ...
  kind: "rate" | "print" | "yield";
  value: number | null;
  asOf: string | null;    // vintage of the value
  unit: string;           // '%' | '' | 'index'
  country: string;
  /** Exact provider identity of the value actually fetched (e.g. "FRED · DFF"). */
  source: string;
  /** LIVE = structured provider; WEB = official page found via search; CACHED = last known good. */
  state: SnapshotState;
  /** Source page for WEB values. */
  url: string | null;
  /** When a CACHED value was last confirmed by a provider. */
  cachedAt?: string | null;
}

interface FREDMeta {
  fredId: string;
  transform?: "level" | "yoy"; // yoy → annual percent change over the level
}

const RATE_SOURCES: { id: string; label: string; region: string; country: string; fred: FREDMeta }[] = [
  { id: "fed-funds", label: "Fed Funds Rate", region: "North America", country: "US", fred: { fredId: "DFF" } },
  { id: "boe-rate", label: "BoE Bank Rate", region: "Europe", country: "UK", fred: { fredId: "IR3TIB01GBM156N" } },
  { id: "ecb-rate", label: "ECB Deposit Rate", region: "Europe", country: "EU", fred: { fredId: "ECBMRRFR" } },
  { id: "boj-rate", label: "BoJ Policy Rate", region: "Asia-Pacific", country: "JP", fred: { fredId: "IRSTCI01JPM156N" } },
  { id: "rba-rate", label: "RBA Cash Rate", region: "Asia-Pacific", country: "AU", fred: { fredId: "IRSTCI01AUM156N" } },
  { id: "rbnz-rate", label: "RBNZ OCR", region: "Asia-Pacific", country: "NZ", fred: { fredId: "IRSTCI01NZM156N" } },
  { id: "boc-rate", label: "BoC Overnight Rate", region: "North America", country: "CA", fred: { fredId: "IRSTCI01CAM156N" } },
  { id: "snb-rate", label: "SNB Policy Rate", region: "Europe", country: "CH", fred: { fredId: "IRSTCI01CHM156N" } },
  { id: "rbi-rate", label: "RBI Repo Rate", region: "Asia-Pacific", country: "IN", fred: { fredId: "IRSTCI01INM156N" } },
  { id: "sbp-rate", label: "SBP Policy Rate", region: "Asia-Pacific", country: "PK", fred: { fredId: "IRSTCI01PKM156N" } },
  { id: "pboc-rate", label: "PBOC Loan Prime Rate", region: "Asia-Pacific", country: "CN", fred: { fredId: "IRSTCI01CNM156N" } },
];

const PRINT_SOURCES: { id: string; label: string; region: string; country: string; kind: "print" | "yield"; unit: string; fred: FREDMeta }[] = [
  // US
  { id: "us-cpi", label: "US CPI (YoY)", region: "North America", country: "US", kind: "print", unit: "%", fred: { fredId: "CPIAUCSL", transform: "yoy" } as FREDMeta },
  { id: "us-gdp", label: "US Real GDP (YoY)", region: "North America", country: "US", kind: "print", unit: "%", fred: { fredId: "GDPC1", transform: "yoy" } as FREDMeta },
  { id: "us-nfp", label: "US Nonfarm Payrolls", region: "North America", country: "US", kind: "print", unit: "k", fred: { fredId: "PAYEMS" } },
  { id: "us-unemp", label: "US Unemployment", region: "North America", country: "US", kind: "print", unit: "%", fred: { fredId: "UNRATE" } },
  { id: "us-10y", label: "US 10Y Treasury", region: "North America", country: "US", kind: "yield", unit: "%", fred: { fredId: "DGS10" } },
  // India
  { id: "in-cpi", label: "India CPI (YoY)", region: "Asia-Pacific", country: "IN", kind: "print", unit: "%", fred: { fredId: "CPALTT01INM659N" } },
  { id: "in-gdp", label: "India Real GDP (YoY)", region: "Asia-Pacific", country: "IN", kind: "print", unit: "%", fred: { fredId: "NGDPRSAXDCCINQ", transform: "yoy" } as FREDMeta },
  { id: "in-unemp", label: "India Unemployment", region: "Asia-Pacific", country: "IN", kind: "print", unit: "%", fred: { fredId: "LRUN64TTINQ156S" } },
  // Pakistan
  { id: "pk-cpi", label: "Pakistan CPI (YoY)", region: "Asia-Pacific", country: "PK", kind: "print", unit: "%", fred: { fredId: "CPALTT01PKM659N" } },
  { id: "pk-gdp", label: "Pakistan Real GDP (YoY)", region: "Asia-Pacific", country: "PK", kind: "print", unit: "%", fred: { fredId: "NGDPRSAXDCPKQ", transform: "yoy" } as FREDMeta },
  { id: "pk-unemp", label: "Pakistan Unemployment", region: "Asia-Pacific", country: "PK", kind: "print", unit: "%", fred: { fredId: "LRUN64TTPKQ156S" } },
  // China
  { id: "cn-cpi", label: "China CPI (YoY)", region: "Asia-Pacific", country: "CN", kind: "print", unit: "%", fred: { fredId: "CPALTT01CNM659N" } },
  { id: "cn-gdp", label: "China Real GDP (YoY)", region: "Asia-Pacific", country: "CN", kind: "print", unit: "%", fred: { fredId: "NGDPRSAXDCCNQ", transform: "yoy" } as FREDMeta },
  // UK
  { id: "gb-cpi", label: "UK CPI (YoY)", region: "Europe", country: "GB", kind: "print", unit: "%", fred: { fredId: "CPALTT01GBM659N" } },
  { id: "gb-unemp", label: "UK Unemployment", region: "Europe", country: "GB", kind: "print", unit: "%", fred: { fredId: "LRUN64TTGBQ156S" } },
  // Euro area
  { id: "eu-cpi", label: "Euro Area HICP (YoY)", region: "Europe", country: "EU", kind: "print", unit: "%", fred: { fredId: "CP0000EZ19M086NEST", transform: "yoy" } as FREDMeta },
  { id: "eu-unemp", label: "Euro Area Unemployment", region: "Europe", country: "EU", kind: "print", unit: "%", fred: { fredId: "LRHUTTTTEZM156S" } },
  // Japan
  { id: "jp-cpi", label: "Japan CPI (YoY)", region: "Asia-Pacific", country: "JP", kind: "print", unit: "%", fred: { fredId: "CPALTT01JPM659N" } },
  { id: "jp-unemp", label: "Japan Unemployment", region: "Asia-Pacific", country: "JP", kind: "print", unit: "%", fred: { fredId: "LRUN64TTJPM156S" } },
  // Canada
  { id: "ca-cpi", label: "Canada CPI (YoY)", region: "North America", country: "CA", kind: "print", unit: "%", fred: { fredId: "CPALTT01CAM659N" } },
  { id: "ca-unemp", label: "Canada Unemployment", region: "North America", country: "CA", kind: "print", unit: "%", fred: { fredId: "LRUN64TTCAQ156S" } },
];

async function fredCSV(id: string): Promise<{ date: string; value: number }[]> {
  const res = await fetch(`https://fred.stlouisfed.org/graph/fredgraph.csv?id=${id}`, { signal: AbortSignal.timeout(15_000) });
  if (!res.ok) throw new Error(`HTTP ${res.status} from FRED CSV (${id})`);
  const csv = await res.text();
  // A provider under maintenance answers HTTP 200 with a maintenance PAGE; it
  // is a transport failure, never data.
  if (isHtmlPayload(csv)) {
    throw new Error(`FRED is serving a web page instead of CSV (${id}) - the series is unavailable right now`);
  }
  const lines = csv.trim().split("\n");
  const out: { date: string; value: number }[] = [];
  for (const line of lines.slice(1)) {
    const [date, rawVal] = line.split(",");
    const v = Number((rawVal ?? "").trim());
    if (date && Number.isFinite(v)) out.push({ date: date.trim(), value: v });
  }
  return out;
}

// yoy → percent change vs the value 12 months/periods earlier.
function yoy(points: { date: string; value: number }[]): { date: string; value: number }[] {
  return points.slice(12).map((p, i) => {
    const prev = points[i].value;
    return { date: p.date, value: prev !== 0 ? ((p.value - prev) / prev) * 100 : NaN };
  }).filter((p) => Number.isFinite(p.value));
}

// Conservative, labelled patterns for the web fallback. A metric without a spec
// is never web-enriched. Each pattern anchors a label to a number so a headline
// or unrelated figure cannot be mistaken for the release.
function percentSpec(
  query: string,
  label: string,
  min = -30,
  max = 50,
): WebMetricSpec {
  return {
    query,
    pattern: new RegExp(`(?:${label})[^.]{0,180}?(-?\\d{1,3}\\.\\d{1,2})\\s*(?:percent|%)`, "i"),
    min,
    max,
  };
}

/** A level reported in thousands, e.g. total nonfarm payroll employment. */
function thousandsSpec(
  query: string,
  label: string,
  min: number,
  max: number,
): WebMetricSpec {
  return {
    query,
    pattern: new RegExp(
      `(?:${label})[^.]{0,180}?(\\d{1,3}(?:,\\d{3})*)\\s*(?:thousand|,000)`,
      "i",
    ),
    min,
    max,
  };
}

const WEB_SPECS: Record<string, WebMetricSpec> = {
  // ── Central-bank policy rates ──
  "fed-funds": percentSpec("federal funds target range latest site:federalreserve.gov", "federal funds|target range", 0, 25),
  "boe-rate": percentSpec("Bank of England Bank Rate latest site:bankofengland.co.uk", "bank rate", 0, 25),
  "ecb-rate": percentSpec("ECB deposit facility rate latest site:ecb.europa.eu", "deposit facility rate|deposit rate", -1, 25),
  "boj-rate": percentSpec("Bank of Japan policy rate latest site:boj.or.jp", "policy rate|policy interest rate", -2, 25),
  "rba-rate": percentSpec("Reserve Bank of Australia cash rate latest site:rba.gov.au", "cash rate", 0, 25),
  "rbnz-rate": percentSpec("Reserve Bank of New Zealand official cash rate latest site:rbnz.govt.nz", "official cash rate", 0, 25),
  "boc-rate": percentSpec("Bank of Canada overnight rate latest site:bankofcanada.ca", "overnight rate|policy interest rate", 0, 25),
  "snb-rate": percentSpec("Swiss National Bank policy rate latest site:snb.ch", "policy rate", -2, 25),
  "rbi-rate": percentSpec("RBI repo rate latest site:rbi.org.in", "repo rate", 0, 25),
  "sbp-rate": percentSpec("State Bank of Pakistan policy rate latest site:sbp.org.pk", "policy rate", 0, 30),
  "pboc-rate": percentSpec("China loan prime rate latest site:pbc.gov.cn", "loan prime rate|LPR", 0, 25),

  // ── CPI / inflation (YoY) ──
  "us-cpi": percentSpec("BLS consumer price index latest 12-month percent change site:bls.gov", "consumer price index|CPI", -5, 30),
  "us-nfp": thousandsSpec("BLS total nonfarm payroll employment latest site:bls.gov", "total nonfarm payroll employment|nonfarm payroll employment", 100000, 250000),
  "in-cpi": percentSpec("India CPI inflation latest site:mospi.gov.in", "consumer price index|CPI|inflation", -5, 40),
  "pk-cpi": percentSpec("Pakistan CPI inflation latest site:pbs.gov.pk", "consumer price index|CPI|inflation", -5, 40),
  "cn-cpi": percentSpec("China CPI latest site:stats.gov.cn", "consumer price index|CPI", -5, 40),
  "gb-cpi": percentSpec("UK CPI latest site:ons.gov.uk", "consumer price index|CPI", -5, 30),
  "eu-cpi": percentSpec("euro area HICP latest site:ec.europa.eu/eurostat", "harmonised index of consumer prices|HICP|inflation", -5, 30),
  "jp-cpi": percentSpec("Japan CPI latest site:stat.go.jp", "consumer price index|CPI", -5, 30),
  "ca-cpi": percentSpec("Canada CPI latest site:statcan.gc.ca", "consumer price index|CPI", -5, 30),

  // ── Unemployment ──
  "us-unemp": percentSpec("BLS unemployment rate latest site:bls.gov", "unemployment rate", 0, 30),
  "in-unemp": percentSpec("India unemployment rate latest site:mospi.gov.in", "unemployment rate", 0, 40),
  "pk-unemp": percentSpec("Pakistan unemployment rate latest site:pbs.gov.pk", "unemployment rate", 0, 40),
  "gb-unemp": percentSpec("UK unemployment rate latest site:ons.gov.uk", "unemployment rate", 0, 30),
  "eu-unemp": percentSpec("euro area unemployment rate latest site:ec.europa.eu/eurostat", "unemployment rate", 0, 30),
  "jp-unemp": percentSpec("Japan unemployment rate latest site:stat.go.jp", "unemployment rate", 0, 30),
  "ca-unemp": percentSpec("Canada unemployment rate latest site:statcan.gc.ca", "unemployment rate", 0, 30),

  // ── GDP growth (YoY) ──
  "us-gdp": percentSpec("US real GDP growth latest site:bea.gov", "gross domestic product|GDP", -30, 50),
  "in-gdp": percentSpec("India GDP growth latest site:mospi.gov.in", "gross domestic product|GDP", -30, 50),
  "pk-gdp": percentSpec("Pakistan GDP growth latest site:pbs.gov.pk", "gross domestic product|GDP", -30, 50),
  "cn-gdp": percentSpec("China GDP growth latest site:stats.gov.cn", "gross domestic product|GDP", -30, 50),

  // ── Yields ──
  "us-10y": percentSpec("10-year treasury yield latest site:treasury.gov", "10[- ]year", 0, 25),
};

export async function buildSnapshot(
  options: { webFallback?: boolean } = {},
): Promise<{ metrics: SnapshotMetric[]; builtAt: string }> {
  // Operators can correct a discontinued/renamed FRED id without a code change:
  // SystemConfig key `econ:fred-series-overrides` = { "<metric id>": "<FRED id>" }.
  const overrides =
    (await readJsonConfig<Record<string, string>>("econ:fred-series-overrides")) ?? {};

  const specs: { id: string; label: string; region: string; country: string; kind: SnapshotMetric["kind"]; unit: string; fred: FREDMeta }[] = [
    ...RATE_SOURCES.map((r) => ({ id: r.id, label: r.label, region: r.region, country: r.country, kind: "rate" as const, unit: "%", fred: r.fred })),
    ...PRINT_SOURCES.map((p) => ({ id: p.id, label: p.label, region: p.region, country: p.country, kind: p.kind, unit: p.unit, fred: p.fred })),
  ].map((spec) => ({
    ...spec,
    fred: { ...spec.fred, fredId: overrides[spec.id]?.trim() || spec.fred.fredId },
  }));

  const metrics = await Promise.all(
    specs.map(async (s): Promise<SnapshotMetric> => {
      try {
        let points = await fredCSV(s.fred.fredId);
        if (s.fred.transform === "yoy") points = yoy(points);
        if (points.length === 0) throw new Error("no data");
        const last = points[points.length - 1];
        return { id: s.id, label: s.label, region: s.region, kind: s.kind, country: s.country, unit: s.unit, value: last.value, asOf: last.date, source: `FRED · ${s.fred.fredId}`, state: "LIVE", url: null };
      } catch (err) {
        console.error(`[economics/snapshot] ${s.id} failed:`, err instanceof Error ? err.message : err);
        return { id: s.id, label: s.label, region: s.region, kind: s.kind, country: s.country, unit: s.unit, value: null, asOf: null, source: `FRED · ${s.fred.fredId}`, state: "UNAVAILABLE", url: null };
      }
    })
  );

  // Fill gaps from official pages via search. This never touches a LIVE value.
  if (options.webFallback !== false && process.env.ECON_WEB_FALLBACK !== "0") {
    try {
      const missing = metrics.filter((m) => m.value === null);
      const enriched = await enrichMetrics(missing, WEB_SPECS);
      for (const metric of metrics) {
        const hit = enriched[metric.id];
        if (!hit || metric.value !== null) continue;
        metric.value = hit.value;
        metric.asOf = hit.asOf;
        metric.source = `WEB · ${hit.provider}`;
        metric.state = "WEB";
        metric.url = hit.url;
      }
    } catch (err) {
      console.error("[economics/snapshot] web fallback failed:", err instanceof Error ? err.message : err);
    }
  }

  return { metrics, builtAt: new Date().toISOString() };
}