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

const OWID_INDICATORS = [
  { value: "covid-vaccinations-doses-per-capita", label: "COVID vaccinations per capita" },
  { value: "co2-per-capita", label: "CO2 emissions per capita" },
  { value: "energy-consumption-per-capita", label: "Energy consumption per capita" },
  { value: "gdp-per-capita-worldbank", label: "GDP per capita (World Bank)" },
  { value: "life-expectancy", label: "Life expectancy" },
  { value: "population", label: "Population" },
];

// Small helper for a JSON GET.
async function getJSON(url: string): Promise<unknown> {
  const res = await fetch(url, { headers: { Accept: "application/json" }, signal: AbortSignal.timeout(20_000) });
  if (!res.ok) throw new Error(`HTTP ${res.status} from ${new URL(url).host}`);
  return res.json();
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
    id: "bls", label: "BLS", color: "#94a3b8", keyRequired: true, keyEnv: "BLS_API_KEY",
    description: "US Bureau of Labor Statistics (optional key raises limits)",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "CUSR0000SA0", options: [
          { value: "CUSR0000SA0", label: "CPI-U, all items (SA)" },
          { value: "LNS14000000", label: "Unemployment rate" },
          { value: "CES0000000001", label: "Nonfarm payrolls" },
          { value: "LAUS", label: "Local unemployment" },
        ],
      },
    ],
    fetch: async (p) => {
      const key = process.env.BLS_API_KEY;
      const headers: Record<string, string> = { "Content-Type": "application/json" };
      const body: Record<string, unknown> = { seriesid: [p.series || "CUSR0000SA0"], startyear: "2010", endyear: String(new Date().getFullYear()) };
      if (key) { headers.Authorization = `Bearer ${key}`; }
      const res = await fetch("https://api.bls.gov/publicAPI/v2/timeseries/data/", {
        method: "POST", headers, body: JSON.stringify(body), signal: AbortSignal.timeout(25_000),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status} from BLS`);
      return res.json();
    },
  },
  {
    id: "census", label: "US Census", color: "#8b5cf6",
    description: "Census Bureau Data API",
    controls: [
      {
        type: "select", name: "dataset", label: "Dataset", defaultValue: "nbas", options: [
          { value: "nbas", label: "Advance Monthly Retail Trade" },
          { value: "nips", label: "Nonresidential construction" },
        ],
      },
    ],
    fetch: (p) => getJSON(`https://api.census.gov/data/timeseries/eits/${p.dataset || "nbas"}?get=cell_value,time_slot_id,error_data,category_code,datatype_code,data_type_code,time_slot_start,seasonally_adj&for=us:*&time=from+2015`),
  },
  {
    id: "fiscaldata", label: "Fiscal Data", color: "#0d9488",
    description: "US Treasury Fiscal Data (debt to the penny)",
    controls: [
      {
        type: "select", name: "endpoint", label: "Dataset", defaultValue: "debt_to_penny", options: [
          { value: "debt_to_penny", label: "Debt to the Penny" },
          { value: "avg_interest_rates", label: "Average interest rates" },
        ],
      },
    ],
    fetch: (p) => {
      if ((p.endpoint || "debt_to_penny") === "avg_interest_rates") {
        return getJSON("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/avg_interest_rates?fields=record_date,security_desc,avg_interest_rate_amt&page[size]=5000");
      }
      return getJSON("https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny?fields=record_date,total_pub_debt_outstanding&page[size]=5000&sort=-record_date");
    },
  },
  {
    id: "bea", label: "BEA", color: "#f97316", keyRequired: true, keyEnv: "BEA_API_KEY",
    description: "US Bureau of Economic Analysis (requires free API key)",
    controls: [
      {
        type: "select", name: "dataset", label: "Dataset", defaultValue: "NIPA", options: [
          { value: "NIPA", label: "NIPA (GDP)" },
          { value: "Regional", label: "Regional GDP" },
        ],
      },
    ],
    fetch: (p) => {
      const key = process.env.BEA_API_KEY;
      if (!key) throw new Error("BEA_API_KEY is not set");
      return getJSON(`https://apps.bea.gov/api/data?UserID=${key}&datasetname=${p.dataset || "NIPA"}&TableName=T10101&Frequency=A&Year=ALL&ResultFormat=JSON`);
    },
  },
  {
    id: "nber", label: "NBER Cycles", color: "#a16207",
    description: "US business-cycle expansions & contractions",
    controls: [],
    fetch: () => getJSON("https://api.nber.org/us_business_cycle_cycle_dates.json"),
  },
  {
    id: "federalreserve", label: "Federal Reserve", color: "#4ade80",
    description: "Fed H.15 selected interest rates",
    controls: [
      {
        type: "select", name: "series", label: "Series", defaultValue: "DGS10", options: [
          { value: "DGS10", label: "10-Year Treasury" },
          { value: "DGS2", label: "2-Year Treasury" },
          { value: "DFF", label: "Fed Funds Rate" },
        ],
      },
    ],
    fetch: (p) => getJSON(`https://fred.stlouisfed.org/graph/fredgraph.csv?id=${p.series || "DGS10"}`).then((raw) => {
      const csv = String(raw as never);
      const lines = csv.trim().split("\n");
      return lines.slice(1).map((line) => {
        const [date, value] = line.split(",");
        return { date, value };
      });
    }),
  },

  // ─── Market / commercial ───────────────────────────────────────────────
  {
    id: "trading-economics", label: "Trading Economics", color: "#dc2626", keyRequired: true, keyEnv: "TRADING_ECONOMICS_API_KEY",
    description: "Live macro forecasts (client:guest key format)",
    controls: [
      { type: "text", name: "indicators", label: "Indicators (comma-sep)", defaultValue: "unemployment rate,gdp growth rate" },
      { type: "select", name: "country", label: "Country", options: [{ value: "united states", label: "United States" }, { value: "china", label: "China" }, { value: "germany", label: "Germany" }, { value: "japan", label: "Japan" }, { value: "united kingdom", label: "United Kingdom" }], defaultValue: "united states" },
    ],
    fetch: (p) => getJSON(`https://api.tradingeconomics.com/country/${p.country || "united states"}?c=${process.env.TRADING_ECONOMICS_API_KEY ?? ""}`),
  },
  {
    id: "economic-calendar", label: "Economic Calendar", color: "#ca8a04",
    description: "Upcoming economic releases (Fincept mirror)",
    controls: [],
    fetch: () => getJSON("https://fincept.pythonanywhere.com/api/v1/econocalendar/data"),
  },
  {
    id: "econdb", label: "EconDB", color: "#059669",
    description: "EconDB via Yahoo-style tickers (e.g. USGDPUSYOY)",
    controls: [
      { type: "text", name: "ticker", label: "Ticker", defaultValue: "USCPI" },
    ],
    fetch: async (p) => {
      const res = await fetch(`https://api.econdb.com/series/?format=json&token=econdb&ticker=${encodeURIComponent(p.ticker || "USCPI")}`, { signal: AbortSignal.timeout(20_000) });
      if (!res.ok) throw new Error(`HTTP ${res.status} from EconDB`);
      return res.json();
    },
  },
  {
    id: "bis", label: "BIS", color: "#7c3aed",
    description: "Bank for International Settlements SDMX",
    controls: [
      {
        type: "select", name: "flow", label: "Dataset", defaultValue: "WS_LONG_CI", options: [
          { value: "WS_LONG_CI", label: "Long-term interest rates" },
          { value: "WS_CREDIT_GIS", label: "Credit to private sector" },
        ],
      },
    ],
    fetch: async (p) => {
      const res = await fetch(`https://stats.bis.org/api/v1/data/${p.flow || "WS_LONG_CI"}.M.N...?format=json&startPeriod=2010`, { signal: AbortSignal.timeout(25_000) });
      if (!res.ok) throw new Error(`HTTP ${res.status} from BIS`);
      return res.json();
    },
  },
  {
    id: "cftc", label: "CFTC", color: "#ea580c",
    description: "Commitments of Traders — positioning data",
    controls: [
      { type: "text", name: "marketCode", label: "Market Code", defaultValue: "088691" },
    ],
    fetch: (p) => getJSON(`https://publicreporting.cftc.gov/resource/6dca-aqww.json?\$limit=1000&\$order=report_date_as_yyyy_mm_dd%20DESC&cftc_contract_market_code=${p.marketCode || "088691"}`),
  },
  {
    id: "eia", label: "EIA", color: "#ca8a04",
    description: "US Energy Information Administration open data",
    controls: [
      {
        type: "select", name: "route", label: "Series", defaultValue: "petroleum", options: [
          { value: "petroleum", label: "Petroleum & coal liquids" },
          { value: "natural-gas", label: "Natural gas" },
        ],
      },
    ],
    fetch: (p) => getJSON(`https://api.eia.gov/v2/${p.route || "petroleum"}/cons/data/?api_key=DEMO_KEY&frequency=monthly&data[0]=value&sort[0][column]=period&sort[0][direction]=desc&offset=0&length=5000`),
  },
  {
    id: "wto", label: "WTO", color: "#0891b2",
    description: "World Trade Organization stats (timeseries mirror)",
    controls: [],
    fetch: () => getJSON("https://timeseries.wto.org/api/v1/data/DF_TT_OWN_SHMPRT/A/USA/W00.MERCHANDISE.EXP..."),
  },

  // ─── National statistical offices ──────────────────────────────────────
  {
    id: "ons-uk", label: "ONS UK", color: "#4338ca",
    description: "UK Office for National Statistics",
    controls: [
      { type: "text", name: "dataset", label: "Dataset ID", defaultValue: "MM23" },
    ],
    fetch: async (p) => {
      const res = await fetch(`https://api.ons.gov.uk/timeseries/${p.dataset || "MM23"}/data`, { signal: AbortSignal.timeout(20_000) });
      if (!res.ok) throw new Error(`HTTP ${res.status} from ONS`);
      return res.json();
    },
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
    id: "akshare-china", label: "AkShare China", color: "#eab308", keyRequired: true, keyEnv: "AKSHARE_API_KEY",
    description: "China macro data bridge (requires AKSHARE_API_KEY)",
    controls: [
      { type: "text", name: "indicator", label: "Indicator", defaultValue: "gdp" },
    ],
    fetch: (p) => getJSON(`https://akshare.cn/api/macro/${p.indicator || "gdp"}?key=${process.env.AKSHARE_API_KEY ?? ""}`),
  },
  {
    id: "statcan", label: "StatCan", color: "#dc2626",
    description: "Statistics Canada WDS API",
    controls: [
      { type: "text", name: "pid", label: "Product ID", defaultValue: "1410028701" },
    ],
    fetch: async (p) => {
      const res = await fetch(`https://www150.statcan.gc.ca/t1/wds/rest/getDataFromVectorsAndLatestNPeriods/${p.pid || "1410028701"},60`, { signal: AbortSignal.timeout(25_000) });
      if (!res.ok) throw new Error(`HTTP ${res.status} from StatCan`);
      return res.json();
    },
  },

  // ─── International / thematic ──────────────────────────────────────────
  {
    id: "central-banks", label: "Central Banks", color: "#818cf8",
    description: "Policy rates from Fincept central-bank mirror",
    controls: [],
    fetch: () => getJSON("https://fincept.pythonanywhere.com/api/v1/centralbank/data"),
  },
  {
    id: "ilo", label: "ILO", color: "#f43f5e",
    description: "International Labour Organization SDMX",
    controls: [countryControl],
    fetch: (p) => getJSON(`https://sdmx.ilo.org/rest/data/ILO,DF_SDG_0831_SEX_SOC_RT,1.0/${p.country || "US"}?format=csvfilewithlabels&startPeriod=2000`),
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
    description: "Asian Development Bank Key Indicators (stub API)",
    controls: [countryControl],
    fetch: (p) => getJSON(`https://data.adb.org/api/v2/dataset/${p.country || "US"}/macro-indicators?format=json`),
  },
  {
    id: "unesco", label: "UNESCO", color: "#7c3aed",
    description: "UNESCO UIS education & science data",
    controls: [countryControl],
    fetch: (p) => getJSON(`https://api.uis.unesco.org/sdmx/data/UNESCO,DF_EDU_EXP,1.0/${p.country || "US"}.X_EXP_FDPG_X.GOV?format=jsondata&startPeriod=2010`),
  },
  {
    id: "owid", label: "Our World In Data", color: "#e879f9",
    description: "OWID indicator charts API",
    controls: [
      { type: "select", name: "indicator", label: "Indicator", options: OWID_INDICATORS, defaultValue: "co2-per-capita" },
      countryControl,
    ],
    fetch: async (p) => {
      const res = await fetch(`https://ourworldindata.org/grapher/${p.indicator || "co2-per-capita"}.csv?tab=chart&time=1990..latest&country=${p.country || "US"}`, { signal: AbortSignal.timeout(25_000) });
      if (!res.ok) throw new Error(`HTTP ${res.status} from OWID`);
      const csv = await res.text();
      const lines = csv.trim().split("\n");
      const header = (lines[0] || "").split(",");
      return lines.slice(1).map((line) => {
        const cells = line.split(",");
        const row: Record<string, string> = {};
        header.forEach((h, i) => { row[h.trim()] = (cells[i] ?? "").trim(); });
        return row;
      });
    },
  },
  {
    id: "fincept-macro", label: "Fincept Macro", color: "#64748b",
    description: "Fincept macro dashboard mirror (aggregate snapshots)",
    controls: [],
    fetch: () => getJSON("https://fincept.pythonanywhere.com/api/v1/macroindicators/data"),
  },
];

export function getSource(id: string): EconSource | undefined {
  return ECON_SOURCES.find((s) => s.id === id);
}