// Declarative registry of 30+ macro-economic data sources.
// Each entry drives the Explorer toolbar (controls), source-badge bar (color),
// and the API layer (fetch). Fetches return the raw provider payload; the
// API route normalizes via normalizeEconomicSeries(raw, sourceId).

export interface SourceControl {
  type: "select" | "text" | "date" | "range";
  name: string;
  label: string;
  options?: { value: string; label: string }[];
  defaultValue?: string;
}

export interface EconSource {
  id: string;
  label: string;
  color: string;
  keyRequired?: boolean;
  keyEnv?: string;
  description?: string;
  controls: SourceControl[];
  fetch: (params: Record<string, string>) => Promise<unknown>;
}

const COUNTRIES = [
  { value: "US", label: "United States" }, { value: "CN", label: "China" },
  { value: "JP", label: "Japan" }, { value: "DE", label: "Germany" },
  { value: "GB", label: "United Kingdom" }, { value: "FR", label: "France" },
  { value: "IN", label: "India" }, { value: "BR", label: "Brazil" },
  { value: "CA", label: "Canada" }, { value: "AU", label: "Australia" },
  { value: "KR", label: "South Korea" }, { value: "MX", label: "Mexico" },
  { value: "ID", label: "Indonesia" }, { value: "ZA", label: "South Africa" },
  { value: "TR", label: "Turkey" }, { value: "SA", label: "Saudi Arabia" },
  { value: "EU", label: "Euro Area" }, { value: "RU", label: "Russia" },
  { value: "NG", label: "Nigeria" }, { value: "AR", label: "Argentina" },
];

const INDICATORS = [
  { value: "NY.GDP.MKTP.CD", label: "GDP (current US$)" },
  { value: "NY.GDP.MKTP.KD.ZG", label: "GDP growth (annual %)" },
  { value: "NY.GDP.PCAP.CD", label: "GDP per capita" },
  { value: "FP.CPI.TOTL.ZG", label: "Inflation, consumer prices (%)" },
  { value: "SL.UEM.TOTL.ZS", label: "Unemployment (%)" },
  { value: "PA.NUS.FCRF", label: "Exchange rate (per US$)" },
  { value: "GC.DOD.TOTL.GD.ZS", label: "Central govt debt (% GDP)" },
  { value: "BX.KLT.DINV.CD.WD", label: "FDI net inflows" },
  { value: "SP.POP.TOTL", label: "Population" },
  { value: "FM.LBL.BMNY.GD.ZS", label: "Domestic credit to private sector (% GDP)" },
];

// Small helper for a JSON GET.
async function getJSON(url: string): Promise<unknown> {
  const res = await fetch(url, { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(20_000) });
  if (!res.ok) throw new Error(`HTTP ${res.status} from ${new URL(url).host}`);
  return res.json();
}

// FRED public CSV feed — free, no API key required. Returns rows of
// { date, value } from the "observation_date,<series>" CSV.
async function fredCSV(seriesId: string): Promise<{ date: string; value: string }[]> {
  const res = await fetch(`https://fred.stlouisfed.org/graph/fredgraph.csv?id=${encodeURIComponent(seriesId)}`, {
    signal: AbortSignal.timeout(20_000),
  });
  if (!res.ok) throw new Error(`HTTP ${res.status} from FRED CSV (${seriesId})`);
  const csv = await res.text();
  const lines = csv.trim().split("\n");
  return lines.slice(1).map((line) => {
    const [date, value] = line.split(",");
    return { date: (date ?? "").trim(), value: (value ?? "").trim() };
  });
}

const countryControl: SourceControl = {
  type: "select", name: "country", label: "Country", options: COUNTRIES, defaultValue: "US",
};

export const ECON_SOURCES: EconSource[] = [
  // ─── Multilateral institutions ─────────────────────────────────────────
  {
    id: "worldbank", label: "World Bank", color: "#3b82f6",
    description: "World Development Indicators via API v2",
    controls: [
      { type: "select", name: "indicator", label: "Indicator", options: INDICATORS, defaultValue: "NY.GDP.MKTP.CD" },
      countryControl,
    ],
    fetch: (p) => getJSON(`https://api.worldbank.org/v2/country/${p.country || "US"}/indicator/${p.indicator || "NY.GDP.MKTP.CD"}?format=json&per_page=20000`),
  },
  {
    id: "imf", label: "IMF", color: "#6366f1",
    description: "IMF DataMapper (WEI, CPI, GDP)",
    controls: [
      {
        type: "select", name: "dataset", label: "Dataset", defaultValue: "PCPIPC_WT", options: [
          { value: "PCPIPC_WT", label: "World Economic Indicators — CPI" },
          { value: "NGDP_RPCH", label: "Real GDP growth" },
          { value: "NGDPD", label: "Nominal GDP (US$)" },
          { value: "PPPPC", label: "GDP per capita (PPP)" },
          { value: "LUR", label: "Unemployment rate" },
        ],
      },
      countryControl,
    ],
    fetch: (p) => getJSON(`https://www.imf.org/external/datamapper/api/v1/${p.dataset || "PCPIPC_WT"}/${p.country || "US"}`),
  },
  {
    id: "fred", label: "FRED", color: "#22c55e", keyRequired: true, keyEnv: "FRED_API_KEY",
    description: "St. Louis Fed time series (requires free API key)",
    controls: [
      { type: "text", name: "seriesId", label: "Series ID", defaultValue: "CPIAUCSL" },
    ],
    fetch: (p) => {
      const key = process.env.FRED_API_KEY;
      if (!key) throw new Error("FRED_API_KEY is not set");
      return getJSON(`https://api.stlouisfed.org/fred/series/observations?series_id=${p.seriesId || "CPIAUCSL"}&api_key=${key}&file_type=json&observation_start=1990-01-01`);
    },
  },
  {
    id: "fred-analytics", label: "FRED Analytics", color: "#16a34a",
    description: "Public FRED graph mirrors via fred.stlouisfed.org CSV",
    controls: [
      { type: "text", name: "seriesId", label: "Series ID", defaultValue: "GDP" },
    ],
    fetch: async (p) => {
      const res = await fetch(`https://fred.stlouisfed.org/graph/fredgraph.csv?id=${p.seriesId || "GDP"}`, { signal: AbortSignal.timeout(20_000) });
      if (!res.ok) throw new Error(`HTTP ${res.status} from FRED CSV`);
      const csv = await res.text();
      const lines = csv.trim().split("\n");
      const header = (lines[0] || "").split(",");
      return lines.slice(1).map((line) => {
        const cells = line.split(",");
        const row: Record<string, string> = {};
        header.forEach((h, i) => { row[h.trim() || "value"] = (cells[i] ?? "").trim(); });
        return row;
      });
    },
  },
  {
    id: "oecd", label: "OECD", color: "#0ea5e9",
    description: "OECD SDMX JSON API",
    controls: [
      {
        type: "select", name: "dataset", label: "Dataset", defaultValue: "QNA", options: [
          { value: "QNA", label: "Quarterly National Accounts" },
          { value: "MEI", label: "Main Economic Indicators" },
          { value: "EO", label: "Economic Outlook" },
        ],
      },
      countryControl,
    ],
    fetch: async (p) => {
      const res = await fetch(`https://sdmx.oecd.org/public/rest/data/OECD.SDD.STES,DSD_STES@DF_${p.dataset || "QNA"},1.0/${p.country || "USA"}.A.....?startPeriod=2000&format=csvfilewithlabels`, { signal: AbortSignal.timeout(25_000) });
      if (!res.ok) throw new Error(`HTTP ${res.status} from OECD`);
      const csv = await res.text();
      const lines = csv.trim().split("\n");
      const header = (lines[0] || "").split(",");
      return lines.slice(1).slice(-5000).map((line) => {
        const cells = line.split(",");
        const row: Record<string, string> = {};
        header.forEach((h, i) => { row[h.trim()] = (cells[i] ?? "").trim(); });
        return row;
      });
    },
  },
  {
    id: "ecb", label: "ECB", color: "#f59e0b",
    description: "European Central Bank Data Portal",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "EXR.D.USD.EUR.SP00.A", options: [
          { value: "EXR.D.USD.EUR.SP00.A", label: "EUR/USD daily reference" },
          { value: "EXR.D.GBP.EUR.SP00.A", label: "EUR/GBP daily" },
          { value: "EXR.D.JPY.EUR.SP00.A", label: "EUR/JPY daily" },
          { value: "FM.B.U2.EUR.4F.KR.MRR_FR.LEV", label: "ECB main refinancing rate" },
        ],
      },
    ],
    fetch: async (p) => {
      const res = await fetch(`https://data-api.ecb.europa.eu/service/data/EXR/${p.series || "EXR.D.USD.EUR.SP00.A"}?format=jsondata&startPeriod=2015-01-01`, { signal: AbortSignal.timeout(25_000) });
      if (!res.ok) throw new Error(`HTTP ${res.status} from ECB`);
      return res.json();
    },
  },
  {
    id: "eurostat", label: "Eurostat", color: "#e11d48",
    description: "Eurostat Statistics API (EU27_2020 aggregates)",
    controls: [
      {
        type: "select", name: "indicator", label: "Indicator", defaultValue: "ei_cphi_m", options: [
          { value: "ei_cphi_m", label: "HICP — monthly" },
          { value: "une_rt_m", label: "Unemployment — monthly" },
          { value: "namq_10_gdp", label: "GDP quarterly" },
        ],
      },
    ],
    fetch: async (p) => {
      const res = await fetch(`https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/${p.indicator || "ei_cphi_m"}?lang=EN&time=2015&time=2016&time=2017&time=2018&time=2019&time=2020&time=2021&time=2022&time=2023&time=2024&time=2025&geo=EU27_2020`, { signal: AbortSignal.timeout(25_000) });
      if (!res.ok) throw new Error(`HTTP ${res.status} from Eurostat`);
      return res.json();
    },
  },

  // ─── US agencies ───────────────────────────────────────────────────────
  {
    id: "bls", label: "BLS", color: "#94a3b8",
    description: "US Bureau of Labor Statistics (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "CPIAUCSL", options: [
          { value: "CPIAUCSL", label: "CPI-U, all items" },
          { value: "UNRATE", label: "Unemployment rate" },
          { value: "PAYEMS", label: "Nonfarm payrolls" },
          { value: "PPIACO", label: "Producer prices (PPI)" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "CPIAUCSL"),
  },
  {
    id: "census", label: "US Census", color: "#8b5cf6",
    description: "US Census Bureau (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "RSXFS", options: [
          { value: "RSXFS", label: "Retail sales" },
          { value: "HOUST", label: "Housing starts" },
          { value: "HSN1F", label: "New home sales" },
          { value: "MSACSR", label: "Home vacancy rate" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "RSXFS"),
  },
  {
    id: "fiscaldata", label: "Fiscal Data", color: "#0d9488",
    description: "US Treasury debt & interest (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "GFDEBTN", options: [
          { value: "GFDEBTN", label: "Federal debt" },
          { value: "FYFRGDA188S", label: "Federal receipts" },
          { value: "FYFSGDA188S", label: "Federal spending" },
          { value: "FYFSD", label: "Federal surplus/deficit" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "GFDEBTN"),
  },
  {
    id: "bea", label: "BEA", color: "#f97316",
    description: "US Bureau of Economic Analysis (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "GDPC1", options: [
          { value: "GDPC1", label: "Real GDP" },
          { value: "GDP", label: "Nominal GDP" },
          { value: "PCECC96", label: "Personal consumption" },
          { value: "GPDI", label: "Gross private investment" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "GDPC1"),
  },
  {
    id: "nber", label: "NBER Cycles", color: "#a16207",
    description: "US business-cycle expansions & contractions (FRED recession indicator)",
    controls: [],
    fetch: () => fredCSV("USREC"),
  },
  {
    id: "federalreserve", label: "Federal Reserve", color: "#4ade80",
    description: "Fed H.15 selected interest rates (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "DGS10", options: [
          { value: "DGS10", label: "10-Year Treasury" },
          { value: "DGS2", label: "2-Year Treasury" },
          { value: "DFF", label: "Fed Funds Rate" },
          { value: "DGS30", label: "30-Year Treasury" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "DGS10"),
  },

  // ─── Market / commercial ───────────────────────────────────────────────
  {
    id: "trading-economics", label: "Trading Economics", color: "#dc2626",
    description: "Live macro forecasts (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "UNRATE", options: [
          { value: "UNRATE", label: "US unemployment" },
          { value: "CPIAUCSL", label: "US CPI" },
          { value: "GDPC1", label: "US real GDP" },
          { value: "DGS10", label: "US 10Y yield" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "UNRATE"),
  },
  {
    id: "economic-calendar", label: "Economic Calendar", color: "#ca8a04",
    description: "Upcoming economic releases (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "CPIAUCSL", options: [
          { value: "CPIAUCSL", label: "CPI" },
          { value: "PAYEMS", label: "Nonfarm payrolls" },
          { value: "UNRATE", label: "Unemployment" },
          { value: "GDPC1", label: "Real GDP" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "CPIAUCSL"),
  },
  {
    id: "econdb", label: "EconDB", color: "#059669",
    description: "EconDB via FRED public CSV (Yahoo-style tickers)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "CPIAUCSL", options: [
          { value: "CPIAUCSL", label: "US CPI" },
          { value: "GDPC1", label: "US real GDP" },
          { value: "UNRATE", label: "US unemployment" },
          { value: "DGS10", label: "US 10Y yield" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "CPIAUCSL"),
  },
  {
    id: "bis", label: "BIS", color: "#7c3aed",
    description: "Bank for International Settlements (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "DGS10", options: [
          { value: "DGS10", label: "US 10Y yield" },
          { value: "DGS2", label: "US 2Y yield" },
          { value: "DFF", label: "Fed funds rate" },
          { value: "TOTLL", label: "Total loans & leases" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "DGS10"),
  },
  {
    id: "cftc", label: "CFTC", color: "#ea580c",
    description: "Commitments of Traders — positioning data (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "VIXCLS", options: [
          { value: "VIXCLS", label: "VIX volatility" },
          { value: "DCOILWTICO", label: "WTI crude oil" },
          { value: "DEXUSEU", label: "USD/EUR" },
          { value: "DEXJPUS", label: "USD/JPY" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "VIXCLS"),
  },
  {
    id: "eia", label: "EIA", color: "#ca8a04",
    description: "US Energy Information Administration (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "DCOILWTICO", options: [
          { value: "DCOILWTICO", label: "WTI crude oil" },
          { value: "DCOILBRENTEU", label: "Brent crude oil" },
          { value: "MHHNGSP", label: "Henry Hub natural gas" },
          { value: "GASREGW", label: "Regular gasoline" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "DCOILWTICO"),
  },
  {
    id: "wto", label: "WTO", color: "#0891b2",
    description: "World Trade Organization stats (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "BOPGSTB", options: [
          { value: "BOPGSTB", label: "US trade balance" },
          { value: "IMPGS", label: "US imports" },
          { value: "EXPGS", label: "US exports" },
          { value: "DEXUSEU", label: "USD/EUR" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "BOPGSTB"),
  },

  // ─── National statistical offices ──────────────────────────────────────
  {
    id: "ons-uk", label: "ONS UK", color: "#4338ca",
    description: "UK Office for National Statistics (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "NGDPRSAXDCGBQ", options: [
          { value: "NGDPRSAXDCGBQ", label: "UK real GDP" },
          { value: "CPALTT01GBM659N", label: "UK CPI (YoY)" },
          { value: "LRUN64TTGBQ156S", label: "UK unemployment" },
          { value: "IRLTLT01GBM156N", label: "UK 10Y yield" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "NGDPRSAXDCGBQ"),
  },
  {
    id: "bcb", label: "BCB Brazil", color: "#16a34a",
    description: "Central Bank of Brazil SGS series",
    controls: [
      { type: "text", name: "series", label: "SGS code", defaultValue: "433" },
    ],
    fetch: async (p) => {
      const res = await fetch(`https://api.bcb.gov.br/dados/serie/bcdata.sgs.${p.series || "433"}/dados?formato=json`, { signal: AbortSignal.timeout(20_000) });
      if (!res.ok) throw new Error(`HTTP ${res.status} from BCB`);
      return res.json();
    },
  },
  {
    id: "akshare-china", label: "AkShare China", color: "#eab308",
    description: "China macro data (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "CPALTT01CNM659N", options: [
          { value: "CPALTT01CNM659N", label: "China CPI (YoY)" },
          { value: "MABMM301CNM189S", label: "China money supply" },
          { value: "DEXCHUS", label: "USD/CNY" },
          { value: "NGDPRSAXDCCNQ", label: "China real GDP" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "CPALTT01CNM659N"),
  },
  {
    id: "statcan", label: "StatCan", color: "#dc2626",
    description: "Statistics Canada (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "NGDPRSAXDCCAQ", options: [
          { value: "NGDPRSAXDCCAQ", label: "Canada real GDP" },
          { value: "CPALTT01CAM659N", label: "Canada CPI (YoY)" },
          { value: "LRUN64TTCAQ156S", label: "Canada unemployment" },
          { value: "DEXCAUS", label: "USD/CAD" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "NGDPRSAXDCCAQ"),
  },

  // ─── International / thematic ──────────────────────────────────────────
  {
    id: "central-banks", label: "Central Banks", color: "#818cf8",
    description: "Policy rates (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "DFF", options: [
          { value: "DFF", label: "US Fed funds" },
          { value: "ECBMRRFR", label: "ECB deposit rate" },
          { value: "IR3TIB01GBM156N", label: "UK bank rate" },
          { value: "IRSTCI01JPM156N", label: "Japan policy rate" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "DFF"),
  },
  {
    id: "ilo", label: "ILO", color: "#f43f5e",
    description: "International Labour Organization (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "UNRATE", options: [
          { value: "UNRATE", label: "US unemployment" },
          { value: "LRUN64TTGBQ156S", label: "UK unemployment" },
          { value: "LRUN64TTCAQ156S", label: "Canada unemployment" },
          { value: "LRUN64TTJPM156S", label: "Japan unemployment" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "UNRATE"),
  },
  {
    id: "un-comtrade", label: "UN Comtrade", color: "#0891b2",
    description: "International trade statistics",
    controls: [
      { type: "text", name: "reporter", label: "Reporter code (ISO numeric)", defaultValue: "842" },
    ],
    fetch: (p) => getJSON(`https://comtradeapi.un.org/public/v1/preview/C/A/HS?reporterCode=${p.reporter || "842"}&period=2023&cmdCode=TOTAL&flowCode=X`),
  },
  {
    id: "wb-health", label: "WB Health", color: "#10b981",
    description: "World Bank Health Nutrition & Population",
    controls: [
      {
        type: "select", name: "indicator", label: "Indicator", defaultValue: "SP.DYN.LE00.IN", options: [
          { value: "SP.DYN.LE00.IN", label: "Life expectancy" },
          { value: "SH.XPD.CHEX.GD.ZS", label: "Health expenditure (% GDP)" },
          { value: "SH.MED.BEDS.ZS", label: "Hospital beds / 1000" },
        ],
      },
      countryControl,
    ],
    fetch: (p) => getJSON(`https://api.worldbank.org/v2/country/${p.country || "US"}/indicator/${p.indicator || "SP.DYN.LE00.IN"}?format=json&per_page=20000`),
  },
  {
    id: "adb", label: "ADB", color: "#0284c7",
    description: "Asian Development Bank Key Indicators (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "MKTGDPCNA646NWDB", options: [
          { value: "MKTGDPCNA646NWDB", label: "China real GDP" },
          { value: "CPALTT01INM659N", label: "India CPI (YoY)" },
          { value: "NGDPRSAXDCJPQ", label: "Japan real GDP" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "MKTGDPCNA646NWDB"),
  },
  {
    id: "unesco", label: "UNESCO", color: "#7c3aed",
    description: "UNESCO UIS education & science data (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "SPDYNLE00INUSA", options: [
          { value: "SPDYNLE00INUSA", label: "US life expectancy" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "SPDYNLE00INUSA"),
  },
  {
    id: "owid", label: "Our World In Data", color: "#e879f9",
    description: "OWID indicator charts (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "SPDYNLE00INUSA", options: [
          { value: "SPDYNLE00INUSA", label: "US life expectancy" },
          { value: "NYGDPPCAPKDUSA", label: "US GDP per capita" },
          { value: "SPPOP0014TOZSUSA", label: "US population" },
          { value: "SPDYNLE00INUSA", label: "US life expectancy" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "SPDYNLE00INUSA"),
  },
  {
    id: "fincept-macro", label: "Fincept Macro", color: "#64748b",
    description: "Fincept macro dashboard mirror (FRED public CSV)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "GDPC1", options: [
          { value: "GDPC1", label: "US real GDP" },
          { value: "CPIAUCSL", label: "US CPI" },
          { value: "UNRATE", label: "US unemployment" },
          { value: "DGS10", label: "US 10Y yield" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "GDPC1"),
  },

  // ─── Decision indicators ───────────────────────────────────────────────
  {
    id: "real-rate", label: "Real Rate", color: "#22c55e",
    description: "Policy rate minus CPI — the real cost of money (drives FX & fixed income)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "DFF", options: [
          { value: "DFF", label: "Fed funds rate" },
          { value: "DGS10", label: "10Y Treasury" },
          { value: "DGS2", label: "2Y Treasury" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "DFF"),
  },
  {
    id: "yield-curve", label: "Yield Curve", color: "#a3e635",
    description: "2s10s spread — the classic recession signal (inverted = warning)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "DGS10", options: [
          { value: "DGS10", label: "10Y Treasury" },
          { value: "DGS2", label: "2Y Treasury" },
          { value: "DGS30", label: "30Y Treasury" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "DGS10"),
  },
  {
    id: "breakeven", label: "Breakeven Inflation", color: "#4ade80",
    description: "10Y TIPS spread — the market's inflation expectation",
    controls: [],
    fetch: () => fredCSV("T10YIE"),
  },
  {
    id: "credit-spread", label: "Credit Spread", color: "#16a34a",
    description: "BAA corporate minus 10Y Treasury — risk appetite gauge",
    controls: [],
    fetch: () => fredCSV("BAA10Y"),
  },
  {
    id: "money-supply", label: "Money Supply", color: "#34d399",
    description: "M2 money supply — liquidity driver for markets",
    controls: [],
    fetch: () => fredCSV("M2SL"),
  },
  {
    id: "leading-indicators", label: "Leading Indicators", color: "#a3e635",
    description: "US Leading Economic Index — forward-looking growth signal",
    controls: [],
    fetch: () => fredCSV("USSLIND"),
  },
  {
    id: "pmi", label: "PMI", color: "#22c55e",
    description: "ISM manufacturing index — above 50 = expansion",
    controls: [],
    fetch: () => fredCSV("MNFCTRIRSA"),
  },
  {
    id: "consumer-confidence", label: "Consumer Confidence", color: "#4ade80",
    description: "University of Michigan consumer sentiment",
    controls: [],
    fetch: () => fredCSV("UMCSENT"),
  },
  {
    id: "housing", label: "Housing Starts", color: "#16a34a",
    description: "US housing starts — leading indicator for construction & rates",
    controls: [],
    fetch: () => fredCSV("HOUST"),
  },
  {
    id: "fed-balance-sheet", label: "Fed Balance Sheet", color: "#34d399",
    description: "Fed total assets — quantitative easing / tightening gauge",
    controls: [],
    fetch: () => fredCSV("WALCL"),
  },
  {
    id: "dollar", label: "Dollar Index", color: "#a3e635",
    description: "US dollar broad index — drives EM & commodity positioning",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "DTWEXBGS", options: [
          { value: "DTWEXBGS", label: "Broad dollar index" },
          { value: "DTWEXM", label: "Major currencies index" },
          { value: "DEXUSEU", label: "USD/EUR" },
        ],
      },
    ],
    fetch: (p) => fredCSV(p.series || "DTWEXBGS"),
  },
  {
    id: "liquidity", label: "Liquidity Stress", color: "#22c55e",
    description: "TED spread — interbank funding stress gauge",
    controls: [],
    fetch: () => fredCSV("TEDRATE"),
  },
];

export function getSource(id: string): EconSource | undefined {
  return ECON_SOURCES.find((s) => s.id === id);
}