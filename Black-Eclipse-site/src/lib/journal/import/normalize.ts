// ── Import Normalization Layer ────────────────────────────────────────────────
// Converts raw broker/exchange trade exports (MT4, MT5, Binance, Coinbase,
// generic CSV) into the normalized BlackEclipse CreateTradeInput shape.
// The journal schema never depends on any single broker — this layer is the
// single place that maps external formats to the internal model.

import type { CreateTradeInput } from "../data";

export type ImportFormat = "generic" | "mt4" | "mt5" | "binance" | "coinbase";

export interface ImportFormatMeta {
  id: ImportFormat;
  label: string;
  description: string;
  /** Example header row for the template download. */
  templateHeader: string;
  /** Example data row for the template download. */
  templateRow: string;
}

export const IMPORT_FORMATS: ImportFormatMeta[] = [
  {
    id: "generic",
    label: "Generic / BlackEclipse",
    description: "symbol, direction, entry, exit, stopLoss, takeProfit, quantity, entryTime, exitTime, session, timeframe, emotion, confidence, notes",
    templateHeader: "symbol,direction,entry,exit,stopLoss,takeProfit,quantity,entryTime,exitTime,session,timeframe,emotion,confidence,notes",
    templateRow: "XAUUSD,LONG,2650.5,2662.0,2648.0,2680.0,1,2026-09-01 09:30,2026-09-01 10:00,New York,15m,Calm,4,Followed the plan",
  },
  {
    id: "mt4",
    label: "MetaTrader 4",
    description: "MT4 'History' export: Ticket, Open Time, Type, Size, Item, Price, S/L, T/P, Close Time, Price, Commission, Taxes, Swap, Profit",
    templateHeader: "Ticket,Open Time,Type,Size,Item,Price,S/L,T/P,Close Time,Price,Commission,Taxes,Swap,Profit",
    templateRow: "123456,2026.09.01 09:30,buy,1.00,xauusd,2650.50,2648.00,2680.00,2026.09.01 10:00,2662.00,0.00,0.00,0.00,11.50",
  },
  {
    id: "mt5",
    label: "MetaTrader 5",
    description: "MT5 'History' export: Ticket, Time, Type, Volume, Symbol, Price, S/L, T/P, Time, Price, Commission, Swap, Profit",
    templateHeader: "Ticket,Time,Type,Volume,Symbol,Price,S/L,T/P,Time,Price,Commission,Swap,Profit",
    templateRow: "123456,2026.09.01 09:30,buy,1.00,XAUUSD,2650.50,2648.00,2680.00,2026.09.01 10:00,2662.00,0.00,0.00,11.50",
  },
  {
    id: "binance",
    label: "Binance",
    description: "Binance futures trade history: Symbol, Side, Price, Qty, Realized PnL, Time",
    templateHeader: "Symbol,Side,Price,Qty,Realized PnL,Time",
    templateRow: "BTCUSDT,BUY,64000.0,0.1,120.5,2026-09-01 09:30:00",
  },
  {
    id: "coinbase",
    label: "Coinbase",
    description: "Coinbase fills: trade_id, product_id, side, size, price, created_at",
    templateHeader: "trade_id,product_id,side,size,price,created_at",
    templateRow: "123456,BTC-USD,BUY,0.1,64000.0,2026-09-01 09:30:00",
  },
];

/** Detect the import format from a CSV header row. */
export function detectFormat(header: string[]): ImportFormat {
  const h = header.map((x) => x.trim().toLowerCase());
  const joined = h.join(",");

  if (h.includes("ticket") && h.includes("open time") && h.includes("close time")) return "mt4";
  if (h.includes("ticket") && h.includes("time") && h.includes("volume") && h.includes("symbol")) return "mt5";
  if (h.includes("symbol") && h.includes("side") && h.includes("realized pnl")) return "binance";
  if (h.includes("product_id") && h.includes("side") && h.includes("created_at")) return "coinbase";
  if (joined.includes("entry") && joined.includes("exit")) return "generic";

  return "generic";
}

/** Normalize a raw CSV row (keyed by lowercased header) into CreateTradeInput. */
export function normalizeRow(format: ImportFormat, r: Record<string, string>): CreateTradeInput | null {
  switch (format) {
    case "mt4":
    case "mt5":
      return normalizeMt(r);
    case "binance":
      return normalizeBinance(r);
    case "coinbase":
      return normalizeCoinbase(r);
    case "generic":
    default:
      return normalizeGeneric(r);
  }
}

// ── Generic / BlackEclipse format ────────────────────────────────────────────

function normalizeGeneric(r: Record<string, string>): CreateTradeInput | null {
  const num = (v: string | undefined) => (v && v !== "" ? Number(v) : undefined);
  const str = (v: string | undefined) => (v && v !== "" ? v : undefined);
  const direction = (r.direction || r.dir || "").toUpperCase();
  if (direction !== "LONG" && direction !== "SHORT") return null;
  const entry = num(r.entry);
  const exit = num(r.exit);
  if (entry == null || exit == null) return null;
  const entryTime = normalizeTime(r.entrytime || r.entry_time || r.entryTime);
  const exitTime = normalizeTime(r.exittime || r.exit_time || r.exitTime);
  if (!entryTime || !exitTime) return null;
  return {
    symbol: (r.symbol || "").toUpperCase(),
    direction,
    entry,
    exit,
    stopLoss: num(r.stoploss || r.stop_loss) ?? null,
    takeProfit: num(r.takeprofit || r.take_profit) ?? null,
    quantity: num(r.quantity || r.qty) ?? 1,
    entryTime,
    exitTime,
    session: str(r.session),
    timeframe: str(r.timeframe || r.tf),
    emotion: str(r.emotion),
    confidence: num(r.confidence) ?? null,
    notes: str(r.notes),
  };
}

// ── MetaTrader 4 / 5 ──────────────────────────────────────────────────────────

function normalizeMt(r: Record<string, string>): CreateTradeInput | null {
  const num = (v: string | undefined) => (v && v !== "" ? Number(v) : undefined);
  const type = (r.type || "").toLowerCase();
  // MT: buy/sell (or buy_limit/sell_limit etc). Only market/closed trades import.
  if (!type.includes("buy") && !type.includes("sell")) return null;
  const direction = type.includes("buy") ? "LONG" : "SHORT";
  const entry = num(r.price);
  const exit = num(r["price.1"] || r.price_1 || r.close_price);
  if (entry == null || exit == null) return null;
  const entryTime = normalizeMtTime(r["open time"] || r.time);
  const exitTime = normalizeMtTime(r["close time"] || r["time.1"] || r.time_1);
  if (!entryTime || !exitTime) return null;
  const symbol = (r.item || r.symbol || "").toUpperCase();
  if (!symbol) return null;
  return {
    symbol,
    direction,
    entry,
    exit,
    stopLoss: num(r["s/l"] || r.sl) ?? null,
    takeProfit: num(r["t/p"] || r.tp) ?? null,
    quantity: num(r.size || r.volume) ?? 1,
    entryTime,
    exitTime,
    notes: r.profit ? `Profit: ${r.profit}` : undefined,
  };
}

// ── Binance ───────────────────────────────────────────────────────────────────

function normalizeBinance(r: Record<string, string>): CreateTradeInput | null {
  const num = (v: string | undefined) => (v && v !== "" ? Number(v) : undefined);
  const side = (r.side || "").toUpperCase();
  if (side !== "BUY" && side !== "SELL") return null;
  const price = num(r.price);
  const qty = num(r.qty);
  if (price == null || qty == null) return null;
  const time = normalizeTime(r.time);
  if (!time) return null;
  return {
    symbol: (r.symbol || "").toUpperCase(),
    direction: side === "BUY" ? "LONG" : "SHORT",
    entry: price,
    exit: price, // Binance fills don't carry an exit; use entry as placeholder
    quantity: qty,
    entryTime: time,
    exitTime: time,
    notes: r["realized pnl"] ? `Realized PnL: ${r["realized pnl"]}` : undefined,
  };
}

// ── Coinbase ─────────────────────────────────────────────────────────────────

function normalizeCoinbase(r: Record<string, string>): CreateTradeInput | null {
  const num = (v: string | undefined) => (v && v !== "" ? Number(v) : undefined);
  const side = (r.side || "").toUpperCase();
  if (side !== "BUY" && side !== "SELL") return null;
  const price = num(r.price);
  const size = num(r.size);
  if (price == null || size == null) return null;
  const time = normalizeTime(r.created_at);
  if (!time) return null;
  return {
    symbol: (r.product_id || "").toUpperCase(),
    direction: side === "BUY" ? "LONG" : "SHORT",
    entry: price,
    exit: price,
    quantity: size,
    entryTime: time,
    exitTime: time,
  };
}

// ── Time helpers ─────────────────────────────────────────────────────────────

/** Normalize a time string to ISO. Accepts ISO, "YYYY-MM-DD HH:MM", MT "YYYY.MM.DD HH:MM". */
function normalizeTime(v: string | undefined): string | null {
  if (!v) return null;
  const t = v.trim();
  if (!t) return null;
  // MT format: 2026.09.01 09:30
  const mt = t.match(/^(\d{4})\.(\d{2})\.(\d{2})[ T](\d{2}:\d{2})/);
  if (mt) return new Date(`${mt[1]}-${mt[2]}-${mt[3]}T${mt[4]}:00`).toISOString();
  // "YYYY-MM-DD HH:MM"
  const m = t.match(/^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2})/);
  if (m) return new Date(`${m[1]}T${m[2]}:00`).toISOString();
  const d = new Date(t);
  return Number.isNaN(d.getTime()) ? null : d.toISOString();
}

function normalizeMtTime(v: string | undefined): string | null {
  return normalizeTime(v);
}
