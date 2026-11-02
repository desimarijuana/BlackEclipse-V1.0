// ── Per-node examples ─────────────────────────────────────────────────────────
// Presentation only: one concrete "input → output" line per node, shown in the
// inspector under the docs. Kept out of the registry on purpose — it is teaching
// material, not a contract, so it must not appear in the manifest or the
// cross-language parity check.
//
// A missing entry is fine (most nodes are self-explanatory once ports are
// labelled); the logic/control-flow pack and the everyday data/transform nodes
// are what people actually get stuck on.

const EXAMPLES: Record<string, string> = {
  'logic.condition':
    'value 87 · operator "gt" · compare 80  →  "If true" fires, Result = true',
  'logic.switch':
    'cases "buy, sell, hold" · value "sell"  →  case2 fires (plus Any match), Case index = 1',
  'logic.merge':
    'A is empty (skipped branch), B has 3 rows  →  value = the 3 rows',
  'logic.assert':
    'value 0 · expect "truthy"  →  node fails with "need at least one row"',
  'logic.fallback':
    'in1 empty, in2 null, in3 has 3 rows  →  Value = the 3 rows, Source = in3',
  'logic.human_approval':
    'message "Submit the order?"  →  the run pauses; after Approve, Value passes through and Done fires',
  'flow.gate':
    'Run fires  →  Value passes through, Done fires',
  'logic.map':
    'items [-2, 0, 5] · expression "value * 10"  →  [-20, 0, 50]',
  'logic.filter':
    'items [-2, 0, 5] · expression "value > 0"  →  [5], Dropped = 2',
  'logic.reduce':
    'items [1, 2, 3] · expression "acc + value" · initial 0  →  6',
  'logic.aggregate':
    'rows Tech 100 / Tech 300 / Fin 200 · field close · op avg · groupBy sector  →  Tech 200, Fin 200',
  'logic.deduplicate':
    'rows AAPL, AAPL, MSFT · keys "symbol"  →  2 rows kept, Dropped = 1',
  'logic.wait':
    'ms 500  →  Waited = 500 (a durable run pauses instead of blocking)',
  'logic.stop':
    'status "failed", message "exposure limit breached"  →  the run ends FAILED with that message',
  'flow.repeat':
    'input 1000 · count 12 · body "x * 1.07"  →  State 2252.19, Iterations = 12',
  'flow.while':
    'input 1000 · condition "value < 2000" · body "x * 1.07"  →  State 2104.85 after 11 iterations',
  'flow.for_each':
    'items [1000, 1500] · body "x * 1.07"  →  Results [1070, 1605], Iterations = 2',
  'flow.parallel':
    'items [1, 2, 3] · concurrency 2 · body "x * 2"  →  Results = [2, 4, 6] in INPUT order',
  'flow.subworkflow':
    'input "AAPL"  →  the child runs and Output = its terminal value',
  'transform.template':
    'a = { price: 190.456 } · "price {{a.price:.2f}}"  →  "price 190.46"',
  'transform.formula':
    'x = 12 · "clamp(x, 0, 10)"  →  10',
  'transform.select':
    'rows [{ symbol, close, sector }] · fields "symbol,close"  →  two columns per row',
  'transform.sort_limit':
    'rows close 100 / 300 / 200 · field "close desc", limit 2  →  MSFT, JPM',
  'transform.join':
    'left [AAPL], right [AAPL] · keys "symbol" · how inner  →  one merged row',
  'data.value':
    'value "1000", dataType number  →  1000',
  'data.json.parse':
    'text "[1, 2, 3]"  →  [1, 2, 3]',
  'finance.market_data':
    'symbol AAPL · interval 1d · lookback 200  →  OHLCV series + provenance',
  'finance.indicator':
    'series · kind sma · period 50  →  values series (warm-up points are null)',
  'quant.zscore':
    'values · period 20  →  z-score series',
  'quant.resample':
    'series 1h · targetInterval 1d  →  daily OHLCV (buckets with too few hours marked partial)',
  'quant.benchmark':
    'backtest result (includeSeries on) · benchmark 1d  →  alpha, beta, tracking error, IR',
  'quant.grade':
    'metrics + trades + Monte Carlo  →  grade B (76/100), 1 warning flag',
  'quant.robustness':
    'series · paramSpaceJson · costMultipliersJson [1,2,5]  →  verdict "fragile" + conclusions',
  'quant.trade_analysis':
    'trades + the bars they traded  →  per-regime P&L, concentration, unclassified count',
  'quant.multiple_testing':
    'optimize trials + backtest result  →  deflated Sharpe 0.62, PBO 41%',
  'quant.align':
    '{ AAPL: bars, MSFT: bars } · join inner · fill none  →  common timestamps + per-symbol missing counts',
  'quant.regime':
    'daily bars · fast 20 / slow 50  →  labels up_normal / down_high …, warm-up `unknown`',
  'quant.position_size':
    'price 190 · stop 4.5 · percent_risk 1% · equity 100k  →  222 units (notional 42,180)',
  'quant.portfolio_backtest':
    '{ AAPL: bars, MSFT: bars } · preset ema_cross  →  one book, combined equity + trades',
  'quant.costs':
    'orders [{buy 100 @ 190}] · kind transaction · commission 0.05%  →  total 9.5',
  'quant.edge_report':
    'backtest result (includeSeries on) + Monte Carlo  →  Markdown report + chart specs + grade',
  'quant.options_strategy':
    'bull call spread 490/510 · spot 500 · 30 days · IV 22%  →  payoff curve, break-even 502, net Greeks',
  'quant.futures_continuous':
    'ES MAR + JUN contracts · roll 2024-03-15 · adjustment difference  →  one continuous OHLCV proxy',
  'research.latest':
    'questionMatch "NVDA revenue"  →  the newest matching researchId + run row',
  'research.sources':
    'domain "sec.gov" · publishedAfter "2026-01-01"  →  deduped sources, plus excludedUndated count',
  'research.gaps':
    'run with one unanswered required question  →  [{ kind: "question", … }], hasGaps = true',
  'research.freshness':
    'asOf "2026-06-30" · freshness "quarter"  →  admissible evidence + every rejection reason',
  'research.conflict_scan':
    'evidence with revenue 100 and 110 (same period)  →  one UNRESOLVED conflict, never a winner',
  'research.citation_audit':
    'a SUPPORTED claim with no citation  →  ok false, coverage 0.8, issue names the claim',
  'research.supersession':
    '10-K amendment with provenance.supersedesEvidenceId  →  currentByKey points at the amendment',
  'research.quality':
    'sources + evidence + claims  →  score 0.72 (MODERATE), components + disclaimer',
  'research.entities':
    'run about NVDA  →  entities and relations, unanchored count 0',
  'research.claims_verify':
    '3 claims · run has an unresolved revenue conflict  →  that claim is CONTRADICTED',
  'research.start_run':
    'question "Did NVDA revenue grow?"  →  r_ab12… (same id on a re-run, existing run untouched)',
  'research.snapshot':
    'include "all"  →  snapshotId r_ab12…_v1, version 1, per-section counts',
  'research.fetch_many':
    'web_search results (8 URLs) · concurrency 2  →  8 pages, duplicate content fetched once',
  'research.scrape':
    'SEC filing page · tables true · maxRows 200  →  rows + first two tables',
  'research.extract_facts':
    'pages from a 10-K · legs [{ metric: "revenue", period: "FY2025" }]  →  validated evidence or a named rejection',
  'research.deep_dive':
    'question "Did NVDA revenue grow?" · depth standard  →  researchId + answer + coverage, readable by research.evidence',
  'research.ingest':
    'agent.research blob (3 evidence, 1 claim) · sourceLabel "agent:analyst"  →  stored with eclipseVerified false',
  'research.diff':
    'baseId r_a · compareId r_b (same question)  →  +2 evidence, 1 claim SUPPORTED→CONTRADICTED, 1 conflict opened',
  'research.queries':
    'question "Did revenue grow?" · 1 CONTRADICTED claim  →  answer, primary-source, support and disconfirming queries',
};

export function exampleFor(nodeType: string): string | undefined {
  return EXAMPLES[nodeType];
}

export const EXAMPLE_NODE_TYPES = Object.keys(EXAMPLES);
