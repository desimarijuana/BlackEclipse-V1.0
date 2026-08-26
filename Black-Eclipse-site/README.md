# BlackEclipse

An open-source, agentic AI investment research platform with a Bloomberg-inspired terminal UI. Screen stocks across 25+ world markets, track a portfolio, follow market news, and explore market bubbles — all in a dark, glassmorphic interface.

![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js)
![TypeScript](https://img.shields.io/badge/TypeScript-5-blue?logo=typescript)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=npm)
![Tailwind](https://img.shields.io/badge/Tailwind-4-38BDF8?logo=tailwindcss)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Market Screener** — equities across US, Pakistan, India, China and 20+ more markets with advanced filtering (sector, industry, cap, P/E, price, volume)
- **Market Bubbles** — interactive physics-based bubble visualization per market (cap-weighted)
- **Global Markets overview** — top instruments by market for every loaded country
- **My Portfolio** — holdings, performance charts, allocation, transaction log
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
- *(optional)* Python 3.9+ with `yfinance` — enables live quotes for non-TradingView markets (e.g. US):
  ```bash
  pip install yfinance
  ```

### Install & Run

```bash
# 1. Install dependencies
npm install

# 2. Start the dev server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser. That's it — the database creates itself, seeds demo data, and starts pulling live prices for any markets you enable.

### Scripts

| Script | Description |
|---|---|
| `npm run dev` | Start the Next.js dev server (also boots the refresh scheduler) |
| `npm run build` / `npm run start` | Production build / serve |
| `npm run lint` | ESLint |
| `npm test` | Vitest unit tests |

## Configuration (all optional)

The app runs fully without environment variables. Copy `.env.example` to `.env.local` to configure:

| Variable | Purpose |
|---|---|
| `CRON_SECRET` | Enables server-to-server calls to mutating endpoints (`Authorization: Bearer <secret>`). **Set this when deploying publicly.** Without it, only same-origin browser requests and localhost calls can mutate state. |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` / `OLLAMA_BASE_URL` | Power the agentic chat/research. Without any of them, a built-in mock provider answers. Keys can also be set from the in-app Settings screen. |

## Deployment Notes

- **Local machine / VPS / Docker (recommended):** everything works out of the box — the scheduler runs inside the app process.
- **Vercel/serverless:** SQLite and the in-process scheduler don't fit serverless. A `POST /api/cron/run` endpoint exists for hosted schedulers (see `vercel.json`); point it at a persistent database for real deployments.
- In-memory caches assume a single app instance; running multiple replicas against one SQLite file is not supported.

## Security Model

BlackEclipse ships open (no accounts) so anyone can clone and run it. Mutating API routes (refresh, settings, scraper, cron, research agents) accept:

1. Same-origin browser requests (the app's own UI), always;
2. Requests carrying `Authorization: Bearer <CRON_SECRET>` or `x-api-key`, when `CRON_SECRET` is configured;
3. Non-browser requests only while the server is on localhost.

Expensive endpoints additionally rate-limit per IP. Outbound feed URLs are validated against an SSRF allowlist (public http(s) hosts only). Stored LLM keys never leave the server — the settings API reports only whether a key exists.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)
