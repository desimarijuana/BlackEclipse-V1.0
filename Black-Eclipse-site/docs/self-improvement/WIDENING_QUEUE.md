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
- `POST /evolution/widening/{id}/apply` — apply an approved proposal as a
  **read-only** runtime grant (default TTL 7 days). Revalidates the tool against
  the contract shadow; refuses effectful/financial/high-risk tools, unknown
  tools, unapproved proposals, and duplicates.
- `GET /evolution/widening/grants` — active grants.
- `POST /evolution/widening/grants/{id}/revoke` — revoke a grant immediately.
- `POST /evolution/widening/{id}/withdraw` — withdraw a proposal.

## Runtime overlay

`widening_runtime.py` keeps an in-process map of `agentId -> read-only tool
names`, refreshed on boot, apply, revoke, and the self-modification tick. The
surface unions those names into `eclipse-agent`'s allowlist only when the
registry tool is still `read`, non-effectful, and `none`/`low` risk. Expired
grants are excluded immediately and marked expired by the tick. This changes
only the run's bound schema; it never edits the agent preset or a source file.

## Tests

`test_widening_queue.py`: stages the one read-only tool, excludes write and
financial tools, skips a duplicate, attaches the three evidence items until
`ready_for_ratification`, approves to `approved_pending_application`, refuses
withdrawal after approval, applies the grant, sees it in `eclipse-agent`'s
effective allowlist, and revokes it back out.

## Not built

No automatic application and no effectful/financial widening. Apply remains an
operator action, and only read-only, non-effectful, `none`/`low`-risk tools can
be granted.
