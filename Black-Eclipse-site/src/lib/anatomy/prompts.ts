// ── Example `/anatomy` prompts ────────────────────────────────────────────────
//
// The canonical quick-check list for the isometric mechanism figure. Used by
// `prompts.test.ts` to prove every one routes to the `agent.anatomy` directive
// that asks for a `response_block_schema`-validated `anatomy` block. Kept here
// (not only in a doc) so the list is exercised by CI. These are the same prompts
// you can paste into the composer to eyeball the rendering.

export const ANATOMY_EXAMPLE_PROMPTS = [
  '/anatomy how a limit order becomes a trade in a matching engine',
  '/anatomy the BlackEclipse market-data path from provider feed to JDdS to the agent --animated',
  '/anatomy how a portfolio rebalance decides what to buy and sell when a holding drifts past its target weight --animated',
  '/anatomy how an order book matches a market order',
  '/anatomy how the fiduciary gate verifies an advisory claim before the answer is sent --animated',
  '/anatomy how a FIFO cost-basis lot is opened and closed as buys and sells settle',
  '/visualize how slippage and market impact change a backtest result',
  '/mechanism how a stop-loss order triggers and executes',
] as const;
