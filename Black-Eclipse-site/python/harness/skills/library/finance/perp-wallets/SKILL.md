# Perp Wallets

## Purpose

Give a clear picture of perpetual sub-accounts and prepare, but not execute, transfers between them.

## When to use

- The user asks which perp wallets exist or what they hold.
- A transfer between spot and perps needs a plan.
- Balances disagree and need reconciliation.

## When not to use

- Spot wallet operations unrelated to perps.
- Executing a transfer without explicit approval.

## Procedure

1. List wallets and resolve the requested wallet unambiguously.
2. Read balances and recent activity.
3. Reconcile against recorded transfers and fills.
4. For a transfer, show source, destination, amount, and fee.
5. Ask for explicit approval before any movement.
6. Record the approved plan in the journal.

## Guardrails

- Never fabricate data, sources, prices, or dates. Missing data is `UNAVAILABLE`.
- Record the source and retrieval time for every factual value.
- Do not execute trades, move funds, or mutate external systems from this skill.
- Never move funds automatically.
- Never guess a wallet from a partial name.
- Report unresolved reconciliation differences.

## Output

Return the wallet view and, when relevant, an approval-gated transfer plan.

