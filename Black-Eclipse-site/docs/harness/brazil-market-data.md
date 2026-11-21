---
title: Brazilian Market Data — B3, CVM, BCB and Tesouro
status: Current
last-verified: 2026-11-20
---

# Brazilian Market Data — B3, CVM, BCB and Tesouro

Four publishers, four formats, one module family (`python/harness/br_data/`). All
of them **parse only** — no module here downloads on import, caches, or invents a
missing field. `datasets.list_datasets()` is the single list of what exists:

| id | Shape | Source | Transport |
|---|---|---|---|
| `cotahist` | one row per paper per day | B3 | fixed-width zip |
| `cvm_inf_diario` | one row per fund per day | CVM | zip of `;`-CSV |
| `bcb_sgs` | one series' observations | BCB | JSON |
| `tesouro_direto_preco_taxa` | one row per bond per day | Tesouro Transparente | `;`-CSV |

`parse_dataset(name, payload, code=…)` routes bytes to the right parser, so a
caller does not import four modules to answer "parse this".

B3 publishes its daily quotes as fixed-width text (`COTAHIST_A{YYYY}.ZIP`,
`COTAHIST_D{DDMMYYYY}.ZIP`): **245 characters per record**, Latin-1, one record per
line. `python/harness/br_data/cotahist.py` parses that format and nothing else —
it does not download, does not cache, and does not invent a missing field.

## The layout is data, not magic numbers

`COLUMNS` holds every field as B3 publishes it, **1-based inclusive**, converted
to a 0-based slice in exactly one place (`_field`). A reader can check any
position against B3's layout without reading the parser body.

| Field | 1-based positions | Note |
|---|---|---|
| `trade_date` | 3–10 | `YYYYMMDD`; all-zeros means "none" and becomes `""` |
| `ticker` | 13–24 | e.g. `PETR4` |
| `market_type` | 25–27 | 10 cash, 20 odd lot, 70/80 options |
| `open/high/low/average/close` | 57–121 | **two implied decimals** |
| `best_bid` / `best_ask` | 122–147 | |
| `trades` / `quantity` / `volume` | 148–188 | |
| `exercise_price` / `expiration_date` | 189–210 | options |
| `factor` | 211–217 | `FATCOT`: the quote factor |
| `isin` | 231–242 | |

## Prices: two implied decimals, and the lot factor

`000000001050` is **10.50**, not 1050. The parser divides by 100 once, so no
downstream consumer repeats the conversion.

A record with `FATCOT > 1` is quoted **per lot**. The row keeps the raw quoted
value (`close`) *and* exposes `unitPrice.close` with the factor divided out, so a
caller never has to guess which number it is holding.

## Failure is named, never silent

| Code | When |
|---|---|
| `BAD_LENGTH` | a quote record is not 245 characters |
| `BAD_PRICE` | a price field is not an integer of implied-2-decimals |
| `BAD_DATE` | a non-zero date is not `YYYYMMDD` |

`parse_records` prefixes the line number. Header (`00`) and trailer (`99`)
records are dropped deliberately; a *skipped* quote row would be invisible data
loss, so it raises instead.

## Sync: archive → SQLite, idempotent

`br_data/store.py` + `br_data/sync.py` turn a local archive into rows:

| Piece | Behaviour |
|---|---|
| `BrStore(path)` | creates the file + schema; `b3_quotes` keyed by `(trade_date, ticker)` |
| `store.upsert(rows)` | `INSERT … ON CONFLICT DO UPDATE`; returns `(inserted, updated, skipped)` |
| `read_archive(path)` | opens the zip, decodes Latin-1, parses records (no store required) |
| `sync_archive(path, store)` | parse → upsert → record a run; re-raises on failure |
| `store.status()` | row count, first/last trade date, and the last run's counts + status |

**Idempotency is the contract**: syncing the same archive twice leaves the row
count unchanged and reports the second pass as `updated`, not `inserted`. A row
without a `trade_date` or `ticker` cannot be keyed and is counted as `skipped`
rather than written under an empty key.

**A failed run is recorded, not swallowed.** `sync_runs` gets the status and the
error (including the `COTAHIST` code, e.g. `BAD_ARCHIVE`), and the exception is
re-raised so the caller cannot believe a stale store is current.

The sync is a pure function of a **local file** — it never downloads. That keeps
it testable offline; how the archive arrives is the caller's decision.

## Download → sync, with an injectable transport

`br_data/download.py` is the only place that touches the network, and it is thin
on purpose:

```
download_archive(url, dest, opener=…)  →  writes <name>.part, proves it is a zip,
                                          renames atomically, returns the path
sync_from_url(url, store, dest, …)     →  download_archive → sync_archive
```

- **Injected `opener`** (`(url, timeout) -> bytes`). Tests run against a recorded
  fixture and never reach B3; a caller can supply a retrying/backpressured
  transport without this module growing a second HTTP stack. The default is
  stdlib `urllib`, so installing Eclipse never pulls an SDK for a dataset most
  users will not sync.
- **Prove it is a zip before it becomes the file.** A truncated or HTML "we are
  down" response is refused with `NOT_ZIP`, not written for a later sync to
  choke on. `TOO_LARGE` caps the payload before it fills the disk.
- **Named failures**: `HTTP_<status>`, `UNREACHABLE`, `TIMEOUT`, `NOT_ZIP`,
  `BAD_PAYLOAD`, `TOO_LARGE`.
- A failed download records **no** sync run — there is nothing to record, and
  inventing one would hide that the store was never touched.

## CVM, BCB and Tesouro — the three later datasets

`csvtext.py` holds the two things that break naive Brazilian CSV parsers, once:

- **decimal comma** (`5,4321`), often with a thousands dot (`1.234.567,89`). The
  separator is chosen by which one appears **last**, so an English `1234.56`
  still parses.
- **two date orders** — `dd/mm/yyyy` (BCB, Tesouro) and `yyyy-mm-dd` (CVM) — plus
  encodings that differ (CVM in Latin-1, Tesouro in UTF-8 with a BOM), handled by
  `decode()` trying UTF-8 first and falling back losslessly.

A **blank cell is `None`, never `0.0`**, everywhere. A missing net asset value and
a zero one are different facts; so is an unreported Selic rate.

| Dataset | Kept verbatim | Derived (and labelled) | Refused |
|---|---|---|---|
| `cvm_inf_diario` | quota value, net assets, contributions, redemptions, holders | `netFlow = contributions − redemptions` (in `derived`) | header-only file (`NO_ROWS`), empty file (`EMPTY`) |
| `bcb_sgs` | every observation as ISO date + float | — | an error object (`BCB_ERROR`), non-JSON (`BAD_JSON`) |
| `tesouro_direto_preco_taxa` | buy/sell yield **as published (% per year)**, buy/sell/base unit price | nothing | impossible date (`BAD_DATE`) |

Two semantics worth stating because they are the usual mistakes:

- **CVM `VL_QUOTA` is the quota value, not the fund's total.** `VL_PATRIM_LIQ` is
  net assets — the closest thing to AUM in that file.
- **Tesouro yields are not decimals.** 12.5% stays `12.5`; converting to `0.125`
  would silently change what the number means, so `yieldUnit` says `"% per year"`.
  A price of `0,00` is real (that side was not offered) and is kept; a blank is
  `None`. The publisher's own `PU … Mania` typo for *Manhã* is accepted alongside
  the corrected spelling.

**BCB does not invent a series name.** The response carries a code and values,
never a title, so `SERIES` maps only documented codes and an unmapped one returns
`label: None, known: False`. A blank observation is **skipped and counted** in
`skipped` — a shorter series must not read as a complete one.

## Store: one table per key, idempotent by construction

`dataset_store.py` holds the three tables, because their natural keys genuinely
differ — a fund is `(cnpj, date)`, a series is `(series, date)`, a bond is
`(bond, date)`. One shared "datasets" table would lose exactly the key that makes a
re-sync a no-op.

| Table | Key | Written by |
|---|---|---|
| `cvm_funds` | `(cnpj, trade_date)` | `sync_dataset("cvm_inf_diario", …)` |
| `bcb_series` | `(series, trade_date)` | `sync_dataset("bcb_sgs", …, code=…)` |
| `tesouro_bonds` | `(bond, trade_date)` | `sync_dataset("tesouro_direto_preco_taxa", …)` |

`BrStore.upsert_dataset(name, rows)` / `dataset_rows(name, key=…)` /
`dataset_counts()` are the whole surface; `store.status()` now reports the three
counts alongside the B3 ones. `sync_dataset` records its run in `sync_runs` exactly
like the archive path, labels a BCB run with its series (`bcb_sgs:11`), records a
failure with its code and re-raises, and reports the parser's own `skipped` count.

Three rules carried over deliberately:

- **A row missing part of its key is skipped and counted**, never written under an
  empty key.
- **The derived CVM `netFlow` is not stored.** It is `contributions − redemptions`
  over stored columns; storing it would let the two disagree.
- **A blank price stays `NULL`.** `0.0` means the publisher reported zero.

## Scheduled registration

`schedule.py` answers "what is due?" from the store, never from a prompt:

| Piece | Behaviour |
|---|---|
| `SCHEDULES` | every dataset, `every_hours=24` (B3 publishes after the close; the CVM monthly file is appended daily) |
| `due_datasets(store, now)` | a label is due when it has **no OK run inside its cadence**. A **failed** run does not count as fresh — a failure is a reason to retry, not evidence of freshness |
| `last_success(store, label)` | the newest `status='ok'` run for that label |
| `sync_due(...)` | fetches each due label, records one outcome per dataset, and **continues past a failure** so one dead publisher cannot block the others |
| `sync_loop(...)` | wakes hourly and calls `sync_due`; a failing pass is logged and survived |
| `start_br_sync(service)` | registers the loop from `boot.py`, **only when `BE_BR_SYNC=1`** |

Two decisions worth stating:

- **Off by default.** A boot that silently downloads tens of megabytes from four
  publishers is not something to do to an operator uninvited; the switch is an env
  var, and the test asserts that unset/`0` means no task is created.
- **Stable labels.** Runs are recorded under the dataset id (`bcb_sgs:432` for a
  series), not the publisher's file name — CVM's zip is named per month, so a
  filename label would make every month look like a first run.

`fetch.py` is the per-dataset fetcher (zip, zip-of-CSV, JSON, CSV) with the same
injected opener as `download.py`, so the whole scheduler is testable offline.

## Not built yet

Routing the synced Brazilian instruments into the market gateway, and a UI
surface for the sync outcomes (the loop logs them; `store.status()` carries the
counts).
