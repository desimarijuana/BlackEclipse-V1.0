// Portfolio alert evaluation — server-side.
// Guest portfolios live in localStorage, so alerts can't be read on the
// server directly. Clients POST their alert ledger to /api/portfolio-alerts;
// this module evaulates every registered alert against live JDDS prices each
// scheduler tick and persists trigger state, so alerts fire even when the
// user's tab is closed. Clients poll GET to surface triggered alerts on return.

import { prisma } from "@/lib/db";

export interface StoredAlert {
  id: string;
  symbol: string;
  type: "PRICE_ABOVE" | "PRICE_BELOW" | "DAILY_MOVE";
  target: number;
  isActive: boolean;
}

const REG_KEY = "portfolio_alert_registry";

export async function getRegisteredAlerts(): Promise<Record<string, StoredAlert[]>> {
  try {
    const row = await prisma.systemConfig.findUnique({ where: { key: REG_KEY } });
    if (row?.value) return JSON.parse(row.value);
  } catch { /* ignore */ }
  return {};
}

export async function setRegisteredAlerts(reg: Record<string, StoredAlert[]>) {
  await prisma.systemConfig.upsert({
    where: { key: REG_KEY },
    update: { value: JSON.stringify(reg) },
    create: { key: REG_KEY, value: JSON.stringify(reg) },
  });
}

/** Evaluate every active registered alert against live prices. */
export async function evaluatePortfolioAlerts() {
  const registry = await getRegisteredAlerts();
  const clientIds = Object.keys(registry);
  if (clientIds.length === 0) return;

  const symbols = new Set<string>();
  for (const list of Object.values(registry)) {
    for (const a of list) if (a.isActive) symbols.add(a.symbol);
  }
  if (symbols.size === 0) return;

  // Live prices in one DB read.
  const prices = await prisma.price.findMany({
    where: { asset: { symbol: { in: [...symbols] }, isActive: true } },
    select: { price: true, previousClose: true, asset: { select: { symbol: true } } },
  });
  const priceMap = new Map<string, { price: number; previousClose: number | null }>();
  for (const p of prices) {
    if (p.price > 0) priceMap.set(p.asset.symbol, { price: p.price, previousClose: p.previousClose });
  }

  let dirty = false;
  for (const clientId of clientIds) {
    const alerts = registry[clientId];
    for (const a of alerts) {
      if (!a.isActive) continue;
      const q = priceMap.get(a.symbol);
      if (!q) continue;
      const move = q.previousClose && q.previousClose > 0
        ? Math.abs((q.price / q.previousClose - 1) * 100)
        : 0;
      const triggered =
        a.type === "PRICE_ABOVE" ? q.price >= a.target
        : a.type === "PRICE_BELOW" ? q.price <= a.target
        : move > a.target;
      // Record first crossing only (sticky trigger until client clears it).
      const key = `${a.id}_triggered` as keyof typeof alerts[number];
      const mark = alerts.find(x => x.id === `${a.id}_triggered`);
      if (triggered && !mark) {
        alerts.push({ ...a, id: `${a.id}_triggered`, isActive: false, target: 0, symbol: a.symbol, type: a.type });
        dirty = true;
        console.log(`[Alerts] TRIGGERED ${a.type} ${a.symbol} @ ${q.price} (target ${a.target})`);
      } else if (!triggered && mark) {
        registry[clientId] = alerts.filter(x => x.id !== mark.id);
        dirty = true;
      }
    }
  }
  if (dirty) await setRegisteredAlerts(registry);
}