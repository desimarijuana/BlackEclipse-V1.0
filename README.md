# BlackEclipse

**An open-source, agentic AI investment research platform** with a
Bloomberg-inspired terminal UI: screen 25+ world markets, track a portfolio,
follow market news, and run a provider-agnostic agent that can research, compute
and (on a demo broker) trade.

![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js)
![TypeScript](https://img.shields.io/badge/TypeScript-5-blue?logo=typescript)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python)
![License](https://img.shields.io/badge/License-MIT-green)

## Quick start

```bash
cd Black-Eclipse-site
npm install       # also provisions the Python agent runtime
npm run dev       # http://localhost:3000
```

No API keys or database setup are required: first boot provisions and seeds the
local market-data vault (`jdds.db`), and the agent runtime starts automatically.
Add a provider key (or point at Ollama) in **Settings** to use a frontier model.

## What is in the box

- **Market screener + global markets** — equities across the US, Pakistan, India,
  China and 20+ more markets.
- **Portfolio** — holdings, performance, allocation, heatmap, correlation,
  contribution-to-risk.
- **News** — sentiment-tagged feed with configurable sources.
- **Agentic chat & research** — Python/LangChain/LangGraph runtime with tools,
  graph workflows, memory, skills and a verification layer.
- **Broker connectivity** — read-only by default; demo execution under an
  operator-created mandate; one-click live approval. No order-send path without
  an explicit operator authorization.
- **Self-hosted data vault (JDDS)** — prices fetched once and served locally;
  source reliability is learned over time.

## Repository layout

| Path | What it is |
|---|---|
| `Black-Eclipse-site/` | The application (Next.js front door + Python agent runtime) |
| `Black-Eclipse-site/docs/` | The canonical system documentation |
| `Black-Eclipse-site/scripts/` | Build, test, release, backup and operations scripts |
| `.github/workflows/` | CI, deploy, live evals, weekly ops drift watch |
| `SECURITY.md` | How to report a vulnerability (GitHub private advisories) |
| `CODEOWNERS` | Path ownership for review |

Start reading at
[`Black-Eclipse-site/README.md`](Black-Eclipse-site/README.md) and
[`Black-Eclipse-site/docs/NAVIGATION.md`](Black-Eclipse-site/docs/NAVIGATION.md).

## Production use

The current release is **`v0.3.0`**, a production release for a
**single-operator self-hosted** instance — not a hosted multi-tenant service.
See [`Black-Eclipse-site/docs/releases/v0.3.0.md`](Black-Eclipse-site/docs/releases/v0.3.0.md)
for the verification record and
[`Black-Eclipse-site/docs/DEPLOYMENT.md`](Black-Eclipse-site/docs/DEPLOYMENT.md)
for deployment, backups, monitoring and incident handling.

The live agent benchmark is published honestly: `task_success 0.8520` on the
live-eligible tasks, below the **0.9 target**. The target is unchanged; the
release ships on a recorded, version-scoped floor (ADR-071 / ADR-H347).

## Contributing

See [`Black-Eclipse-site/CONTRIBUTING.md`](Black-Eclipse-site/CONTRIBUTING.md).
Security reports go through GitHub's private advisory channel, never a public
issue ([`SECURITY.md`](SECURITY.md)).

## License

The application and this repository's original code are **MIT** (see
[`LICENSE`](LICENSE)). One component is different: the isolated Pine Script
engine in `Black-Eclipse-site/pine-engine/` is a separate program distributed
under **AGPL-3.0-only** because it depends on `pinets`; it communicates with the
app only through files. See
[`Black-Eclipse-site/pine-engine/NOTICE.md`](Black-Eclipse-site/pine-engine/NOTICE.md).
