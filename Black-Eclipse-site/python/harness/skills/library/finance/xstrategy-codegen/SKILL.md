# Cross-Sectional Strategy Codegen

## Purpose

Build a cross-sectional score, form quantile baskets, and test the long-short portfolio with realistic costs.

## When to use

- The user wants a multi-asset or ranked basket strategy.
- A factor should be tested as a portfolio rather than a single signal.

## When not to use

- Single-asset timing strategies.
- Universe-agnostic ideas with no cross-sectional ranking.

## Procedure

1. Define the universe, rebalance cadence, and score formula.
2. Build the factor and test its cross-sectional predictive power.
3. Form quantile baskets and compute turnover and costs.
4. Run out-of-sample and regime tests.
5. Report capacity, crowding, and decay risk.
6. Request approval before deployment.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Guard against look-ahead in universe construction.
- Report multiple-testing and data-mining risk.
- Do not deploy without approval.

## Output

Return the factor, basket construction, backtest, and limitations.

