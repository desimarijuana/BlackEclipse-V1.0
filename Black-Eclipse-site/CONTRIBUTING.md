# Contributing to BlackEclipse

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

1. Fork and clone the repository
2. Run `npm install`
3. Run `npm run dev` and open http://localhost:3000

No API keys or database setup are required. `npm install` runs `prisma generate`,
and first boot provisions and seeds JDDS via `scripts/doctor.js` / `prisma db push`
— `jdds.db` is runtime state (untracked), so you get real market data on screen
without any configuration.

New to the codebase? Read [`docs/OVERVIEW.md`](docs/OVERVIEW.md) first, then use
[`docs/NAVIGATION.md`](docs/NAVIGATION.md) to find the file you want.

## The release gate

`npm run check:all` is **the** release gate (same steps as CI,
`.github/workflows/ci.yml`): `prisma generate` → `tsc --noEmit` → `eslint` →
`npm test` (Vitest + Python) → `npm run test:evals`. Run it before any push.
Individual pieces: `npm test`, `npm run test:py`, `npm run test:evals`,
`npm run lint`, `npm run typecheck`.

**Live smoke (`npm run test:smoke`) is NOT part of the gate** — it contacts real
external providers. A human must run it **before creating a release tag** (it is
the only check that exercises the live retrieval/research path end to end). It is
deliberately never in `npm test` or CI.

## Code Style

- TypeScript, strict mode
- Components live in `src/components/` organized by domain (`screens/`, `layout/`, `chat/`, `ui/`)
- Reusable UI primitives go in `src/components/ui/`
- Use named exports, not default exports
- Run `npm run lint` before committing
- Line endings are normalized by the root `.gitattributes` (LF for text); leave it alone.

## Pull Request Process

1. Ensure your code builds: `npm run build`
2. Run the release gate: `npm run check:all`
3. Update the README if your change affects usage
4. Add tests for new logic where practical
5. If your change alters architecture, a data shape/contract, or setup steps, update the owning doc in [`docs/`](docs/) — see [`skills/DOCS.md`](skills/DOCS.md). Append a dated `docs/CHANGELOG.md` entry (the `commit-msg` hook enforces this for non-doc changes).
6. Your PR will be reviewed

## Reporting Issues

- Include the browser/OS you're using
- Describe the expected vs. actual behavior
- If it's a visual bug, a screenshot helps
