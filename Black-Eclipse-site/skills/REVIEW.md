# REVIEW.md — Code, Architecture & Context Review System

> Treat this as a **mandatory pre-completion checklist**. Before declaring any task done, run the relevant checks below against your actual changes.
> For a **financial product**, data accuracy and correctness outweigh visual polish. Never claim something is complete if it has not actually been verified.

---

## Test-After-Every-Change Rule (REQUIRED)

Run `npm run test` (Vitest) **and** `npx tsc --noEmit` **after every change**, not just at the end. Catching issues incrementally is far cheaper than debugging a large batch of broken changes.

## Functional Review

- [ ] Does the feature actually work? (Run it; don't assume.)
- [ ] Are all requested requirements implemented?
- [ ] Are edge cases handled (empty input, missing data, null/undefined)?
- [ ] Are loading states handled? (skeletons from `src/components/ui/skeleton.tsx`)
- [ ] Are empty states handled?
- [ ] Are error states handled? (see `src/components/ui/error-boundary.tsx`)
- [ ] Do APIs return the expected shape? (e.g. `/api/news` → `{ news, source, pagination }`)
- [ ] Is any server-only logic (RSS parsing, secrets) correctly in an API route, not a client component?

## Architectural Review (check against ARCHITECT.md)

- [ ] Does the implementation follow the documented architecture?
- [ ] Is existing functionality being duplicated? (reuse `use-screener-filters.ts`, `use-portfolio-engine.ts`, ui primitives)
- [ ] Is the correct layer/service being used?
- [ ] Is business logic in the correct location?
- [ ] Did the change introduce unnecessary coupling or dependencies?
- [ ] Did the change create technical debt (e.g. re-bloating a large file)?

## Data Review

- [ ] Is data accurate? (financial correctness first)
- [ ] Are stale values possible?
- [ ] Are null/undefined cases handled?
- [ ] Are timestamps correct and consistent?
- [ ] Are symbols correctly normalized (via `getTradingViewSymbol()` where relevant)?
- [ ] Are market-cap/volume string parsers (`1.3T`, `28.4B`, `540M`) correct?
- [ ] Is sentiment classification reasonable?

## Security Review

- [ ] Authentication / authorization (if any) respected
- [ ] No secrets or API keys in client-side code
- [ ] Environment variables only accessed server-side
- [ ] Input validation present
- [ ] No SQL/database injection risks (if a DB is added)
- [ ] No unintended API exposure
- [ ] Sensitive data not logged

## Performance Review

- [ ] No unnecessary API calls
- [ ] No N+1 / excessive DB calls
- [ ] No sequential ops that should be concurrent
- [ ] No memory leaks (clear intervals/timeouts)
- [ ] No expensive re-renders (use `useMemo`/`useCallback` where appropriate)
- [ ] No overly large payloads
- [ ] Respect external rate limits (RSS, APIs)

## UI/UX Review (check against IMPRINT.md)

- [ ] Visual consistency with the dark green-on-black identity
- [ ] Responsive behavior (don't just shrink desktop layouts)
- [ ] Typography consistency (sans for body+headings, mono for data)
- [ ] Reuses existing components, not one-off implementations
- [ ] Loading / empty / error states present
- [ ] Accessibility (keyboard nav, contrast, focus states)
- [ ] Numbers/prices formatted consistently and scannable

## Regression Review

- [ ] What existing functionality could this change break?
- [ ] Inspect related code and dependencies before declaring success.
- [ ] Run `npm run test` (Vitest) and `npx tsc --noEmit` — both must pass.
- [ ] Verify the affected screens render correctly (run the dev server).

---

## Final Review Output

For major changes, internally verify each item before reporting completion:

- **IMPLEMENTED** — the code exists and matches the intent
- **TESTED** — actually run it / ran the tests; not assumed
- **REVIEWED** — checked against this file
- **NO KNOWN REGRESSIONS** — inspected dependencies
- **ARCHITECTURE CONSISTENT** — matches ARCHITECT.md
- **UI CONSISTENT** — matches IMPRINT.md
- **DATA VALIDATED** — financial data is correct

Never fabricate a passing test. Never claim a fix worked without running it.
