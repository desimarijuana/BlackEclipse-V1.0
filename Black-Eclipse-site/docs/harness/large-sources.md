---
title: Large-Corpus Sources (open anything in place)
status: Current
last-verified: 2026-11-10
---

# Large-Corpus Sources

**Code:** `python/harness/sources/`
**Tools:** `source_roots`, `source_list`, `source_open`, `source_read`,
`source_lines`, `source_search`, `source_sql`, `source_index`, `source_stats`
(registered by `sources/tools.py:register_source_tools`)
**Routes:** `python/harness/routers/sources.py` → `/sources/*`, proxied by
`src/app/api/sources/[...path]/route.ts`
**UI:** Sources tab (`src/components/screens/sources/sources-screen.tsx`)
**Config:** `sources/config.py` (`HARNESS_SOURCES_*` env, `ECLIPSE_SOURCES_DIR`,
`ECLIPSE_SOURCES_DB_PATH`)
**ADR:** `docs/DECISIONS.md` ADR-077

## Why this exists

The chat attachment path reads a file into memory, base64-encodes it and sends it
as JSON, with an 8 MB per-file cap. That is correct for a note and impossible for
a 4 TB drive. This layer is the other primitive: **the bytes never move**. A
source root is a folder or drive catalogued in place; opening a file returns a
bounded card; answers come from metadata, an optional text index, DuckDB or a
bounded scan.

The design rule is one sentence: *open instantly, index lazily, query with a
budget, and never claim more coverage than was measured.*

## Invariants

1. **No copy, no upload.** Roots store a path. Reads go to the original bytes.
2. **Bounded everything.** Card ≤ ~5 KB of sample; read windows ≤ 1 MiB; scan
   bytes/time/results are capped; DuckDB has a memory limit + spill directory.
3. **Constant context.** The model receives a source card and tool results, never
   file content. A 2 MB file and a 4 TB file cost the same prompt space.
4. **Honest partials.** A result carries `truncated`, `warnings`, `scannedFiles`,
   `scannedBytes`, `elapsedMs` and the chosen plan. "Indexed" is per file.
5. **Read-only.** Agent tools cannot add a root, write a file or mutate SQL.
   Adding a root is an operator route; SQL must be one SELECT/WITH statement.
6. **No fabricated coverage.** An unsupported format is `opaque` with a preview,
   not a guessed parse. Missing OCR/vision/embeddings are `UNAVAILABLE`.

## Layout

```
python/harness/sources/
  config.py     budgets + env, hard ceilings (config may only lower)
  errors.py     stable SourceError codes
  contracts.py  RootRecord, FileRecord, SourceCard, Hit, SearchResult, SqlResult
  catalog.py    SQLite catalog + FTS5 chunk index + optional vector table
  scanner.py    incremental resumable directory walk (extension-only classify)
  probe.py      magic bytes, head/tail, schema/pages/image size/archive entries
  extract.py    streaming text chunks; PDF/Office/archive/DB text; table samples
  indexer.py    bounded per-file indexing (pay once per touched region)
  semantic.py   opt-in embeddings over a filtered subset (never the corpus)
  query.py      read-only DuckDB, statement allowlist, describe + run
  rawscan.py    bounded parallel literal/regex scan with byte/time budgets
  planner.py    candidate set → engine choice → fusion → honest coverage
  service.py    the one entry point (roots, scan, open, read, search, sql, index)
  tools.py      the source_* agent tools
  bootstrap.py  boot wiring on the ONE registry
```

Derived state lives under `<app>/.black-eclipse/sources/` (`sources.db`, `tmp/`).
It is disposable; deleting it never touches the user's files.

## Catalog

One row per file: `rootId, relpath, name, ext, size, mtime, inode, rootPath,
magic, klass, scannedAt, seenEpoch, indexedAt, chunkCount`.

- `Root` carries the path, scan epoch, file count and total bytes.
- The scanner increments `scanEpoch`, upserts changed rows in batches and, only
  after a *complete* walk, deletes rows whose `seenEpoch` is stale. A truncated
  walk is `PARTIAL` and deletes nothing.
- One writer (scanner) + WAL readers; a scan never blocks a search.
- Classify during the scan by extension only (no file opens). Unknown extensions
  are classified at probe time from magic bytes / printable ratio.

## Probe (open anything)

Read ≤ 4 KB head + ≤ 1 KB tail. Identify by magic bytes first (`%PDF`, `PAR1`,
`PK\x03\x04`, `SQLite format 3`, image/audio/video/archive signatures), extension
second. The card contains whatever is cheap:

| Class | Card contents |
|---|---|
| table | DuckDB `DESCRIBE` (Parquet footer or bounded CSV sample), optional row hint, delimiter |
| document | PDF page count (pypdf), Office/EPUB entry count; no body parse |
| text/code | head + tail preview, truncated flag |
| image | width/height from the header |
| archive/database | entry count / "read-only SQL" note |
| binary/unknown | printable strings preview, `opaque` warning |

## Read windows

- `read_window(offset, length)` seeks and reads ≤ 1 MiB; text is decoded, binary
  is returned as base64 with the class named. `eof`/`truncated` are explicit.
- `read_lines(start, count)` streams lines with a 5,000-line and 10 s cap.
- Nothing is cached as a full-file copy.

## Index (pay once per region)

`extract_chunks` streams text in 256 KB blocks with an incremental decoder,
splitting near paragraph/sentence/space boundaries (`chunk_chars`, overlap).
Each file's chunks replace its previous chunks in a standalone FTS5 table (no
triggers, no second store). Per-file and total chunk ceilings stop a pathologically
large file from becoming the index.

Other formats are bounded samples, not full parses:

- CSV/TSV: header + up to 2,000 rows as text (SQL is the precise path).
- Parquet: up to 200 rows through DuckDB.
- XLSX: up to 1,000 rows per sheet via openpyxl (read-only).
- PDF: page text up to `index_pdf_max_pages`; scanned PDFs yield nothing and are
  labelled, never OCR'd implicitly.
- DOCX/PPTX/EPUB/ODF: text extracted from the relevant zip parts, each part capped.
- Archives: entry listing. SQLite: object/schema listing.
- Media/opaque: metadata only.

Adaptive indexing: when a search falls back to `scan` and returns hits, the
service indexes up to 20 of those files in a background thread, so the *next*
query is an FTS lookup. This is the "first touch pays, second touch is instant"
behaviour.

## Query routing

`plan_and_search` first derives the candidate set from the catalog (root, class,
path prefix, name, size, mtime), then picks:

| Mode | When | Engine |
|---|---|---|
| `metadata` | empty/filename/extension query, or a table query with aggregates | catalog SQL |
| `text` | ordinary content query | FTS5 BM25 + metadata + scan of **unindexed** candidates only |
| `raw` | explicit, regex, or freshness matters | bounded parallel scan |
| `similar` | explicit `similar` and a provider is configured | cosine over vectors of the filtered subset |

Fusion dedupes by `(root, relpath, offset)` and keeps the best score. Every result
reports the plan and its coverage. A budget hit is `truncated: true` with a
warning such as "stopped at the 512 MB scan budget".

SQL is not auto-generated from prose. `source_sql` accepts one statement, binds
the file(s) as view `t`, refuses `read_*`/`glob`/`attach`/DDL/DML/comments/multiple
statements, and caps rows. The engine is DuckDB with `memory_limit`, `threads` and
`temp_directory` set, so it spills instead of loading.

## Semantic index (opt-in)

`HARNESS_SOURCES_SEMANTIC=1` enables chunk embedding through the existing
`search.embeddings.EmbeddingService` (providers, batching, cache, honest
availability). Vectors are stored per file/ordinal in the catalog and scored with
numpy over at most 50k candidate vectors. It is a rerank layer over a filtered
subset, not a whole-corpus index — a terabyte of text is not embeddable, and the
layer says so when no provider is configured.

## Security

- Paths are root-confined: `resolve` rejects `..`, absolute escapes and symlink
  escapes; a path outside every root is `ROOT_UNKNOWN`.
- Roots are added only through the operator-gated route. Agent tools are read-only.
- SQL: one statement, allowlisted starts, denied keywords/functions, no comments,
  no filesystem/network readers, bounded rows.
- Retrieved content is wrapped as untrusted DATA (`UNTRUSTED_SOURCE_CONTENT`).
- Scanner skips `.git`, `node_modules`, `$RECYCLE.BIN`, `System Volume
  Information`, virtualenvs and the app's own `.black-eclipse`; no symlink
  following by default.

## Configuration (lower-only)

`HARNESS_SOURCES_MAX_FILES`, `HARNESS_SOURCES_MAX_DEPTH`,
`HARNESS_SOURCES_INDEX_MAX_BYTES`, `HARNESS_SOURCES_MAX_CHUNKS_FILE`,
`HARNESS_SOURCES_MAX_CHUNKS`, `HARNESS_SOURCES_CHUNK_CHARS`,
`HARNESS_SOURCES_CHUNK_OVERLAP`, `HARNESS_SOURCES_PDF_PAGES`,
`HARNESS_SOURCES_WINDOW_BYTES`, `HARNESS_SOURCES_MAX_READ_BYTES`,
`HARNESS_SOURCES_MAX_LINES`, `HARNESS_SOURCES_SCAN_MAX_BYTES`,
`HARNESS_SOURCES_SCAN_MAX_FILE_BYTES`, `HARNESS_SOURCES_SCAN_TIMEOUT`,
`HARNESS_SOURCES_SCAN_WORKERS`, `HARNESS_SOURCES_QUERY_TIMEOUT`,
`HARNESS_SOURCES_QUERY_MEMORY`, `HARNESS_SOURCES_QUERY_ROWS`,
`HARNESS_SOURCES_MAX_RESULTS`, `HARNESS_SOURCES_SEMANTIC`,
`HARNESS_SOURCES_MAX_VECTORS`, `HARNESS_SOURCES_BATCH`.

Hard ceilings live in `config.py` and cannot be raised by configuration.

## Known limitations (deliberate)

- No copying or uploading: a corpus on another machine is not a source root.
- No whole-corpus embedding and no automatic OCR of scanned PDFs.
- No media transcription/vision; media is metadata only until a separate tool is
  used on it.
- Spreadsheet files are not queryable as DuckDB tables (Excel needs a CSV/Parquet
  export; the document tools handle workbooks).
- Legacy `.doc`/`.xls`/`.ppt` need LibreOffice, as in Document Intelligence.
- A cold terabyte text corpus is bounded by disk throughput: the first scan is
  capped and labelled, and indexing the touched region is what makes the next
  query fast.

## Tests

`python/tests/test_sources_core.py` (catalog/scan/incremental/stale, root
confinement, probe by magic, streaming chunk budgets, read windows/adoption) and
`python/tests/test_sources_query_tools.py` (DuckDB exactness + allowlist, FTS
routing, metadata wildcard, raw scan coverage/line numbers/byte budget,
filter confinement, semantic availability + fake-vector scoring, tool registry
and untrusted wrapping).
