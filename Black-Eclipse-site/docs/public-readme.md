---
title: The Public README
status: Current
last-verified: 2026-11-15
---

# The Public README

**Who this is for:** anyone changing the public claim, the screenshots, the install
instructions, the benchmark block or the social preview — and anyone who has to
defend a sentence on them.

The repository root `README.md` is the **only** public front door. There is no
separate landing site and no Pages build: a reader arrives on the repo page and
decides there. Every social post, release note and link points at that one file.

That makes the README a marketing surface with a **factual obligation**. This
project's whole argument is that its claims are auditable, so a sentence in the
README is held to the same standard as a number in a report.

---

## 1. The order, and why it is that order

A stranger needs to know *what this is* before they can care *why it is
different*, and needs to see it before they trust either. So:

1. **Hero** — name, "The Open-Source Financial AI Harness", the four verbs
   (*Research. Analyze. Build. Automate. Trade.*), download, badges.
2. **Screenshots** — real captures, immediately.
3. **Introduction** — the fragmentation problem, in the reader's terms.
4. **Problems we're solving** — five, each paired with the answer in the same row.
5. **What makes it different** — six differentiators; this is the section that
   earns a choice.
6. **What you can do** — nine capabilities, each linked to its package or doc.
7. **Architecture** — seven areas with what exists today and its source path.
8. **Why it is a harness** — the model/Python/broker split, stated once.
9. **Workflow** — one narrative from question to authorized order.
10. **Who it is for** — five personas.
11. **Install** — platforms, signing status, checksums, troubleshooting.
12. **First working example** — smoke test, then an embedded run.
13. **Benchmarks** — the numbers *and* the methodology table.
14. **Documentation · roadmap and limits · open source · licensing · disclaimer.**

Two rules of thumb: a section that repeats an earlier one gets cut (that is why
there is one philosophy section, not three), and a claim that cannot be checked
belongs in a blog post, not here.

## 2. Every claim and its evidence

If you change a claim, change this row in the same commit. If the evidence no
longer exists, the claim comes off the README.

| Claim | Evidence in the tree |
|---|---|
| MetaTrader 5 integration for trading operations | `python/harness/trade/` (`terminal.py`, `tools.py`), `computer/applications/adapters.py` (`MT5Adapter`); doc `docs/trading.md` |
| Provider-agnostic models (OpenAI, Anthropic, Google, Mistral, Groq, OpenAI-compatible, Ollama) | `python/harness/models.py`, `python/harness/model_runtime/`, extras in `Black-Eclipse-site/pyproject.toml` |
| The model never computes a metric; formula, inputs, assumptions and seed are recorded | `docs/harness/financial-analysis-engine.md`, `python/harness/research/calculations.py` |
| Backtesting is anti-lookahead; walk-forward, Deflated Sharpe / PBO | `docs/quant-engine.md`, `python/harness/quant/` (`walkforward`, `multiple_testing`, `montecarlo`, `verdict`) |
| Leases, fencing, at-most-once effects, `unknown` as a first-class outcome | `docs/harness/failure-recovery.md`, `python/harness/run_effects.py` |
| One authorization path, hash-chained audit, undeclared tools unpublished | `docs/harness/security.md`, `docs/harness/tool-registry.json`, `python/harness/security/` |
| Authority scores; conflicts disclosed, never averaged | `docs/harness/search-retrieval.md`, `python/harness/retrieval/authority.py`, `market/verification.py` |
| Sandbox flags (`python -I`, scrubbed env, `--network none`) | `docs/harness/quant-sdk-sandbox.md`, `python/harness/quant/sdk_runtime.py` |
| Live trial gates, mandate, kill switch, named refusals | `docs/quant-live-strategy.md`, `python/harness/trade/`, `python/tests/test_quant_live.py` |
| **Benchmark numbers** (0.9970 / 0.9748 / 0.9963 / 1.0000) | `docs/harness/benchmarks.md` — generated, never hand-edited |
| **Corpus size** (347 tasks, 15 datasets, split counts, oracle coverage 78.1%) | `python/harness/evaluation/baselines/corpus_manifest.json` |
| `financial_accuracy` is graded deterministically, not by a model | `docs/harness/agent-evaluation.md` §5 (`FinancialGrader` recomputes the oracle) |
| Installers are unsigned; releases publish `SHA256SUMS.txt` | `.github/workflows/desktop-release.yml` (three-OS matrix), `scripts/desktop-installer.js` (writes the sums, prints the unsigned warning) |
| Linux `.deb` and macOS `.dmg` artifacts | `.github/workflows/desktop-release.yml` (build + smoke-test steps per OS) |
| `npm run desktop:doctor` exists | `Black-Eclipse-site/package.json` scripts |
| Pine engine is a separate AGPL-3.0-only program | `Black-Eclipse-site/pine-engine/NOTICE.md`, root `LICENSE` |

## 3. Screenshots

- Captures live in `Black-Eclipse-site/docs/figures/readme/`, 1600px wide,
  PNG, ≤ 170 KB each.
- **They are real captures of the running app.** No mockups, no stock imagery, no
  invented dashboards. A screenshot that shows a state the product cannot reach is
  a fabricated benchmark with better lighting.
- **Crop the bottom of the app window.** The composer's status strip renders a
  machine-local path (`C:\Users\<name>\AppData\Local\Temp\...`), which leaks a
  user profile into a public repo. The committed figures are cropped to 1600×868
  for exactly this reason — see `docs/OPEN-SOURCE-READINESS.md` O3.
- Screenshots that show demo data must keep the `DEMO` badge visible.
- Missing shots (quant/strategy, portfolio, MT5) are pending a clean capture. Do
  not substitute a competitor's image or a stock chart; leave the gap.

Regenerate from the launch assets with `sharp` (run from `Black-Eclipse-site/`,
where it is installed): resize to 1600 wide, `extract` to height 868, then
`png({ compressionLevel: 9 })`.

### The four that need a warm, fresh app

Dashboard, Journal, Graph Studio and Bots cannot be captured from a cold checkout,
and a stale vault is not enough either. What happens when you try (all four
verified on 2026-11-15, against a copy of a real vault):

| Surface | What blocks a good capture |
|---|---|
| **Dashboard** | Needs fresh prices. A vault whose last price write is days old makes the app render `LIVE PRICES UNAVAILABLE` and leave widgets on `Loading…` — which is correct behaviour and a terrible screenshot. |
| **Journal** | Needs seeded trades. The demo seeder supplies 76 labelled trades, but the tab also needs the price bridge, so it renders `LOADING` while the bridge is cold. |
| **Bots** | The list arrives (13 automations seed from a used profile), but the conversation pane fetches threads from the harness and sits on `LOADING` for a long time on a large `agent-memory.db`. |
| **Graph Studio** | Deep-linking `?tab=graph-studio` renders the Workflows gallery; the canvas needs a workflow *opened* from the catalog, and the catalog needs the harness warm. It is not in the default sidebar, so it also cannot be reached by clicking F-keys. |

Capture procedure:

```bash
cd Black-Eclipse-site
npm run desktop:refresh                      # seeds the vault, boots the runtime
# let the app refresh prices once (Market Discover -> Refresh Prices), then:
node scripts/capture-readme-shots.js
```

The script waits for real content, refuses to write a figure that is still
`LOADING`, and crops to 1600 wide. Two hard rules:

- **Do not screenshot a stale vault.** `LIVE PRICES UNAVAILABLE` is the product
  being honest; shipping it in the README makes the product look broken instead.
- **Do not screenshot a personal vault.** The dev vault carries real broker
  trades. Scrubbing for a capture means deleting `Trade`, `TradeFill`,
  `TradeExecution`, `JournalDay` and `JournalProfile` from a *copy*, then seeding
  demo trades — never pointing the app at the real file.

A headless capture against a dev server with no seeded harness produces `BOTS · 0`,
a blank canvas and a spinner. That was tried twice and rejected both times.

## 4. Copy rules

1. **No unverifiable superlative.** "Deterministic", "durable", "auditable" are
   fine because each maps to a row above. "Best", "fastest", "most accurate" are
   not.
2. **No slogan as a section heading, and no metaphor where a mechanism would do.**
   Learned the hard way: "a door that doesn't open" and "survives Tuesday" read as
   generic because they could describe any product. "What it refuses to do",
   followed by six refusal codes, could not.
3. **Concrete over clever.** Prefer the flag, route, command or error string:
   `maxConcurrency` 4, `python -I`, `--network none`, `APPROVAL_REQUIRED`.
4. **Say what is unmeasured.** `UNKNOWN` appears in the benchmark block on
   purpose. Never round it to zero or to a pass.
5. **Never claim a distribution that does not exist.** The install block leads
   with the source install and labels PyPI as pending (§6).
6. **The heading states the category.** *The Open-Source Financial AI Harness*
   tells a stranger what this is; the four verbs tell them what it is for.
7. **No vendor trademark in the positioning.** Not a "Bloomberg replacement" — a
   terminal is a data product, this is infrastructure. `docs/OPEN-SOURCE-READINESS.md`
   O6 flags vendor wording for a trademark read.

## 5. The social preview

`.github/assets/social-card.svg` is the source of truth for the 1280×640 preview
(Repository → Settings → Social preview). Export the PNG rather than editing the
bitmap:

```bash
cd Black-Eclipse-site
node -e "require('sharp')('../.github/assets/social-card.svg',{density:144}).resize(1280,640).png().toFile('../.github/assets/social-card.png')"
```

`.github/assets/download-windows.svg` is the README's download button. It must
keep pointing at the version-independent release alias
`releases/latest/download/BlackEclipse-Setup.exe` — never a versioned filename.

## 6. Two things that are not finished

| # | Open item | Effect on the README |
|---|---|---|
| L1 | `black-eclipse-harness` is **not on PyPI** (`docs/harness/roadmap/round-4-gap-closure.md` O6: "declarable, not installable") | The install block shows the source install and says "PyPI release pending". When it publishes, replace the source line with `pip install black-eclipse-harness` and delete the note. `.github/workflows/publish-harness.yml` does the publish on a version tag. |
| L2 | The public repository URL does not exist yet; `origin` is private, and `pyproject.toml` points at `github.com/black-eclipse/black-eclipse` | Every link uses the current `origin`. Rewrite them in one pass when the public repository is created — never mix the two. |

## 7. Where this sits

- [`OPEN-SOURCE-READINESS.md`](./OPEN-SOURCE-READINESS.md) — what makes the
  repository safe to publish. The README is the *argument*; that doc is the *gate*.
- [`PRODUCTION-READINESS.md`](./PRODUCTION-READINESS.md) — what is still open in
  the product. The README's roadmap section points here.
- [`NAVIGATION.md`](./NAVIGATION.md) — the task row that sends you back here.
