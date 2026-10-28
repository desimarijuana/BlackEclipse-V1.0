# Legacy Advisory Debt

## Read-only report

`GET /advisory/legacy` returns each legacy-unscored recommendation and why it
cannot be scored:

- `no_horizon` — no stated scoring deadline;
- `no_entry_price` — no recorded entry price;
- `no_symbol` — no symbol to mark;
- `no_method` — no method/basis class.

`status` is `unscorable` or `scorable_if_backfilled`. The report never changes a
row and never implies it was audited.

## Provenance-bound backfill

`POST /advisory/backfill-entry-prices` (operator-gated, `dryRun: true` by
default) only acts when:

1. the row has a stated horizon (not `unscored`);
2. it has at least one symbol;
3. no entry price already exists;
4. the market gateway returns a real historical bar at/after `createdAt`.

It stores three basis rows: `entry_price`, `entry_price_source`,
`entry_price_asof`, with a SHA-256 provenance hash. A missing bar is a named
skip (`no_historical_bar`), never a guessed price. Existing entry prices are
never overwritten.

## Live state

14 legacy rows are marked `legacyUnscored`. All 14 have no horizon and no entry
price; many symbols are non-tradable labels (`API`, `UTC`, `COT`, `CFTC`,
`SMA`, `EMA`). They are reported as **unscorable**; the backfill dry-run skips
them with `no_horizon`. No score was invented.

## Tests

- `test_legacy_report_explains_unscorable_rows`
- `test_backfill_is_dry_run_first_and_stores_provenance`
- `test_backfill_skips_when_no_historical_bar`
