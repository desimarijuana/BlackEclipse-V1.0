# Read-Only Tool-Contract Shadow

This phase inventories registered tools that are **not** on an agent's surface
and classifies whether they could be widened later. It does not grant, activate,
register, or modify an allowlist — the report is evidence for an operator.

## Classification

A tool is `eligible_shadow` only when:

- its `ToolContract` has no hard violations;
- `permission == "read"`;
- `effect` is empty or `read`;
- `risk` is `none` or `low`;
- its name is not a financial-action or mechanism tool (same frozen markers as
  the widening safety case);
- it is not on an explicit blocked list.

Everything else is `ineligible` with named reasons:
`not_read_permission`, `effectful`, `high_risk`, `financial_action`, `mechanism`,
`blocked_tool`, or the contract violations.

## Surface

`GET /evolution/tool-contracts` (operator-gated) returns the counts and rows for
the finance agent's current surface. `note` states that nothing was granted.

## Tests

`test_tool_contract_shadow.py` registers read, write, financial, mechanism,
blocked and already-granted tools; it asserts one eligible row, named reasons for
the rest, and an unchanged registry.

## Not built

- No grant, TTL, or activation. A later phase would need the full evidence
  standard and an operator-authored class policy.
- No tool implementation change and no finance-agent allowlist change.
