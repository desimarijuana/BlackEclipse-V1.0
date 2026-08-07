# BlackEclipse

An open-source, agentic AI investment research platform with a Bloomberg-inspired terminal UI. Screen stocks, track a portfolio, follow market news, and explore crypto bubbles — all in a dark, glassmorphic interface.

![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js)
![TypeScript](https://img.shields.io/badge/TypeScript-5-blue?logo=typescript)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)
![Tailwind](https://img.shields.io/badge/Tailwind-4-38BDF8?logo=tailwindcss)
![License](https://img.shields.io/badge/License-MIT-green)

## Features

- **Agentic Chat** — an AI research assistant interface (provider-agnostic, mock by default)
- **Market Screener** — stocks, crypto, ETFs, IPOs, blue chips, funds, and dividend stocks with advanced filtering
- **Market Bubbles** — an interactive physics-based crypto bubble visualization
- **My Portfolio** — holdings, performance charts, asset allocation, and transaction log
- **Market News** — sentiment-tagged financial news feed
- **Aurora Background** — a WebGL aurora glow that reacts to market sentiment (green = bullish, red = bearish)
- **Dark Theme** — consistent black/grey Bloomberg-inspired palette

## Tech Stack

| Layer | Technology |
|---|---|
| Framework | Next.js 15 (App Router) |
| Language | TypeScript |
| UI | React 19 + Tailwind CSS v4 |
| Components | @base-ui/react (shadcn-style) |
| Charts | Recharts, TradingView widget |
| 3D/GL | ogl (Aurora background) |
| PDF | jspdf + jspdf-autotable |

## Getting Started

### Prerequisites
- Node.js 20+
- npm

### Install & Run

```bash
# 1. Install dependencies
npm install

# 2. Start the dev server
npm run dev
```

Open [http://localhost:3000](http://localhost:3000) in your browser.

### Scripts

| Script | Description |
|---|---|
| `npm run dev` | Start the Next.js dev server |
| `npm run build` | Production build |
| `npm run start` | Start the production server |
| `npm run lint` | Run ESLint |

## Project Structure

```
src/
├── app/                    # Next.js App Router
│   ├── layout.tsx          # Root layout (dark theme, fonts)
│   └── page.tsx            # Renders the StockChat terminal
├── components/
│   ├── chat/               # Chat input, history, empty state
│   ├── layout/             # Sidebar, top bar
│   ├── screens/            # Full-screen views (screener, bubbles, portfolio, news)
│   └── ui/                 # Reusable primitives (button, card, skeleton, etc.)
├── hooks/                  # Custom hooks (portfolio engine)
├── lib/                    # Utilities
└── types/                  # TypeScript definitions
```

## Architecture

The app is fully client-side and runs on **demo data** out of the box — no API keys or database required. This makes it easy to run, test, and contribute to.

The **agentic chat** is designed to be provider-agnostic: swap in OpenAI, Anthropic, or a local Ollama model by setting the corresponding environment variable. Without one, it falls back to built-in mock responses.

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

[MIT](LICENSE)
