# Wallet Transfers

## Purpose

Prepare an auditable funding plan and surface the exact fees, network, and address risks. Never move funds on its own.

## When to use

- The user wants to deposit, withdraw, or sweep funds.
- Moving USDC between spot and perps needs a plan.

## When not to use

- Trading a position.
- Any transfer without explicit user confirmation.

## Procedure

1. Confirm the asset, network, and destination identity.
2. Read available balances and any withdrawal limits.
3. Compute fees and the amount that will actually arrive.
4. Show the plan and require explicit confirmation.
5. Warn about wrong-network and wrong-address risk.
6. Record the approved plan; never broadcast it.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never invent an address or network.
- Never claim funds were sent.
- Never bypass an approval step.

## Output

Return the plan, fees, risks, and approval flag.

