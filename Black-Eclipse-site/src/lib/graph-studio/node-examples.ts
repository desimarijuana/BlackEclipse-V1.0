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
};

export function exampleFor(nodeType: string): string | undefined {
  return EXAMPLES[nodeType];
}

export const EXAMPLE_NODE_TYPES = Object.keys(EXAMPLES);
