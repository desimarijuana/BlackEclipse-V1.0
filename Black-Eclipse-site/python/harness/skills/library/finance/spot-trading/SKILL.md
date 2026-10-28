# Spot Trading Plan

## Purpose

Prepare a precise, reviewable spot trade or transfer plan. It deliberately stops before execution.

## When to use

- The user wants to buy, sell, swap, or transfer a supported asset.
- A spot order needs a preview and risk read.

## When not to use

- Derivatives or leverage; use `finance.perps-trading`.
- Unattended or automated execution.

## Procedure

1. Resolve the asset and venue; never assume a chain or ticker.
2. Read balances and available routes.
3. Quote the size, fees, slippage, and minimum received.
4. Show the plan and ask for explicit confirmation with `clarify`.
5. Record the intended trade in the journal only after approval.
6. If execution is requested, explain that Eclipse has no trading permission and hand off the plan.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never claim an order was placed.
- Never hide fees, slippage, or route risk.
- Do not retry a failed transaction automatically.

## Output

Return the plan, preview, risks, and an explicit approval-required flag.

