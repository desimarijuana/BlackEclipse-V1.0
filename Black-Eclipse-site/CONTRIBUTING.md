# Contributing to BlackEclipse

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

1. Fork and clone the repository
2. Run `npm install`
3. Run `npm run desktop:dev` (Dev channel, port 3101) or `npm run desktop:refresh`
   (Stable, port 3100) to build and open the native window

The product is the **desktop app**; there is no website runtime in the daily
loop. See [`docs/QUICKSTART.md`](docs/QUICKSTART.md) for the channel layout and
`npm run desktop:doctor` for a one-screen status check.

No API keys or database setup are required. `npm install` runs `prisma generate`,
and first boot provisions and seeds JDDS via `scripts/doctor.js` / `prisma db push`
— `jdds.db` is runtime state (untracked), so you get real market data on screen
without any configuration.

New to the codebase? Read [`docs/OVERVIEW.md`](docs/OVERVIEW.md) first, then use
[`docs/NAVIGATION.md`](docs/NAVIGATION.md) to find the file you want.

## The release gate

`npm run check:all` is **the** release gate (same steps as CI,
`.github/workflows/ci.yml`): `prisma generate` → `tsc --noEmit` → `eslint` →
committed-secret scan → security preflight → decision-record (ADR) check →
harness size budget → `npm test` (Vitest + Python) → eval gates → the corpus
gate. CI additionally runs the two Playwright drift smokes
(`npm run test:drift`). Run the gate before any push.
Individual pieces: `npm test`, `npm run test:py`, `npm run test:evals`,
`npm run test:drift`, `npm run lint`, `npm run typecheck`,
`npm run check:secrets`, `npm run security:preflight`, `npm run check:adr`,
`npm run check:size`.

Two release-tag preconditions are **NOT part of the gate** because they hit the
network. A human must run **both** before creating a release tag:

- **`npm run test:smoke`** — contacts real external providers; the only check that
  exercises the live retrieval/research path end to end.
- **`npm run test:presets`** — resolves the `bin` of every shipped `stdio` MCP
  preset package via `npm view <pkg> bin` and fails if a package cannot be
  launched (e.g. it declares no executable). A preset is a promise that clicking
  it works; this is what catches a package that has no server code.

Both are deliberately never in `npm test` or CI.

## Public-release checks (maintainers)

`npm run check:all` asks "is this tree releasable?". It does **not** ask "is this
repository safe to publish?". Three commands answer that, and are deliberately
not part of `check:all` because a private working tree legitimately fails them:

- **`npm run check:oss`** — tracked secrets/state, required community files,
  absolute home paths, package metadata, the SBOM/notices pair, and git refs
  that still expose pre-rewrite data.
- **`npm run oss:prune-refs`** — dry run that names those refs and prints the
  exact `git push origin --delete` command; `-- --apply` executes it and prunes.
- **`npm run sbom`** — regenerates `sbom.cdx.json` and `THIRD-PARTY-NOTICES.md`
  from the lockfiles. CI and `check:oss` both reject a stale pair.

Read [`docs/OPEN-SOURCE-READINESS.md`](docs/OPEN-SOURCE-READINESS.md) before any
visibility change; it owns the deletion, rotation and GitHub-settings runbook.

## Time-dependent tests

Do **not** derive an assertion period from the live clock (`new Date()`,
`Date.now()`) and then assert against fixed-timestamp fixtures. A test like that
couples a hardcoded date to the wall-clock moment the suite runs, so it passes
for a while and then fails with no code change (the UTC month rollover of
`src/lib/journal/analytics/weekly.test.ts` was exactly this). Either pass the
period explicitly to the function under test, or derive the fixture from the
same chosen period — never mix a live clock with a literal fixture.

Journal dates are **UTC everywhere** (see the `src/lib/journal/dates.ts` row in
[`docs/NAVIGATION.md`](docs/NAVIGATION.md)); format month/day labels in UTC or
they render a month off.

## Code Style

- TypeScript, strict mode
- Components live in `src/components/` organized by domain (`screens/`, `layout/`, `chat/`, `ui/`)
- Reusable UI primitives go in `src/components/ui/`
- Use named exports, not default exports
- Run `npm run lint` before committing
- Line endings are normalized by the root `.gitattributes` (LF for text); leave it alone.

## Developer Certificate of Origin

Every commit must certify the contribution with a sign-off:

```sh
git commit -s -m "your message"
```

The [`DCO`](./DCO) (version 1.1) certifies that you wrote the contribution or
have the right to submit it under this project's licence. A commit without a
`Signed-off-by:` line is not merged. The DCO is separate from the MIT licence:
the licence grants use; the DCO records provenance.

## Pull Request Process

1. Ensure your code builds: `npm run build`
2. Run the release gate: `npm run check:all`
3. Update the README if your change affects usage
4. Add tests for new logic where practical
5. If your change alters architecture, a data shape/contract, or setup steps, update the owning doc in [`docs/`](docs/) — see [`skills/DOCS.md`](skills/DOCS.md). Append a dated `docs/CHANGELOG.md` entry (the `commit-msg` hook enforces this for non-doc changes).
6. Your PR will be reviewed

## Reporting Issues

- Include your OS, the app version and channel (Stable/Dev), and whether the
  Python harness was running
- Describe the expected vs. actual behavior
- If it's a visual bug, a screenshot helps
