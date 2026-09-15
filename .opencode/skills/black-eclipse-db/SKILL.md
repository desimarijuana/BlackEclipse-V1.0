---
name: black-eclipse-db
description: Black-Eclipse database rules — SQLite via Prisma (jdds.db, seed snapshot committed to git), WAL checkpointing before any commit of jdds.db, never re-commit jdds.db automatically, .env stays gitignored. Use when working with the database, prisma schema, seed data, git commits, or onboarding/open-source setup for this repo.
---

# Black-Eclipse DB

- Database is **SQLite** only (`Black-Eclipse-site/jdds.db`), accessed through Prisma + `@prisma/adapter-better-sqlite3` (`src/lib/db.ts`). Postgres was removed — do not reintroduce `DATABASE_URL` or pg tooling.
- `jdds.db` is a **seed snapshot committed to git once** (28 markets, ~55k assets, ~55k prices). Schema lives in `prisma/schema.prisma`; `prisma db push` auto-creates an empty DB for fresh clones, but the committed file ships real data for open-source users.
- **Never commit `jdds.db` again** on routine pushes — it changes constantly (scrapers run) and would bloat the repo. Update the snapshot deliberately only, e.g. monthly.

## MANDATORY: the pre-commit `jdds.db` self-check

Before **every** commit/push, ask yourself: **"does the `jdds.db` in the repo need
to be updated for this change?"** Do not skip this because the file happens to
show as modified — it is almost always runtime churn.

Answer **YES (update the snapshot)** only if **either** is true:

1. **Schema changed** — `prisma/schema.prisma` was edited (new model/field/index)
   and fresh clones need the new shape.
2. **The shipped universe/data deliberately changed** — an `import-*.js` /
   `seed-*.ts` script was run or added, a market was added, or the snapshot is
   overdue (roughly monthly) and you have deliberately decided to refresh it.

Answer **NO (leave it modified and unstaged)** in every other case. Typical NO
signals:

- `prisma/` and `scripts/` show no changes for this work.
- The code changes are unrelated to data (UI, workspace, aurora, docs, …).
- The growth is background churn: **news `NewsItem` rows** (14-day rolling
  window), `MacroSeries` cache fills, or a handful of scraper-discovered
  assets/prices.

**How to check, not guess** (compare the working DB against `HEAD`):

```bash
# counts in the working copy
node -e "const D=require('better-sqlite3');const db=new D('jdds.db',{readonly:true});const q=s=>db.prepare(s).get().c;console.log('assets',q('select count(*) c from Asset'),'prices',q('select count(*) c from Price'),'news',q('select count(*) c from NewsItem'),'macro',q('select count(*) c from MacroSeries'));db.close()"
```

If new **markets** or a step change in **assets** appears, that is YES. If only
`news`/`macro`/price counts moved, that is NO.

### If the answer is YES

- **Checkpoint WAL first** or the snapshot is stale: with the dev server
  **stopped**, run a `node -e` script calling
  `db.pragma('wal_checkpoint(TRUNCATE)')` via better-sqlite3.
- Stage `jdds.db` **explicitly** (never `git add -A`) and call it out in the
  commit message as a deliberate seed update.
- `jdds.db-shm` / `jdds.db-wal` stay unstaged (gitignored).

### If the answer is NO

- Leave `jdds.db` modified in the working tree. Do **not** `git add` it, restore
  it, or commit it. A dirty `jdds.db` is the normal state while the dev server
  runs.
- Runtime side files (`jdds.db-shm`, `jdds.db-wal`) are gitignored; `jdds.db` itself is NOT ignored (unusual — the ignore entry was removed on purpose).
- `.env` is gitignored and contains Google OAuth secrets + `CRON_SECRET` — never commit it. New machines need it copied manually.
- Import/seed scripts live in `Black-Eclipse-site/scripts/import-*.js` (US universe, PSX, India, Japan, etc.).
- GitHub Actions backup (`.github/workflows/backup.yml`) uses `sqlite3 jdds.db ".backup ..."` — SQLite-only, no Postgres.