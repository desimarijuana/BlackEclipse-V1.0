---
name: blackeclipse-review
description: Mandatory pre-completion checklist before finishing any BlackEclipse task. Use to verify work across functional, architectural, data, security, performance, UI, and regression categories before reporting a task complete.
---

Treat `skills/REVIEW.md` as a mandatory pre-completion checklist. Before declaring a task done, verify:

- **Functional**: feature works, edge cases, loading/empty/error states
- **Architectural**: follows `skills/ARCHITECT.md`, no duplication, correct layers
- **Data**: financial accuracy, stale/null values, timestamps, symbol normalization
- **Security**: no secrets in client code, input validation, no unintended API exposure
- **Performance**: no N+1, no memory leaks, no unnecessary re-renders
- **UI/UX**: matches `skills/IMPRINT.md`, responsive, accessible, consistent
- **Regression**: inspect what could break, verify related code

**Test-after-every-change rule:** Run `npm run test` (Vitest) and `npx tsc --noEmit` after every change.

For major changes, internally confirm: IMPLEMENTED, TESTED, REVIEWED, NO KNOWN REGRESSIONS, ARCHITECTURE CONSISTENT, UI CONSISTENT, DATA VALIDATED.

Never claim a fix worked without running it. Never fabricate a passing test.
