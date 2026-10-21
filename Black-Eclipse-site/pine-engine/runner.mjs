// ── The isolated Pine Script runtime ─────────────────────────────────────────
// This is a SEPARATE PROGRAM. It is not a library of the Eclipse app and it
// is never imported by it: Eclipse spawns it as a child process, hands it a
// JSON request file, and reads back a JSON response file. The only thing that
// crosses the boundary is data.
//
// ── Why the boundary exists ─────────────────────────────────────────────────
// The Pine Script engine this program uses (`pinets`, by LuxAlgo) is licensed
// AGPL-3.0-only. Running it inside the app would arguably make the app a
// derivative work. Keeping it in its own program, communicating only through
// files, follows the "separate programs communicating at arm's length" pattern
// from the GPL FAQ: the app stays proprietary, and the corresponding source of
// THIS program is public (it lives in this repository) while the engine's own
// corresponding source ships with the npm package it came from.
//
// If you change this file, you change the corresponding source of the
// AGPL-covered work in this folder. Keep it that way.
//
// ── The protocol ─────────────────────────────────────────────────────────────
//   request:  { source, bars: [{time,o,h,l,c,v}], symbol, timeframe, limits }
//   response: { status: "ok"|"error", plots, signals, trades, diagnostics }
//
// The runner never reaches the network: the bars come from the request, so a
// Pine script is always evaluated against the data the caller already has.

import { readFileSync, writeFileSync } from 'node:fs';
import { basename } from 'node:path';

let PineTS;
let Provider;
try {
  ({ PineTS, Provider } = await import('pinets'));
} catch (err) {
  const message = `the Pine engine is not installed - run \`npm run setup:pine\` (${err && err.message})`;
  process.stderr.write(`${message}\n`);
  process.exit(70);
}

const requestPath = process.argv[2];
if (!requestPath) {
  process.stderr.write('usage: runner.mjs <request.json>\n');
  process.exit(64);
}

let request;
try {
  // A byte-order mark is not JSON; strip it rather than refusing the file.
  const raw = readFileSync(requestPath, 'utf8').replace(/^﻿/, '');
  request = JSON.parse(raw);
} catch (err) {
  process.stderr.write(`the request was not readable: ${err && err.message}\n`);
  process.exit(66);
}

const responsePath = request.responsePath;

/** A provider that serves the bars carried by the request - never the network. */
class LocalBarsProvider {
  constructor(bars, symbol, timeframe) {
    this.bars = bars ?? [];
    this.symbol = symbol ?? 'UNKNOWN';
    this.timeframe = timeframe ?? '1d';
  }

  configure() {}

  getSupportedTimeframes() {
    return new Set([this.timeframe]);
  }

  async getSymbolInfo(tickerId) {
    return {
      current_contract: tickerId,
      description: tickerId,
      isin: '',
      main_tickerid: tickerId,
      prefix: '',
      root: tickerId,
      ticker: tickerId,
      tickerid: tickerId,
      type: 'stock',
      basecurrency: 'USD',
      country: 'US',
      currency: 'USD',
      timezone: 'Etc/UTC',
      employees: 0,
      industry: '',
      sector: '',
      shareholders: 0,
      shares_outstanding_float: 0,
      shares_outstanding_total: 0,
      expiration_date: 0,
      session: '24x7',
      volumetype: 'base',
      mincontract: 1,
      minmove: 1,
      mintick: 0.01,
      pointvalue: 1,
      pricescale: 100,
      recommendations_buy: 0,
      recommendations_buy_strong: 0,
      recommendations_date: 0,
      recommendations_hold: 0,
      recommendations_sell: 0,
      recommendations_sell_strong: 0,
      recommendations_strong_buy: 0,
      recommendations_strong_sell: 0,
      recommendations_total: 0,
      target_price_average: 0,
      target_price_date: 0,
      target_price_estimates: 0,
      target_price_high: 0,
      target_price_low: 0,
      target_price_median: 0,
    };
  }

  async getMarketData(tickerId, timeframe, limit) {
    const rows = this.bars
      .slice(0, limit && limit > 0 ? limit : undefined)
      .map((bar) => ({
        time: bar.time ?? 0,
        open: Number(bar.o ?? bar.open ?? 0),
        high: Number(bar.h ?? bar.high ?? 0),
        low: Number(bar.l ?? bar.low ?? 0),
        close: Number(bar.c ?? bar.close ?? 0),
        volume: Number(bar.v ?? bar.volume ?? 0),
        openTime: bar.time ?? 0,
        closeTime: bar.time ?? 0,
      }));
    return rows;
  }
}

function serializePlots(plots) {
  const out = {};
  if (!plots || typeof plots !== 'object') return out;
  for (const [name, plot] of Object.entries(plots)) {
    // The engine keeps its drawing helpers under `__`-prefixed keys; they are
    // not the script's plots.
    if (name.startsWith('__')) continue;
    const data = Array.isArray(plot?.data) ? plot.data : [];
    out[name] = {
      title: plot?.title ?? name,
      // The engine's plot points are {title, time, value, options}; the value
      // is the number, and it is `null` while the indicator is warming up.
      points: data.map((point) => ({
        time: point?.time ?? null,
        value: point?.value === null || point?.value === undefined ? null : Number(point.value),
      })),
    };
  }
  return out;
}

function serializeTrade(trade) {
  return {
    id: trade?.id ?? null,
    entryId: trade?.entry_id ?? null,
    direction: trade?.size < 0 ? 'short' : 'long',
    entryTime: trade?.entry_time ?? null,
    entryBarIndex: trade?.entry_bar_index ?? null,
    entryPrice: trade?.entry_price ?? null,
    exitTime: trade?.exit_time ?? null,
    exitBarIndex: trade?.exit_bar_index ?? null,
    exitPrice: trade?.exit_price ?? null,
    exitId: trade?.exit_id ?? null,
    quantity: trade?.size ?? null,
    commission: trade?.commission ?? null,
    profit: trade?.profit ?? null,
    maxDrawdown: trade?.max_drawdown ?? null,
    maxRunup: trade?.max_runup ?? null,
    status: trade?.status ?? null,
  };
}

function serializeTrades(strategy) {
  const closed = Array.isArray(strategy?.closedtrades) ? strategy.closedtrades : [];
  const open = Array.isArray(strategy?.opentrades) ? strategy.opentrades : [];
  return [...closed.map(serializeTrade), ...open.map(serializeTrade)];
}

function write(payload) {
  try {
    writeFileSync(responsePath, JSON.stringify(payload), 'utf8');
  } catch (err) {
    process.stderr.write(`the response could not be written: ${err && err.message}\n`);
    process.exit(73);
  }
}

try {
  const provider = new LocalBarsProvider(request.bars, request.symbol, request.timeframe);
  // The engine takes a provider INSTANCE; registering it under a name as well
  // keeps the ticker resolution honest for scripts that ask for it.
  try {
    Provider.eclipse = provider;
  } catch {
    // A frozen registry is not fatal: the instance is passed directly.
  }
  const pine = new PineTS(provider, request.symbol ?? 'UNKNOWN',
    request.timeframe ?? '1d', request.limit ?? (request.bars?.length ?? 500));
  if (request.maxLoops) pine.setMaxLoops(request.maxLoops);
  const context = await pine.run(request.source);
  const plots = serializePlots(context?.plots);
  const trades = serializeTrades(context?.strategy);
  write({
    status: 'ok',
    plots,
    trades,
    signals: context?.alerts ?? null,
    warnings: Array.isArray(context?.warnings) ? context.warnings : [],
    diagnostics: {
      plotCount: Object.keys(plots).length,
      tradeCount: trades.length,
      barCount: request.bars?.length ?? 0,
      initialCapital: context?.strategy?.initial_capital ?? null,
      engine: 'pinets',
    },
  });
} catch (err) {
  write({
    status: 'error',
    code: 'PINE_RUNTIME_ERROR',
    message: err?.message ? String(err.message) : String(err),
    name: err?.name ?? 'Error',
    stack: typeof err?.stack === 'string' ? err.stack.split('\n').slice(0, 12).join('\n') : null,
  });
  process.exit(0);
}
