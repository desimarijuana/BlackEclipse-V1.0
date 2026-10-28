# Staged Widening Queue

`GET /evolution/tool-contracts` classifies tools; this phase lets an operator
stage the eligible read-only ones as **durable proposals**.

## What a proposal is

A `WideningProposal` row records:

- `toolName`;
- `status` = `needs_evidence` (or `withdrawn`);
- the tool contract and the eligibility reasons from the shadow report;
- the evidence checklist: `historicalReplay`, `denyPath`, `conclusionStability`
  (all `false` at staging);
- `createdAt`, `expiresAt` (14 days default), `stagedBy`.

**Staging is not permission.** No allowlist, agent preset, registry entry, or
runtime surface changes.

## Surfaces

- `POST /evolution/widening/stage` (operator) — stages up to `limit` eligible
  tools; duplicates are skipped; effectful/financial/mechanism tools are never
  eligible.
- `GET /evolution/widening` — list proposals.
- `POST /evolution/widening/{id}/evidence` — attach one checklist item
  (`historicalReplay`, `denyPath`, `conclusionStability`); all three move the
  status to `ready_for_ratification`.
- `POST /evolution/widening/{id}/approve` — operator approval; status becomes
  `approved_pending_application`. **No runtime surface changes.**
- `POST /evolution/widening/{id}/withdraw` — withdraw a proposal.

## Tests

`test_widening_queue.py`: stages the one read-only tool, excludes write and
financial tools, skips a duplicate, attaches the three evidence items until
`ready_for_ratification`, approves to `approved_pending_application`, and refuses
withdrawal after approval; the registry is unchanged.

## Not built

No runtime grant, no allowlist change, no automatic application. Approval records
the decision only; applying a ratified tool remains a separate operator action.
