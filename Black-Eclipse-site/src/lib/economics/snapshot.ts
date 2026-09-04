// Global Macro Snapshot — key central-bank rates and key US prints, each with
// its "as of" vintage. Values come from free public endpoints (no key needed):
//   • Policy rates + yields from FRED CSV mirror (fredgraph.csv — public).
//   • CPI/GDP/unemployment from FRED public CSV too (CPIAUCSL, GDPC1, UNRATE).
// If a fetch fails, the entry is marked unavailable — never fabricated.

export interface SnapshotMetric {
  id: string;
  label: string;
  region: string;         // grouping: 'North America' | 'Europe' | 'Asia-Pacific' | ...
  kind: "rate" | "print" | "yield";
  value: number | null;
  asOf: string | null;    // vintage of the value
  unit: string;           // '%' | '' | 'index'
  country: string;
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
];

const PRINT_SOURCES: { id: string; label: string; region: string; country: string; kind: "print" | "yield"; unit: string; fred: FREDMeta }[] = [
  { id: "us-cpi", label: "US CPI (YoY)", region: "North America", country: "US", kind: "print", unit: "%", fred: { fredId: "CPIAUCSL", transform: "yoy" } as FREDMeta },
  { id: "us-gdp", label: "US Real GDP (YoY)", region: "North America", country: "US", kind: "print", unit: "%", fred: { fredId: "GDPC1", transform: "yoy" } as FREDMeta },
  { id: "us-unemp", label: "US Unemployment", region: "North America", country: "US", kind: "print", unit: "%", fred: { fredId: "UNRATE" } },
  { id: "us-10y", label: "US 10Y Treasury", region: "North America", country: "US", kind: "yield", unit: "%", fred: { fredId: "DGS10" } },
];

async function fredCSV(id: string): Promise<{ date: string; value: number }[]> {
  const res = await fetch(`https://fred.stlouisfed.org/graph/fredgraph.csv?id=${id}`, { signal: AbortSignal.timeout(15_000) });
  if (!res.ok) throw new Error(`HTTP ${res.status} from FRED CSV (${id})`);
  const csv = await res.text();
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

export async function buildSnapshot(): Promise<{ metrics: SnapshotMetric[]; builtAt: string }> {
  const specs: { id: string; label: string; region: string; country: string; kind: SnapshotMetric["kind"]; unit: string; fred: FREDMeta }[] = [
    ...RATE_SOURCES.map((r) => ({ id: r.id, label: r.label, region: r.region, country: r.country, kind: "rate" as const, unit: "%", fred: r.fred })),
    ...PRINT_SOURCES.map((p) => ({ id: p.id, label: p.label, region: p.region, country: p.country, kind: p.kind, unit: p.unit, fred: p.fred })),
  ];

  const metrics = await Promise.all(
    specs.map(async (s): Promise<SnapshotMetric> => {
      try {
        let points = await fredCSV(s.fred.fredId);
        if (s.fred.transform === "yoy") points = yoy(points);
        if (points.length === 0) throw new Error("no data");
        const last = points[points.length - 1];
        return { id: s.id, label: s.label, region: s.region, kind: s.kind, country: s.country, unit: s.unit, value: last.value, asOf: last.date };
      } catch (err) {
        console.error(`[economics/snapshot] ${s.id} failed:`, err instanceof Error ? err.message : err);
        return { id: s.id, label: s.label, region: s.region, kind: s.kind, country: s.country, unit: s.unit, value: null, asOf: null };
      }
    })
  );

  return { metrics, builtAt: new Date().toISOString() };
}