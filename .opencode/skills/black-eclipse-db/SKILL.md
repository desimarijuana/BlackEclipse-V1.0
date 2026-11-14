---
name: black-eclipse-db
description: Black-Eclipse database rules — SQLite via Prisma (jdds.db is untracked runtime data, never a committed snapshot), schema + demo seeding for fresh clones and installers, .env and backups stay gitignored. Use when working with the database, prisma schema, seed data, git commits, or onboarding/open-source setup for this repo.
---

# Black-Eclipse DB

- Database is **SQLite** only, accessed through Prisma + `@prisma/adapter-better-sqlite3`
  (`src/lib/db.ts`). Postgres was removed — do not reintroduce `DATABASE_URL` or pg tooling.
- **`jdds.db` is NOT tracked by git.** Root and app `.gitignore` both ignore `*.db`,
  `jdds.db-*`, `/.black-eclipse/`, `backups/`, `agent-memory.db`, `eclipse-memory.db`.
  Never `git add -f` a database. Old snapshots that predate this rule live in
  history; they are removed by `scripts/scrub-public-history.ps1`, not by a commit.
- The live file resolves through `src/lib/db.ts`: `BE_DB_PATH` → `BE_DATA_DIR` →
  the data dir (`Black-Eclipse-site/.black-eclipse/<channel>/jdds.db` under the
  launcher, the checkout root for a bare `dev`). `prisma.config.ts` reads the same
  variable, so CLI and runtime always agree.

## A fresh clone or install is never empty

No database ships in git. Two seeding layers fill it, sharing one implementation:

1. **Schema** — `scripts/doctor.js` (dev) and `scripts/desktop-server.js`
   `seedFirstRunDatabase` (installer) create the tables with `prisma db push`.
2. **Demo content** — `src/instrumentation.ts` calls `seedJournalDemo()` on boot
   (`src/lib/journal/demo.ts`). Deterministic PRNG, ~88 trades, 90 days.
   `scripts/lib/seed-db.js` runs the **same** seeder (`scripts/seed-journal.ts`)
   at package time so an installer's `app/seed/jdds.db` opens populated on first
   launch, and regenerates a stale schema-only seed left by an older build.

Demo contract, do not weaken it: every row is tagged `source: 'demo'`, seeding
runs **once ever** (marker `journal_demo_seeded_v1`), it never touches a journal
that already has trades, and `clearDemoData` + the marker is a permanent opt-out.
Demo rows are readable records, not fabricated live prices.

## Real data never ships

- Broker-synced trades are `source: 'broker'` (`externalId`, broker link). They
  are the user's account data — never part of a seed, never labelled demo.
- Personal vault, `backups/` rolling copies, `mcp-servers.json`, `.connector-key`,
  channel `secret.key`, and `.env*` (except `.env.example`) are all gitignored.
- `.env` holds OAuth/`CRON_SECRET`/provider keys; a new machine needs it copied
  manually, never committed.

## Pre-commit self-check

Before committing, run `git status` and confirm **no `.db`, `.db-wal`, `.env`,
`backups/`, or `.black-eclipse/` path is staged**. If one appears, it was added
with `-f` or a ignore rule regressed — fix the ignore, do not commit the file.

- Import/seed scripts live in `scripts/import-*.js` (US universe, PSX, India,
  Japan, …) and `scripts/seed-*.ts`.
- GitHub Actions backup (`.github/workflows/backup.yml`) uses `sqlite3 jdds.db
  ".backup …"` — SQLite-only, no Postgres.
