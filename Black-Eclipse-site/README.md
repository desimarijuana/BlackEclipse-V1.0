# BlackEclipse

An open-source, agentic AI investment research platform with a Bloomberg-inspired terminal UI. Screen stocks across 25+ world markets, track a portfolio, follow market news, and explore market bubbles — all in a dark, glassmorphic interface.

![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js)
![TypeScript](https://img.shields.io/badge/TypeScript-5-blue?logo=typescript)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=npm)
![Tailwind](https://img.shields.io/badge/Tailwind-4-38BDF8?logo=tailwindcss)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Market Screener** — equities across US, Pakistan, India, China and 20+ more markets with advanced filtering (sector, industry, cap, P/E, price, volume)
- **Market Bubbles** — interactive physics-based turnover map per market, with a whole-market Volume Analytics panel (traded value, concentration, contribution bands)
- **Global Markets overview** — top instruments by market for every loaded country
- **My Portfolio** — holdings, performance charts, allocation, transaction log, plus a per-fund heatmap, date-aligned correlation matrix and contribution-to-risk decomposition
- **Market News** — sentiment-tagged financial news feed (configurable RSS sources)
- **Agentic Chat & Research** — provider-agnostic AI assistant (OpenAI / Anthropic / Ollama / built-in mock), with a multi-agent research pipeline that persists findings
- **Self-healing data layer (JDDS)** — prices are scraped once into a local SQLite vault and served to every screen; source reliability is learned over time

## Architecture at a Glance

```
Browser UI ──► Next.js API routes ──► JDDS (SQLite via Prisma)
                      ▲                     ▲
                      │                     │ background scheduler (node-cron)
             in-memory SWR caches     TradingView scanner (whole markets,
                                      batched) + yfinance Python bridge
                                      (US etc.) + adaptive fallback chain
```

- **JDDS** (`jdds.db`, auto-created on first run) is the single data vault: assets, latest prices, index quotes, news, source health, agent research memory.
- **Price refresh** runs in-process while the app runs. TradingView-covered markets are synced as one whole-market scan; other markets use a batched [yfinance](https://pypi.org/project/yfinance/) bridge (`scripts/yfinance_bridge.py` — needs Python 3.9+ installed, optional).
- Markets outside trading hours are skipped automatically (per-market timezone/hours stored in JDDS).
- **Simulated data is always labeled**: when no real universe has been imported yet the screener falls back to demo values behind a visible `DEMO` banner.

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 15 (App Router) |
| Language | TypeScript |
| UI | React 19 + Tailwind CSS v4 |
| Components | @base-ui/react (shadcn-style) |
| DB | SQLite via Prisma + better-sqlite3 (zero-config, file-based) |
| Charts | Recharts, TradingView widget |
| Scraping | TradingView scanner API, yfinance bridge, cheerio, Playwright fallbacks |
| Scheduler | node-cron (in-process) |

## Getting Started

### Prerequisites
- Node.js 20+
- npm
- Rust and the Tauri prerequisites to build the desktop shell (see
  [`desktop/README.md`](desktop/README.md))
- *(optional)* Python 3.9+ with `yfinance` — enables live quotes for non-TradingView markets (e.g. US):
  ```bash
  pip install yfinance
  ```

### Install & Run

```bash
# 1. Install dependencies (also provisions the Python agent stack)
npm install

# 2. Build and open the desktop app
npm run desktop:dev       # Dev channel: isolated data, port 3101
# or
npm run desktop:refresh   # Stable channel: promote the build, port 3100
```

The product is the **native desktop app**; there is no website to open. On a
packaged install, launch **Black Eclipse** from the Start menu — it starts its
own loopback server. `npm run desktop:doctor` prints the window, port, served
build, harness, and provider state in one screen.

### Scripts

| Script | Description |
|---|---|
| `npm run desktop:dev` | Build and launch the Dev channel (isolated data, port 3101) |
| `npm run desktop:refresh` | Build, promote, and open the Stable channel (port 3100) |
| `npm run desktop:doctor` | One-screen window / port / build / harness / provider status |
| `npm run build` | Production Next build used by the desktop payload |
| `npm run lint` / `npm run typecheck` | ESLint / `tsc --noEmit` |
| `npm test` | Vitest + Python + eval gates |
| `npm run check:all` | The full release gate |

## Configuration (all optional)

The app runs fully without environment variables. Copy `.env.example` to `.env` to configure:

| Variable | Purpose |
|---|---|
| `CRON_SECRET` | Guards server-to-server calls to mutating endpoints (`Authorization: Bearer <secret>`) and the non-loopback harness bind. |
| `HARNESS_AUTH` / `HARNESS_AUTH_SECRET` | `required` + a random secret is mandatory before any non-loopback bind. A missing secret fails closed (503). |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `OLLAMA_BASE_URL` | Power the agentic chat/research. Without one, an agent run fails honestly with a provider-unavailable error — it never falls back to a fake answer. Keys can also be set in the in-app Settings screen. |
| `CONNECTOR_SECRET_KEY` | Base64 32-byte key used to encrypt operator data-source credentials at rest. Locally it is optional — a gitignored `.connector-key` is generated on first use. |

## Runtime Notes

- The **desktop app is the product**. It owns its loopback server and the Python
  harness; there is no hosted website, reverse proxy, or serverless deployment
  lane.
- Two channels can run at once: **Stable** (3100) and **Dev** (3101, isolated
  data).
- The agent runtime is a child process. If Python is unavailable, runs fail
  honestly with a 503 instead of falling back to a mock agent.
- Back up the data directory (`jdds.db`, `agent-memory.db`, `.black-eclipse/`).

## Security Model

BlackEclipse ships open (no accounts) so anyone can clone and run it. Mutating API routes (refresh, settings, scraper, cron, research agents) accept:

1. Same-origin browser requests (the app's own UI), always;
2. Requests carrying `Authorization: Bearer <CRON_SECRET>` or `x-api-key`, when `CRON_SECRET` is configured;
3. Non-browser requests only while the server is on localhost.

Expensive endpoints additionally rate-limit per IP. Outbound feed URLs are validated against an SSRF allowlist (public http(s) hosts only). Stored LLM keys never leave the server — the settings API reports only whether a key exists.

## Documentation

New to the codebase? Start with [`docs/OVERVIEW.md`](docs/OVERVIEW.md), then
follow the reading order in [`docs/README.md`](docs/README.md):

| Doc | Answers |
|---|---|
| [`docs/OVERVIEW.md`](docs/OVERVIEW.md) | What is this, and what is the mental model? |
| [`docs/QUICKSTART.md`](docs/QUICKSTART.md) | How do I run it? |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | What are the layers? |
| [`docs/DATA-FLOW.md`](docs/DATA-FLOW.md) | Where does data come from? |
| [`docs/NAVIGATION.md`](docs/NAVIGATION.md) | Which file do I open to change X? |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Why is it built this way? |
| [`docs/GLOSSARY.md`](docs/GLOSSARY.md) | What does this word mean? |

Documentation rules and maintenance obligations are in
[`skills/DOCS.md`](skills/DOCS.md).

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)
