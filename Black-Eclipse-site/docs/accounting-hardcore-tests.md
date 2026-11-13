---
title: Accounting hardcore chat tests
status: Current
last-verified: 2026-11-13
---

# Accounting hardcore chat tests (two books)

Paste these into Eclipse chat. Each prompt targets one of the two books of
record and can be graded from the answer alone:

- **General Ledger** — a company's double-entry books, used by the `bookkeeper`
  preset (`ledger_*` tools). See `docs/ledger.md`.
- **Portfolio Accounting Engine** — a securities book (lots, cost basis,
  realized P&L), used by the `portfolio_*` tools. See
  `docs/portfolio-accounting.md`.

Every prompt has **pass rules**; the highest-risk behaviours also have an
**offline twin** in `python/tests/test_accounting_hardcore.py`: the prompt states
what the bookkeeper must do, the test pins what the engine must produce. Run the
suite without a model:

```bash
cd Black-Eclipse-site/python
python -m pytest tests/test_accounting_hardcore.py -q
```

If a chat answer passes while the offline twin fails (or vice versa), the
failure is real — grade against the pass rules, not against preferred wording.

---

## A. General Ledger (company books)

### A1. Month-end close from raw events

> Open a book for a trading company in USD. Record: 100,000 share capital into
> the bank; inventory 9,000 on credit; a 24,000 credit sale; cost of sales
> 9,000; 2,000 rent paid; a 12,000 customer receipt; 15,000 equipment paid
> from the bank; a 30,000 bank loan. Produce the trial balance, balance sheet,
> income statement and cash flow, reconcile closing cash to the cash accounts,
> then run the January close.

**Pass:** every statement `balanced`; net income 13,000; financing 130,000,
investing −15,000, operating 10,000; closing cash equals the cash-account
trial balance; close is `READY` then `CLOSED`; no plug or cached total.

### A2. A correction is a reversal, never an edit

> The 800 utilities accrual posted on 31 January was wrong. Correct it in
> February without changing January's numbers.

**Pass:** a reversing entry dated in February, linked both ways; January still
shows the 800 expense; February shows −800; the original lines are unchanged;
trial balance stays balanced.

### A3. Bank import with a suspense row

> Import this bank CSV (a coffee purchase the rules do not recognise and a
> customer receipt). Preview first, commit, then try to close the month.

**Pass:** preview writes nothing; the unrecognised row posts to `9999 Suspense`
(never a guessed account); the close is refused (`PERIOD_NOT_READY`) while
suspense is non-zero; the trial balance is balanced throughout.

### A4. Foreign-currency purchase

> Buy 1,000 EUR of equipment from a EUR bank account at 1.10 USD/EUR. Then try
> the same entry with no rate.

**Pass:** the first posts at 1,100 USD base, with the transaction currency and
rate retained on the line; the second is refused `MISSING_FX`; no rate is
invented and no line is silently converted at 1.0.

### A5. Inclusive VAT, partial payment, aging

> Invoice a customer 3 × 10.00 including 20% VAT, due in 30 days. Take a 10.00
> partial payment next month. Show AR aging at month-end before the payment and
> after it, and prove aging reconciles to the control account.

**Pass:** subtotal 25.00 + tax 5.00 = 30.00; aging is 30.00 before the payment
and 20.00 after; both reconcile to `1100 Accounts receivable`; an overpayment is
refused `DOCUMENT_OVERPAID`.

### A6. Accrual and its automatic reversal

> Accrue 1,200 of audit fees in March and reverse it on 1 April. Show both
> periods.

**Pass:** March expense +1,200 and April −1,200; the pair nets to zero across the
range but never hides the March accrual; a repeated reference posts once.

### A7. Depreciation that sums exactly

> Buy a 10,000 machine with 1,000 salvage over 12 months, straight line. Post
> every period.

**Pass:** Σ posted depreciation = 9,000 exactly (the last period takes the
rounding remainder); no period is posted twice; a closed period stops the run at
the first unpostable entry.

### A8. 80%-owned subsidiary consolidation

> The parent invoiced the sub 100. Consolidate the group at 80% ownership.

**Pass:** proportionate inclusion; only the matched 80 of the intercompany pair
is eliminated; the remaining 20 stays visible plus an
`INTERCOMPANY_OUT_OF_BALANCE` warning; the consolidated balance sheet balances;
nothing is force-balanced.

### A9. Export that is not a filing

> Export the journal CSV and XBRL. Also produce SAF-T.

**Pass:** CSV survives commas/quotes/newlines in a memo; XBRL is well-formed and
says in the file that it is not a filing (no taxonomy linkbase); SAF-T is refused
with a reason rather than approximated.

### A10. Range and movement

> Show the February trial balance with January as opening, then the February
> income statement only.

**Pass:** opening + movement = closing per account; movement debits = movement
credits; the income statement excludes January; closing cash still ties to the
cash-account closing balances.

---

## B. Portfolio Accounting Engine (securities book)

### B1. Method comparison on identical facts

> I bought 10 XYZ at 100, then 10 at 200, then sold 10 at 300. Show realized
> cost basis and P&L under FIFO, LIFO, average cost, HIFO and specific-lot.

**Pass:** FIFO 1,000/2,000; LIFO 2,000/1,000; average 1,500/1,500; HIFO
2,000/1,000; specific-lot names the actual lot; fees raise the acquisition basis
and reduce sale proceeds.

### B2. A net-only broker import

> Import a sell of 10 shares with only a settled net amount of 1,500 — no price
> and no gross. What is realized P&L if basis was 1,000? What is the cash
> balance after a 10,000 deposit, a 1,000 net buy and this sell?

**Pass:** proceeds 1,500, realized +500 (not −1,000); cash 10,500; no fabricated
total loss.

### B3. Split with a sale before it

> Buy 10 at 100, sell 4 at 150, then a 2:1 split. Show quantity, basis and
> `acquired − disposed = remaining`.

**Pass:** remaining 12, basis 1,000, realized 200; acquired 20 and disposed 8 in
post-split share units; the invariant holds.

### B4. Specific-lot designation by id

> Show my open lots. Then sell 10 using the cheapest lot id you just returned.

**Pass:** the lot id survives a re-read (stable ids); the sale consumes exactly
that lot; an unknown or malformed lot id is refused (`LOT_MISMATCH` /
`INVALID_TRANSACTION`) rather than silently becoming FIFO; a designated lot on a
non-SPECIFIC_ID book is refused, never ignored.

### B5. Average cost holding period

> Under average cost, I bought 10 in 2020 and 10 in 2024, then sold 10 in 2026.
> What is the holding period of the shares sold?

**Pass:** basis is pooled at the average, but the match reports the 2020
acquisition date and a >5-year holding period — not a fabricated 0-day
short-term disposal.

### B6. Oversell must not corrupt the book

> Sell 20 when I only hold 10.

**Pass:** refused (`INSUFFICIENT_POSITION`); nothing is written; even the
engine's diagnostic run reports 10 disposed, 3,000 proceeds — never 20 units or
6,000 inflated proceeds.

### B7. Corporate actions that conserve basis

> Apply a 2:1 split, a spin-off, a stock-for-stock merger with cash boot, and a
> return of capital larger than basis.

**Pass:** split scales quantity and inverse-scales unit cost; spin-off conserves
basis across parent + child; merger carries basis and treats the cash boot as a
real partial disposal; return of capital reduces basis and books only the excess
as a taxable realized gain; every step appends ledger entries and an audit event.

### B8. Crypto lifecycle

> Buy 10 ETH, stake it, unstake it, record a 2 ETH staking reward, bridge 3 ETH
> to another chain, swap 2 ETH for USDC, then get 1 ETH slashed.

**Pass:** stake/unstake change custody only (no quantity or basis effect);
reward acquires at fair value; bridge carries basis with no gain; swap is a
taxable disposal plus an acquisition at fair value; slashing is a disposal at
zero proceeds realizing a loss equal to consumed basis.

### B9. Valuation honesty

> Value the fund with a missing price and with a missing FX rate.

**Pass:** the missing symbols appear in `missingPrices`/`missingFX`; data quality
is `PARTIAL`/`UNAVAILABLE`; market value is null, never zero; allocation and
exposure say which positions are unpriced.

### B10. Tax-lot audit

> Rebuild every lot from the ledger and prove the invariants.

**Pass:** `acquired − disposed = remaining`; `remaining basis + realized basis =
acquisition cost ± basis adjustments`; no negative lots; shorts refused, not
miscalculated; a fresh recompute equals the materialized cache.

---

## Grading checklist

- [ ] Every statement/posting balances exactly; differences are named, never plugged
- [ ] Corrections are reversals or adjustments — history is never rewritten
- [ ] Missing price/FX/rate is `UNAVAILABLE`/`MISSING_FX`, never zero or 1.0
- [ ] Suspense is used and blocks a close; no account is guessed
- [ ] Tax is configured data, not a bundled rate
- [ ] Lot ids are stable and a designated lot is honoured (or refused)
- [ ] `acquired − disposed = remaining`, including after splits
- [ ] Proceeds come from the settled amount when that is all the import has
- [ ] Oversell is refused and cannot inflate proceeds or move the book
- [ ] Consolidation eliminates only the matched amount and reports the remainder
- [ ] Exports are text, not filings; unsupported formats are refused
- [ ] Chat only — no separate UI is required
