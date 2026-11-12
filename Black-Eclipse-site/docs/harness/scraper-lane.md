---
title: The scraper lane (collect what the vault does not have)
status: Current
last-verified: 2026-10-20
---

# The scraper lane

**Who this is for:** you want to know how Eclipse gets data that is not in JDdS,
and where the line is between "collect a page" and "build a scraper".

## Why this exists

JDdS is a vault, not the world. It holds the market data, filings and series the
app was built around — but a user routinely asks for something the vault does
not have: an index's published weights, a regulator's daily bulletin, a
company's own investor table. Until now the answer was `UNAVAILABLE`, full
stop, and the honest-but-useless one.

`web_scrape` covers the easy half of that: ONE page, ONE CSS selector, ONE
answer. It cannot walk to page 2, cannot join two sources, cannot reshape the
records.

The **scraper lane** covers the rest. When the answer is not on the page (and
not in the vault), Eclipse writes a scraper for the site that has it, runs it,
and keeps what it found.

## The shape of it

```
user:  "pull the daily holdings for this fund and keep them"
   │
   ├─ agent writes a Python program (the scraper)
   │     import eclipse_tools
   │     page = eclipse_tools.web_page(url=..., selector=..., fields={...})
   │     result = {"rows": page.get("rows") or [], "columns": [...]}
   │
   ├─ Eclipse runs it in the SAME analysis sandbox
   │     · no sockets, no files outside its own folder, no other processes
   │     · the ONLY way out is eclipse_tools.web_page
   │
   ├─ the HOST does the fetching
   │     · the same SSRF-hardened transport web_scrape uses
   │     · https-only, DNS-pinned, every redirect re-checked, size/time caps
   │
   ├─ the operator approves the SITE (once)
   │     · the unit of consent is the DOMAIN, not the program
   │     · after the first approval the domain is remembered (a revocable
   │       standing grant)
   │
   └─ the rows are stored
         · in the custom-dataset store, labelled SCRAPER
         · each row keyed by its own content, so a re-run updates in place
         · the program is saved beside them, so it can be run again
```

## The three rules that make it safe

1. **The program cannot reach the network.** `socket` and `ssl` stay denied by
   the runtime guard; there is no import allowlist entry for an HTTP client; a
   URL literal is refused by the AST gate unless the host turned the web
   binding on for THAT run. The only way a page is fetched is the host's
   `web_page` binding, which validates the address and hands it to the
   hardened transport.
2. **The consent is per domain.** The approval kind is `scraper_domain` and its
   request key is the host. A different site asks again. The consent is a
   standing grant, so it is visible and revocable like every other grant.
3. **What comes back is COLLECTED.** Scraped rows are labelled `SCRAPER` and are
   never a verified source, never an Eclipse-verified number, and never a
   canonical market row. The page is the source; cite the page.

## Honesty rules

- A program that never sets `result` is a **failure**, not an empty dataset.
  The host appends a check to the program so the two can never be confused.
- A selector that matches nothing is a **confirmed zero for the pages it read**
  — not proof the data does not exist.
- A failed fetch is `UNAVAILABLE`, not absence.
- A row the vault could not store is reported as not stored. The count that
  comes back is the count that was written.

## Where it lives

| Piece | Where |
|---|---|
| The tool (`scraper_run`) | `python/harness/scraper/tools.py` |
| The program contract (what `result` must be) | `python/harness/scraper/program.py` |
| The per-domain approval | `python/harness/scraper/authorizers.py` |
| Where rows and programs are kept | `python/harness/scraper/store.py` |
| The sandbox binding (`web_page`) | `python/harness/code/sandbox_tools.py` |
| The sandbox seam (tool set, URL literals, call budget) | `python/harness/code/execution.py` |
| The policy noun family | `python/harness/code/policy.py` (`SCRAPER_TOOLS`) |
| The front-door write route | `src/app/api/scraper/datasets/route.ts` |
| The page collection (the host's fetch) | `src/lib/harness/data-bridge/data-bridge-collect.ts` |

## Deliberately not here

- **No unbounded crawler.** One run reads a bounded number of pages
  (`MAX_PAGE_FETCHES`), and the budget is the host's, not the program's.
- **No second transport.** The lane reuses `web_collect` — the same capability
  `web_scrape` uses. There is no second HTTP client, no second HTML parser.
- **No site mirroring, no robots bypass, no stored credentials.**
- **The analysis sandbox still cannot reach the web.** The web binding belongs
  to this lane alone; an ordinary `analysis_run` program may not even name a
  URL.

## See also

- `docs/harness/web-research-engine.md` — the read-only research engine and
  `web_scrape`.
- `docs/harness/roadmap/phase-16-bulk-acquisition.md` — the bulk-acquisition
  phase this lane sits next to (declared sources, not generated code).
- `docs/harness/python-runtime.md` — the analysis sandbox itself.
- ADR-051 — why the lane is shaped this way.
