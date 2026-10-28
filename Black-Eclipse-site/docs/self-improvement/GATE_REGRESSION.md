# Learning Gate Regression

Phase 3 adds no capability and loosens no gate. These are the boundaries the
tests pin.

| Action | Gate | Enforcement |
|---|---|---|
| Accept a learning candidate | operator route + `{operator: true}` | `routers/sessions.py:accept_candidate` (`require_operator` + body flag) |
| `skill_create` / `skill_update` / `skill_delete` | single-use, digest-bound operator approval | `skills/manage_tools.py:make_skill_manage_authorizer` |
| `skill_learning_set` | single-use, digest-bound operator approval | `skills/lifecycle_tools.py:make_skill_lifecycle_authorizer` |
| `skill_version_evaluate` / `skill_version_activate` | same lifecycle approval | `skills/lifecycle_tools.py` |
| Effectful/global capability activation | `operator=True` in `builder.activate` | `capabilities/builder.py` |
| Advisory outcome scoring (cadence) | **not a capability grant** — writes only observed outcomes | `advisory/cadence.py` + `advisory/service.py:auto_evaluate` |

## Tests

- `test_candidate_accept_refuses_without_operator_flag` — missing/false body flag
  returns 403.
- `test_skill_authoring_tools_are_in_the_approval_sets`
- `test_skill_lifecycle_writes_are_in_the_approval_set`
- `test_effectful_capability_activation_requires_operator`
- Existing lifecycle E2E tests still assert one approval authorizes one call.

## What the cadence may write

Only `AdvisoryOutcome` rows for recommendations that already exist, have a
recorded entry price, and whose stated horizon elapsed. It cannot create a
recommendation, skill, memory, grant, or tool.
