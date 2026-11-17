---
title: Alternative-intelligence signals (the intel lane)
status: Current
last-verified: 2026-11-17
---

# Alternative-intelligence signals

**The question this answers:** *what did a public record measure that the price
may not have absorbed yet — and can I re-derive that measurement myself?*

This is the "satellite-shadow / parking-lot" idea, built on the part of it that
is real and free. The commercial version of that trade is **not** an AI looking
at a photo; it is a calibrated measurement against a licensed 30–50 cm image,
validated against ground truth. What ships here is the same *shape* — acquire →
measure deterministically → build a time series → score the divergence — over
public records that need no key, no licence and no scraped tile.

## Why not imagery first

Free satellite imagery cannot carry the headline claims, and pretending
otherwise would be fabricated data:

| Source | Resolution | Revisit | Can it do the trick? |
|---|---|---|---|
| Sentinel-2 L2A | 10 m | ~5 days | Tank *caps* yes; **cars no** (a car is ~4 m); floating-roof shadow → fill level no |
| Sentinel-1 SAR | ~10 m | ~6–12 days | Vessel detection (>20 m), anchorage congestion — genuinely good |
| VIIRS nightlights | 500–750 m | daily | Site-level activity proxy only |
| Planet / Maxar | 0.3–0.5 m | tasking | Tank shadow levels, parking occupancy — **paid licence** |

So the lane starts where free data is *strong* (filings, attention, public
records) and leaves the paid imagery lane as a future monitor plugged into the
same engine. Tanker "how much oil is aboard" is in any case normally read off
AIS static `draught`, not shadows.

## The four signals

| id | question | source | unit |
|---|---|---|---|
| `insider_conviction` | Are insiders spending their own money, or only selling on autopilot? | SEC EDGAR Form 4 | USD net |
| `activist_stake` | Has a holder crossed 5% with declared intent to influence? | SEC EDGAR Schedule 13D | count |
| `filing_heat` | Is this company filing far more than its own normal? | SEC EDGAR submissions | ratio |
| `attention_velocity` | Is public attention moving faster than the price? | Wikimedia pageviews | robust z |

### The exclusion that makes `insider_conviction` mean something

Most retail "insider buying" screens net purchases against sales and call it a
signal. That measures nothing, because insider **sales** are dominated by
mechanical and pre-scheduled activity. This lane **excludes**:

- code `A` (grants) and `M` (option exercises) — compensation;
- code `F`/`C` (tax withholding, conversion) — mechanical;
- anything flagged `aff10b5One`, **or** whose footnote names Rule 10b5-1 — scheduled.

What remains is an unplanned open-market purchase by an officer or director:
someone spending real money at a real price. A **cluster** (≥2 distinct buyers)
is the event worth reading. Planned sales are counted and reported
(`plannedExcluded`) so the exclusion is visible, not silent.

## Pipeline and contracts

```
fetch (injected) → pure parsers → deterministic summary → observation
      → persist → score → card snapshot → tool text + payload
```

- `contracts.Observation` — entity, signal, `asOf`, one numeric `value` (a
  uniform series), `unit`, `windowDays`, `confidence`, `source`, a reproducible
  `method`, the full `detail`, and `provenance` (accessions, article, counts).
  `value` is the series; `detail` is the evidence a card quotes.

  Keeping them apart is deliberate: the numeric series stays comparable across
  scans while the card can still say "three officers bought $4.1M".

- `confidence` is **evidence quality** (how many filings were actually read, how
  complete the pageview window is). It is not conviction and not a probability.

- Parsers are pure and the fetch is injected, so the whole pipeline runs from
  fixtures with no sockets (`python/tests/test_intel_*`).

## Scoring: triage, not expected return

Weights (renormalised over the signals that fired, so a missing signal lowers
confidence instead of scoring zero):

```
insider_conviction 0.45   attention_velocity 0.25
activist_stake     0.15   filing_heat        0.15
```

- **Gates.** A signal contributes only above its own threshold
  (`|z| ≥ 2` attention, `ratio ≥ 2` filing heat). A quiet week produces **no
  card** — silence is a result.
- **Direction** needs a directional signal. Attention is always `watch`: the
  same spike precedes a squeeze and a top. Only its interaction with price
  (`divergence`, when price context is supplied) is interpretable.
- **Conviction is corroboration, not intensity.** One very loud signal is a
  `low`-conviction card at high priority; two independent publishers are what
  upgrade it. That is why "attention alone" never reads as a strong call.
- **Priority is a 0–1 ordering for a research queue.** It is not a probability
  and not an expected return, and no tool or prompt turns it into a trade.

Every card carries `thesis` (built from the actual numbers), `invalidation`
(the specific future that proves it wrong), `caveats` (the owning signal's
stated limit) and `horizonDays`.

## `UNAVAILABLE` is the licence to be trusted

The rule from `AGENTS.md` — never fabricate financial data — is enforced at the
observation boundary:

- no Form 4 in the window → **no observation** (not a zero);
- an issuer missing from SEC's ticker→CIK map → `unavailable` with that reason;
- a Wikipedia title that is a redirect/stub (baseline median 0) → skipped, and
  redirects are followed first (`Nvidia Corp` → `Nvidia`) so a shell page is
  never mistaken for collapsed attention;
- a transport failure → the reason names the failure, distinct from "no article
  exists".

The tool text always renders the `missing` map, so a model reading only the text
cannot mistake "not measured" for "nothing happened".

## Using it

**In chat or a bot** (bots inherit the interactive agent's surface — see
`automation/dispatcher.py::_run_request`, which narrows nothing):

```
intel_scan({"tickers": ["NVDA", "MRNA"]})
intel_scan({"prices": {"NVDA": {"change5d": 0.01, "change30d": -0.08}}})
intel_entity({"ticker": "NVDA"})      intel_series({"ticker": "NVDA"})
intel_cards({"limit": 5})              intel_watch({"action": "add", "tickers": ["NVDA"]})
intel_catalog({})
```

`intel_scan` with no `tickers` uses the stored watchlist. A scheduled bot is an
ordinary automation whose objective drives these tools, e.g. *"Scan the watchlist
with `intel_scan`, and for any card with conviction `high` or `medium`, explain
the evidence and state the invalidation. Do not propose a trade."* Prices are
optional: without them the card says the divergence is unknown rather than
guessing.

**Network surface.** Only EDGAR and `wikipedia.org` are contacted, only when a
tool runs, and only with a ticker, company name or article title. No portfolio,
position, holding or user identity is sent. EDGAR requires a descriptive
`User-Agent` — override it with `BE_EDGAR_USER_AGENT` (put a contact address in
it); EDGAR's limit is 10 req/s and the client throttles to 0.12 s and reads Form
4 documents four at a time.

## Adding a signal

1. Add a `SignalSpec` (question, source, unit, rationale, **limit**) to
   `intel/contracts.py` and its id to `SIGNAL_IDS`.
2. Write a collector that returns `Observation`s: pure parser + injected fetch.
3. Add a scorer in `intel/engine.py` and its weight/gate/horizon.
4. Cover it in `python/tests/test_intel_*.py` — including the
   "cannot measure → no observation" case.
5. Update this doc's tables.

Paid imagery, AIS or a broker feed would each arrive this way: a new collector
and a new scorer, behind the same `UNAVAILABLE` contract and the same
`external_action`/licence gate. The engine does not change.

## Limits, stated plainly

- **Two sources, four signals.** That is a first lane, not a data platform.
- **`filing_heat` is seasonally biased** (proxy season, 10-K exhibits). It is
  measured against the company's own history, but a single month is a small
  sample and the gate is deliberately high.
- **Attention is not buying.** Pageviews are curiosity, polluted by news and
  surviving bot filtering; a z-score carries no direction.
- **13D intent is not a plan.** Stakes can be defensive, already priced, or
  amended down.
- **No grading loop yet.** Cards are persisted as immutable snapshots, which is
  the substrate for scoring them against forward returns later — but nothing
  currently scores them, so no hit-rate is claimed anywhere.

## Tests

`python/tests/test_intel_sec.py`, `test_intel_attention.py`,
`test_intel_engine.py`, `test_intel_service.py` — parsers against real filing
shapes (including namespaced XML and both plan-flag paths), the robust-z
behaviour and its refusal cases, scoring gates and conviction semantics, the
end-to-end pipeline over fixtures, idempotent re-scans, owner scoping, honest
`unavailable` reporting, and the boot wiring (all six tools registered `read`/`low`
and advertised on `ECLIPSE_AGENT`).
