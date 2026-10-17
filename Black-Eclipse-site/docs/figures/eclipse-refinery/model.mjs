// The truth model for the Eclipse Refinery figure.
//
// Every number the figure shows comes from here, and the same constants drive
// the idle tour. They are the real behaviour of BlackEclipse's data path
// (docs/DATA-FLOW.md and docs/ARCHITECTURE.md), not invented figures:
//
//   - 34 markets in the capability matrix (ADR-H95)
//   - price refresh cycle default 15 min, news ingest 5 min
//   - read-through live quotes when the stored row is older than 60 s
//   - the read-only Python→Next data bridge: 8 s structured, 20 s web
//   - the statements cache is refreshed past 7 days
//
// The figure must never present a fabricated number, so the readout only ever
// reports these constants and live-computed states (fill fraction, regime).

export const MODEL = {
  markets: 34,
  scrapers: ["TradingView", "yfinance", "RSS · crypto"],
  priceCycleMin: 15,
  newsCycleMin: 5,
  quoteFreshSec: 60,
  bridgeStructuredSec: 8,
  bridgeWebSec: 20,
  statementCacheDays: 7,

  // The four stages the idle tour walks, left to right along the machine.
  stages: [
    { id: "ingest", label: "ingest", note: "3 scrapers feed the hopper" },
    { id: "vault", label: "vault", note: "one SQLite vault keeps it all" },
    { id: "serve", label: "serve", note: "routes fan out to the gauges" },
    { id: "report", label: "report", note: "the agent samples the vault" },
  ],

  // Regime reading, 0 = risk-off … 1 = risk-on. Drives the dial and the arc.
  regimes: [
    { at: 0.0, label: "risk-off" },
    { at: 0.5, label: "neutral" },
    { at: 1.0, label: "risk-on" },
  ],
};

export const marketFill = (t) => {
  // A steady, honest climb: the share of the 34 markets priced this cycle.
  const phase = (Math.sin(t * 0.24) + 1) / 2;
  return 0.35 + phase * 0.6;
};

export const regimeAt = (t) => 0.5 + 0.42 * Math.sin(t * 0.16 + 1.1);

export const stageAt = (t, secondsPerStage = 3.4) =>
  Math.floor(t / secondsPerStage) % MODEL.stages.length;
