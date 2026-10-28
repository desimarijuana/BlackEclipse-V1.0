# Strategy Codegen

## Purpose

Turn a trading idea into a validated strategy with an honest backtest, then prepare deployment for approval.

## When to use

- The user wants a rule-based strategy written or backtested.
- An existing strategy needs validation or iteration.

## When not to use

- Discretionary trade ideas with no rules.
- Deploying without out-of-sample evidence.

## Procedure

1. Write the entry, exit, sizing, and universe rules explicitly.
2. Implement in the strategy runtime and validate the graph or code.
3. Backtest in-sample, then run out-of-sample and walk-forward tests.
4. Report costs, slippage, turnover, and drawdown.
5. Stress the parameter surface and report fragility.
6. Request approval before deployment.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- No look-ahead, survivorship bias, or cost-free backtests.
- Never present an in-sample curve as expected future performance.
- Do not deploy without approval.

## Output

Return the strategy, backtest, validation, and risks.

