// Independent daily-close fallback for markets Stooq covers well (US listings).
// It is deliberately a narrow, keyless CSV reader used only when the primary
// chart provider returns nothing. Stooq is one provider, not an authority.

import type { Bar } from './yahoo-chart';

const STOOQ_BASE = 'https://stooq.com/q/d/l/';
const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';

export function stooqSymbol(symbol: string, market: string): string | null {
  const clean = symbol.trim().toLowerCase();
  if (!clean) return null;
  if (market === 'US') {
    if (clean.startsWith('^')) return clean;
    if (clean.includes('.')) return clean;
    return `${clean}.us`;
  }
  return null;
}

function rangeStart(range: string): string {
  const days = range === '5y' ? 1827 : range === '1y' ? 366 : range === '6mo' ? 183 : 92;
  return new Date(Date.now() - days * 86_400_000).toISOString().slice(0, 10).replace(/-/g, '');
}

export function parseStooqCsv(csv: string): Bar[] {
  const lines = csv.trim().split(/\r?\n/);
  if (lines.length < 2) return [];
  const header = lines[0].toLowerCase();
  if (!header.includes('date') || !header.includes('close')) return [];
  const out: Bar[] = [];
  for (const line of lines.slice(1)) {
    const cols = line.split(',');
    if (cols.length < 5) continue;
    const close = Number(cols[4]);
    if (!Number.isFinite(close) || close <= 0) continue;
    const date = cols[0];
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) continue;
    const open = Number(cols[1]);
    const high = Number(cols[2]);
    const low = Number(cols[3]);
    const volume = Number(cols[5]);
    out.push({
      date,
      open: Number.isFinite(open) ? open : null,
      high: Number.isFinite(high) ? high : null,
      low: Number.isFinite(low) ? low : null,
      close,
      volume: Number.isFinite(volume) ? volume : null,
    });
  }
  return out.sort((a, b) => a.date.localeCompare(b.date));
}

export async function fetchStooqDailySeries(
  symbol: string,
  market: string,
  range: string,
): Promise<Bar[]> {
  const ticker = stooqSymbol(symbol, market);
  if (!ticker) return [];
  const params = new URLSearchParams({
    s: ticker,
    i: 'd',
    d1: rangeStart(range),
    d2: new Date().toISOString().slice(0, 10).replace(/-/g, ''),
  });
  try {
    const res = await fetch(`${STOOQ_BASE}?${params.toString()}`, {
      headers: { 'User-Agent': UA, Accept: 'text/csv,text/plain,*/*' },
      signal: AbortSignal.timeout(12_000),
      cache: 'no-store',
    });
    if (!res.ok) return [];
    const text = await res.text();
    if (!text || /exceeded|no data/i.test(text.slice(0, 200))) return [];
    return parseStooqCsv(text);
  } catch {
    return [];
  }
}
