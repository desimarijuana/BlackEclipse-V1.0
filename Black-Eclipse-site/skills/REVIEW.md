# REVIEW.md — Code, Architecture & Context Review System

> Treat this as a **mandatory pre-completion checklist**. **Run it at the end of EVERY task**, automatically — do not wait to be asked.
> For a **financial product**, data accuracy and correctness outweigh visual polish. Never claim something is complete if it has not actually been verified.

## When to run this
Run the full review checklist **before reporting any task complete**. This is not optional and not something to ask the user about — it is part of finishing the work.

**Git rule:** Do **not** commit, push, or create branches/PRs unless the user explicitly asks. When they do, inspect `git status`/`git diff` first, stage only intended files, and never commit secrets.

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

## Simplicity & Lightness Review (STANDING GOAL)

The site must be **simple, fast, and light**. Check every change against this:

- [ ] Did the change reuse existing hooks/components/services instead of adding new ones?
- [ ] Did the change add any new dependency? If so, is it justified and is it the lightest option?
- [ ] Is filtering/pagination done server-side (not pulling the whole universe client-side)?
- [ ] Did the change bloat a large file (e.g. `market-overview.tsx`)? Should logic be extracted into a hook/module?
- [ ] Is the DOM/JSX lean (no unnecessary wrappers, no heavy animations)?
- [ ] Is the bundle/payload kept small (no data shipped that the screen doesn't use)?
- [ ] Is the change simpler than the alternative, not more complex?

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

## Documentation Review (see DOCS.md)

Docs live in `docs/`. The obligation is **proportional** — a doc update is
required only when the change alters architecture, a data shape, a contract, or
setup steps.

- [ ] Did the change alter architecture, a data shape/contract, or setup? If so, update the owning doc (map it via `docs/NAVIGATION.md`).
- [ ] Did the change add/move a top-level folder or major module? Update `docs/NAVIGATION.md`.
- [ ] Did the change make an architectural decision? Add an ADR to `ARCHITECT.md` and mirror it in `docs/DECISIONS.md`.
- [ ] Is any doc now wrong? Mark it `status: Stale` (never delete) instead of leaving a confident lie.
- [ ] Did `last-verified` get bumped **only** for docs actually re-read against the code?
- [ ] **Was an entry appended to `docs/CHANGELOG.md`?** Required for *every*
  change, including ones needing no doc update.
- [ ] Does the final report state `docs updated: <file(s)>` or `no doc change — <reason>`?
- [ ] If docs were not needed, is the reason genuine (bug fix / refactor / style), not laziness?

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
