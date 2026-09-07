---
name: black-eclipse-db
description: Black-Eclipse database rules — SQLite via Prisma (jdds.db, seed snapshot committed to git), WAL checkpointing before any commit of jdds.db, never re-commit jdds.db automatically, .env stays gitignored. Use when working with the database, prisma schema, seed data, git commits, or onboarding/open-source setup for this repo.
---

# Black-Eclipse DB

- Database is **SQLite** only (`Black-Eclipse-site/jdds.db`), accessed through Prisma + `@prisma/adapter-better-sqlite3` (`src/lib/db.ts`). Postgres was removed — do not reintroduce `DATABASE_URL` or pg tooling.
- `jdds.db` is a **seed snapshot committed to git once** (28 markets, ~55k assets, ~55k prices). Schema lives in `prisma/schema.prisma`; `prisma db push` auto-creates an empty DB for fresh clones, but the committed file ships real data for open-source users.
- **Never commit `jdds.db` again** on routine pushes — it changes constantly (scrapers run) and would bloat the repo. Update the snapshot deliberately only, e.g. monthly.
- If committing `jdds.db` (seed update), **checkpoint WAL first** or data is stale: `node -e` script calling `db.pragma('wal_checkpoint(TRUNCATE)')` via better-sqlite3 while the dev server is stopped.
- Runtime side files (`jdds.db-shm`, `jdds.db-wal`) are gitignored; `jdds.db` itself is NOT ignored (unusual — the ignore entry was removed on purpose).
- `.env` is gitignored and contains Google OAuth secrets + `CRON_SECRET` — never commit it. New machines need it copied manually.
- Import/seed scripts live in `Black-Eclipse-site/scripts/import-*.js` (US universe, PSX, India, Japan, etc.).
- GitHub Actions backup (`.github/workflows/backup.yml`) uses `sqlite3 jdds.db ".backup ..."` — SQLite-only, no Postgres.