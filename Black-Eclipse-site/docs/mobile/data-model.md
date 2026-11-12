---
title: Eclipse Mobile — Data Model
status: Proposed
last-verified: 2026-11-12
---

# Data model

SQLite is the only durable store. It is owned by Rust; the WebView has no SQL
access. This document defines the schema, migration rules, search, encryption,
and erasure.

## 1. Database setup

```
path: <app data dir>/eclipse-mobile.db
driver: rusqlite (bundled SQLite; SQLCipher variant if the Phase 0 spike passes)
journal_mode=WAL
foreign_keys=ON
synchronous=NORMAL
busy_timeout=5000
secure_delete=ON
temp_store=MEMORY
wal_autocheckpoint=1000
```

Rules:

- One writer. Commands enqueue writes on a dedicated DB thread (or a
  `tokio::sync::Mutex<Connection>`); no async task holds a connection across an
  `.await` that performs network I/O.
- Every multi-row mutation is one transaction.
- All timestamps are RFC 3339 UTC strings (`2026-11-12T18:04:21.512Z`).
- All ids are prefixed ULIDs/UUIDv7 strings: `bot_`, `grp_`, `thr_`, `msg_`,
  `run_`, `evt_`, `tcl_`, `apr_`, `mem_`, `sch_`, `att_`.
- JSON columns are `TEXT` with `CHECK (json_valid(col))`, validated in Rust before
  insert as well.
- No secret material is stored. Provider keys live in the OS keychain; the DB
  stores only `key_ref`.

## 2. Schema (v1)

```sql
CREATE TABLE schema_migrations (
  version    INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  applied_at TEXT NOT NULL
) STRICT;

CREATE TABLE bots (
  id             TEXT PRIMARY KEY,
  name           TEXT NOT NULL,
  description    TEXT,
  objective      TEXT NOT NULL DEFAULT '',
  avatar_json    TEXT CHECK (avatar_json IS NULL OR json_valid(avatar_json)),
  avatar_image   TEXT,                       -- relative path under avatars/
  model_provider TEXT,
  model_id       TEXT,
  agent_preset   TEXT NOT NULL DEFAULT 'mobile-agent',
  target         TEXT NOT NULL DEFAULT 'local_mobile'
                 CHECK (target IN ('local_mobile','local_desktop','remote_worker')),
  archived_at    TEXT,
  created_at     TEXT NOT NULL,
  updated_at     TEXT NOT NULL
) STRICT;

CREATE TABLE bot_groups (
  id          TEXT PRIMARY KEY,
  name        TEXT NOT NULL,
  avatar_json TEXT CHECK (avatar_json IS NULL OR json_valid(avatar_json)),
  avatar_image TEXT,
  created_at  TEXT NOT NULL,
  updated_at  TEXT NOT NULL
) STRICT;

CREATE TABLE group_members (
  group_id TEXT NOT NULL REFERENCES bot_groups(id) ON DELETE CASCADE,
  bot_id   TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  position INTEGER NOT NULL,
  PRIMARY KEY (group_id, bot_id)
) STRICT;

CREATE TABLE threads (
  id              TEXT PRIMARY KEY,
  kind            TEXT NOT NULL CHECK (kind IN ('bot','group')),
  bot_id          TEXT REFERENCES bots(id) ON DELETE CASCADE,
  group_id        TEXT REFERENCES bot_groups(id) ON DELETE CASCADE,
  title           TEXT,
  last_message_at TEXT,
  created_at      TEXT NOT NULL,
  updated_at      TEXT NOT NULL,
  CHECK ((kind = 'bot' AND bot_id IS NOT NULL AND group_id IS NULL)
      OR (kind = 'group' AND group_id IS NOT NULL AND bot_id IS NULL))
) STRICT;

CREATE TABLE messages (
  id            TEXT PRIMARY KEY,
  thread_id     TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
  thread_seq    INTEGER NOT NULL,
  role          TEXT NOT NULL CHECK (role IN ('user','assistant','system')),
  author_bot_id TEXT REFERENCES bots(id) ON DELETE SET NULL,
  content       TEXT NOT NULL DEFAULT '',
  status        TEXT NOT NULL DEFAULT 'final'
                CHECK (status IN ('streaming','final','error','interrupted')),
  error_class   TEXT,
  run_id        TEXT,
  reply_to_id   TEXT REFERENCES messages(id) ON DELETE SET NULL,
  meta_json     TEXT CHECK (meta_json IS NULL OR json_valid(meta_json)),
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL,
  UNIQUE (thread_id, thread_seq)
) STRICT;

CREATE TABLE runs (
  id              TEXT PRIMARY KEY,
  thread_id       TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
  bot_id          TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  group_id        TEXT REFERENCES bot_groups(id) ON DELETE CASCADE,
  turn_id         TEXT,                       -- groups a team turn
  kind            TEXT NOT NULL DEFAULT 'bot' CHECK (kind IN ('bot','group_member')),
  status          TEXT NOT NULL
                  CHECK (status IN ('created','queued','running','waiting_approval',
                                    'completed','failed','cancelled','interrupted')),
  trigger         TEXT NOT NULL CHECK (trigger IN ('user','schedule','catch_up','retry')),
  provider        TEXT,
  model           TEXT,
  input_json      TEXT CHECK (input_json IS NULL OR json_valid(input_json)),
  output_text     TEXT,
  error_class     TEXT,
  error_message   TEXT,
  attempt         INTEGER NOT NULL DEFAULT 1,
  last_seq        INTEGER NOT NULL DEFAULT 0,
  idempotency_key TEXT,
  owner_boot_id   TEXT,
  owner_pid       INTEGER,
  created_at      TEXT NOT NULL,
  started_at      TEXT,
  finished_at     TEXT,
  UNIQUE (thread_id, idempotency_key)
) STRICT;

CREATE TABLE run_members (
  run_id   TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  bot_id   TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  turn_id  TEXT NOT NULL,
  position INTEGER NOT NULL,
  PRIMARY KEY (run_id, bot_id)
) STRICT;

CREATE TABLE run_events (
  run_id  TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  seq     INTEGER NOT NULL,
  type    TEXT NOT NULL,
  at      TEXT NOT NULL,
  data_json TEXT NOT NULL CHECK (json_valid(data_json)),
  PRIMARY KEY (run_id, seq)
) STRICT;

CREATE TABLE tool_calls (
  id          TEXT PRIMARY KEY,
  run_id      TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  step        INTEGER NOT NULL,
  idx         INTEGER NOT NULL,
  name        TEXT NOT NULL,
  args_json   TEXT NOT NULL CHECK (json_valid(args_json)),
  args_digest TEXT NOT NULL,
  status      TEXT NOT NULL
              CHECK (status IN ('pending','awaiting_approval','running','completed',
                                'failed','denied','cancelled','unknown')),
  result_json TEXT CHECK (result_json IS NULL OR json_valid(result_json)),
  error_class TEXT,
  started_at  TEXT,
  finished_at TEXT,
  UNIQUE (run_id, step, idx)
) STRICT;

CREATE TABLE approvals (
  id           TEXT PRIMARY KEY,
  run_id       TEXT NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  tool_call_id TEXT REFERENCES tool_calls(id) ON DELETE CASCADE,
  kind         TEXT NOT NULL CHECK (kind IN ('tool','clarify')),
  title        TEXT NOT NULL,
  summary      TEXT NOT NULL DEFAULT '',
  effect       TEXT,
  risk         TEXT,
  tool_name    TEXT,
  args_json    TEXT CHECK (args_json IS NULL OR json_valid(args_json)),
  args_digest  TEXT,
  grant_pattern TEXT,
  status       TEXT NOT NULL
               CHECK (status IN ('pending','approved','denied','expired','consumed')),
  decision     TEXT,
  remember     INTEGER NOT NULL DEFAULT 0,
  question     TEXT,
  options_json TEXT CHECK (options_json IS NULL OR json_valid(options_json)),
  answer       TEXT,
  created_at   TEXT NOT NULL,
  expires_at   TEXT NOT NULL,
  decided_at   TEXT,
  CHECK ((kind = 'tool'    AND tool_call_id IS NOT NULL AND args_digest IS NOT NULL)
      OR (kind = 'clarify' AND question IS NOT NULL))
) STRICT;

CREATE TABLE memories (
  id            TEXT PRIMARY KEY,
  bot_id        TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  thread_id     TEXT REFERENCES threads(id) ON DELETE SET NULL,
  scope         TEXT NOT NULL DEFAULT 'conversation'
                CHECK (scope IN ('conversation','bot','group_member')),
  subject       TEXT NOT NULL DEFAULT '',
  content       TEXT NOT NULL,
  source_run_id TEXT REFERENCES runs(id) ON DELETE SET NULL,
  importance    INTEGER NOT NULL DEFAULT 3 CHECK (importance BETWEEN 1 AND 5),
  created_at    TEXT NOT NULL,
  updated_at    TEXT NOT NULL
) STRICT;

CREATE TABLE schedules (
  id               TEXT PRIMARY KEY,
  bot_id           TEXT NOT NULL REFERENCES bots(id) ON DELETE CASCADE,
  kind             TEXT NOT NULL
                   CHECK (kind IN ('manual','once','daily','weekdays','weekly',
                                   'monthly','interval','cron')),
  cron             TEXT,
  interval_seconds INTEGER,
  run_at           TEXT,
  timezone         TEXT NOT NULL,
  enabled          INTEGER NOT NULL DEFAULT 1,
  misfire          TEXT NOT NULL DEFAULT 'run_once'
                   CHECK (misfire IN ('skip','run_once','catch_up')),
  catch_up_max     INTEGER NOT NULL DEFAULT 1,
  next_run_at      TEXT,
  last_run_at      TEXT,
  created_at       TEXT NOT NULL,
  updated_at       TEXT NOT NULL
) STRICT;

CREATE TABLE attachments (
  id             TEXT PRIMARY KEY,
  thread_id      TEXT NOT NULL REFERENCES threads(id) ON DELETE CASCADE,
  message_id     TEXT REFERENCES messages(id) ON DELETE SET NULL,
  name           TEXT NOT NULL,
  mime           TEXT NOT NULL,
  byte_size      INTEGER NOT NULL,
  sha256         TEXT NOT NULL,
  storage_path   TEXT NOT NULL,              -- relative under attachments/
  extracted_text TEXT,
  truncated      INTEGER NOT NULL DEFAULT 0,
  created_at     TEXT NOT NULL
) STRICT;

CREATE TABLE provider_configs (
  provider      TEXT PRIMARY KEY,
  label         TEXT NOT NULL,
  base_url      TEXT,
  model_default TEXT,
  key_ref       TEXT,                        -- opaque keychain reference, never a key
  configured_at TEXT,
  updated_at    TEXT NOT NULL
) STRICT;

CREATE TABLE settings (
  key        TEXT PRIMARY KEY,
  value_json TEXT NOT NULL CHECK (json_valid(value_json)),
  updated_at TEXT NOT NULL
) STRICT;
```

## 3. Indexes

```sql
CREATE INDEX idx_messages_thread      ON messages(thread_id, thread_seq);
CREATE INDEX idx_messages_run         ON messages(run_id);
CREATE INDEX idx_threads_last         ON threads(last_message_at DESC);
CREATE INDEX idx_runs_thread          ON runs(thread_id, created_at DESC);
CREATE INDEX idx_runs_active          ON runs(status) WHERE status IN
  ('created','queued','running','waiting_approval');
CREATE INDEX idx_run_events_run       ON run_events(run_id, seq);
CREATE INDEX idx_tool_calls_run       ON tool_calls(run_id, step, idx);
CREATE INDEX idx_approvals_pending    ON approvals(status) WHERE status = 'pending';
CREATE INDEX idx_memories_bot         ON memories(bot_id, created_at DESC);
CREATE INDEX idx_schedules_due        ON schedules(enabled, next_run_at);
CREATE INDEX idx_attachments_thread   ON attachments(thread_id, created_at);
```

## 4. Full-text search (FTS5)

```sql
CREATE VIRTUAL TABLE messages_fts USING fts5(
  content,
  content='messages',
  content_rowid='rowid',
  tokenize='unicode61 remove_diacritics 2'
);

CREATE TRIGGER messages_ai AFTER INSERT ON messages BEGIN
  INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
END;
CREATE TRIGGER messages_ad AFTER DELETE ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content)
    VALUES ('delete', old.rowid, old.content);
END;
CREATE TRIGGER messages_au AFTER UPDATE OF content ON messages BEGIN
  INSERT INTO messages_fts(messages_fts, rowid, content)
    VALUES ('delete', old.rowid, old.content);
  INSERT INTO messages_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE VIRTUAL TABLE memories_fts USING fts5(
  content, subject,
  content='memories',
  content_rowid='rowid',
  tokenize='unicode61 remove_diacritics 2'
);
-- equivalent ai/ad/au triggers for memories
```

Query shape:

```sql
SELECT m.* FROM messages_fts f
JOIN messages m ON m.rowid = f.rowid
WHERE messages_fts MATCH ?
ORDER BY bm25(messages_fts)
LIMIT 20;
```

The query string is sanitized (quote each term, strip FTS operators) before
matching; an invalid query must not throw into the UI.

`conversation_search` is scoped to the current thread by default; "search all"
is an explicit second mode.

## 5. Migrations

- `PRAGMA user_version` is the schema version; `schema_migrations` is the audit log.
- Migrations are append-only Rust constants:

```rust
struct Migration { version: u32, name: &'static str, sql: &'static str }
const MIGRATIONS: &[Migration] = &[Migration { version: 1, name: "initial", sql: include_str!("migrations/001_initial.sql") }];
```

- Apply inside a transaction, set `user_version`, insert the audit row.
- A failed migration rolls back and refuses to open the app with an actionable
  message; it never starts from an unknown schema.
- Never edit a shipped migration. Add `002_…`.
- Tests: open a v1 DB, run all migrations, assert `user_version` and a smoke query.
- Downgrade is unsupported. A DB newer than the binary is refused with
  `storage_schema_too_new`.

## 6. Transactions and write paths

| Operation | Transaction |
| --- | --- |
| Start a run | insert user message + run + assistant placeholder + run.created (one tx) |
| Append event | `UPDATE runs SET last_seq = ?` + insert event (one tx) |
| Checkpoint stream | update `messages.content` + insert `message.checkpoint` (throttled) |
| Tool call start | insert tool_call + event |
| Approval decision | compare-and-set approval + event |
| Finish run | update message + run + terminal event |
| Delete bot | cascade + delete avatar/attachment files after commit |
| Delete all data | close DB, delete file + WAL/SHM + attachments, recreate |

## 7. Export, backup, restore

- **Export (v1)**: a JSON document per entity plus the SQLite file, written to a
  user-chosen location through the dialog plugin. Attachments are copied into a
  folder. The export excludes provider keys by construction (they are not in the
  DB).
- **Backup**: `PRAGMA wal_checkpoint(TRUNCATE)` then `VACUUM INTO ?` produces a
  consistent single-file copy. Never copy the live DB + WAL manually.
- **Restore**: not in v1. A future restore must validate `user_version`, run
  forward migrations, and re-encrypt with the device key.
- **OS cloud backup**: exclude the DB and attachments from iCloud/Google backup by
  default (`NSURLIsExcludedFromBackupKey`, `android:allowBackup="false"`). The user
  can export deliberately. This prevents private conversations from silently
  leaving the device.
- **Share/send**: sharing a transcript is an explicit action; it must render the
  same text the user sees, and must not include hidden memory or system prompts.

## 8. Erasure

Deleting a bot, group, thread or "all data":

1. Delete rows in one transaction (FK cascade).
2. Delete attachment files and avatar images **after** the commit.
3. `PRAGMA secure_delete=ON` overwrites freed pages where the OS/filesystem
   honours it.
4. Run `VACUUM` on "delete all data" to remove residual pages.
5. Explain the limit honestly: on flash storage with wear levelling and OS
   snapshots, no app can guarantee physical erasure. Deleting the app removes the
   sandbox but not provider-side copies (the provider already received content).

Memory deletion is a single row delete plus FTS cleanup; the UI offers "forget this
memory" and "forget all memories for this bot".

## 9. Encryption

Preferred:

```
PRAGMA key = "x'<64 hex chars>'";   -- 32 random bytes from the OS keychain
PRAGMA cipher_memory_security = ON;
```

- The key is generated on first launch, stored in Keychain/Keystore, and never
  logged.
- A failed decrypt (key lost, restore to a new device) must offer "start fresh"
  and explain that the old DB is unreadable. Never fall back to plaintext silently.
- Key rotation: `PRAGMA rekey` inside a transaction after re-encrypting; a crash
  mid-rekey is recovered from a backup copy.

Fallback if SQLCipher does not build on a target:

- Ship plaintext SQLite inside the app sandbox, relying on iOS Data Protection and
  Android's per-app UID + file-based encryption.
- State this in Settings › Privacy and in `security-model.md`.
- Do not call it "encrypted at rest by the app".

## 10. What is deliberately not migrated

| Desktop store | Size | Why not |
| --- | ---: | --- |
| `jdds.db` | ~361 MB | Market-data vault; no market tools on mobile |
| `agent-memory.db` | ~1.6 GB | Run traces/memory for the Python harness; no compatible schema |
| `eclipse-memory.db` | — | Evidence graph, skills, review workflow; only explicit memories are portable |
| `BotState` documents | ≤ 8 MiB each | A server mirror for browser loss; SQLite is the source now |
| `localStorage` bot stores | — | Replaced by SQLite; a one-time import is not planned |
| Session attachment folders | — | Server filesystem; mobile attachments are copied into the sandbox |

## 11. Size expectations

| Data | Estimate |
| --- | --- |
| 1,000 messages (1 KB avg) + FTS | ~2 MB |
| 10,000 messages | ~20 MB |
| 1,000 memories | ~1 MB |
| Run events (50 per run, 500 runs) | ~10 MB |
| Attachments | user-controlled; cap per file 25 MB, warn above 10 MB |
| **Typical active install** | **30–80 MB** |

The app warns at 500 MB and offers per-thread cleanup. It never silently deletes
history.

## 12. Data invariants enforced by tests

1. `messages.thread_seq` is gap-free per thread under concurrent appends.
2. `runs.last_seq` equals `MAX(run_events.seq)`.
3. A `run_events` insert with a duplicate `seq` fails, never overwrites.
4. `threads.kind` XOR constraint holds.
5. Deleting a bot cascades messages, runs, events, tools, approvals, memories and
   schedules, and leaves no orphan attachment rows.
6. FTS insert/update/delete triggers keep `messages_fts` in sync.
7. `json_valid` rejects malformed JSON at the boundary.
8. A schema-newer DB is refused, not opened read-write.
