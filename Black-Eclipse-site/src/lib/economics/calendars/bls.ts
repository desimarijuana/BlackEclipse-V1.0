// ── BLS release schedules ──────────────────────────────────────────────────
// Every BLS release page uses the same official schedule table
// (`table.release-list`: Reference Month | Release Date | Release Time). This
// adapter covers the releases the macro calendar needs — CPI, Employment
// Situation, PPI, JOLTS, ECI, Real Earnings, Import/Export Prices and
// Productivity & Costs — and never invents a date when a page is unavailable.

import * as cheerio from "cheerio";
import { safeGet } from "@/lib/connectors/security";
import { OUTBOUND_USER_AGENT } from "@/lib/web-research";
import { MONTHS, MONTHS_SHORT, isoDate, dedupe, type OfficialEvent } from "./types";

const BASE = "https://www.bls.gov/schedule/news_release";

interface BlsSource {
  id: string;
  page: string;
  title: string;
  importance: OfficialEvent["importance"];
}

const BLS_SOURCES: BlsSource[] = [
  { id: "cpi", page: "cpi", title: "US Consumer Price Index (CPI)", importance: "high" },
  { id: "nfp", page: "empsit", title: "US Nonfarm Payrolls (NFP)", importance: "high" },
  { id: "ppi", page: "ppi", title: "US Producer Price Index (PPI)", importance: "high" },
  { id: "jolts", page: "jolts", title: "US JOLTS Job Openings", importance: "medium" },
  { id: "eci", page: "eci", title: "US Employment Cost Index (ECI)", importance: "medium" },
  { id: "real-earnings", page: "realer", title: "US Real Earnings", importance: "medium" },
  { id: "trade-prices", page: "ximpim", title: "US Import/Export Prices", importance: "medium" },
  { id: "productivity", page: "prod2", title: "US Productivity & Costs", importance: "medium" },
];

export function parseBlsSchedule(
  html: string,
  meta: { title: string; url: string; importance?: OfficialEvent["importance"] },
): OfficialEvent[] {
  const $ = cheerio.load(html);
  const events: OfficialEvent[] = [];

  $("table.release-list tbody tr").each((_, row) => {
    const cells = $(row).find("td");
    if (cells.length < 2) return;
    const dateText = cells.eq(1).text().trim();
    const match = dateText.match(/^([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s*(\d{4})/);
    if (!match) return;
    const monthKey = match[1].toLowerCase();
    const month = MONTHS[monthKey] ?? MONTHS_SHORT[monthKey.slice(0, 3)];
    if (month === undefined) return;
    const day = Number(match[2]);
    const year = Number(match[3]);
    if (!Number.isInteger(day) || day < 1 || day > 31) return;
    const time = cells.eq(2).text().trim();
    events.push({
      date: isoDate(year, month, day),
      time: time ? `${time} ET` : null,
      title: meta.title,
      country: "US",
      importance: meta.importance ?? "high",
      confirmed: true,
      url: meta.url,
    });
  });

  return dedupe(events);
}

async function fetchBls(source: BlsSource): Promise<OfficialEvent[]> {
  const url = `${BASE}/${source.page}.htm`;
  const res = await safeGet({
    url,
    headers: { "user-agent": OUTBOUND_USER_AGENT },
    timeoutMs: 10_000,
    maxBytes: 3 * 1024 * 1024,
  });
  if (res.status < 200 || res.status >= 300) throw new Error(`BLS HTTP ${res.status} (${source.id})`);
  return parseBlsSchedule(res.text, {
    title: source.title,
    url,
    importance: source.importance,
  });
}

const CACHE_TTL_MS = 12 * 60 * 60 * 1000;
let cache: { at: number; events: OfficialEvent[] } | null = null;

export async function fetchBlsSchedules(now: () => number = Date.now): Promise<OfficialEvent[]> {
  if (cache && now() - cache.at < CACHE_TTL_MS) return cache.events;

  // One failed page must not blank the other seven.
  const settled = await Promise.allSettled(BLS_SOURCES.map((source) => fetchBls(source)));
  const events = dedupe(
    settled.flatMap((result) => (result.status === "fulfilled" ? result.value : [])),
  );
  if (events.length === 0) throw new Error("every BLS schedule page failed or returned no rows");
  cache = { at: now(), events };
  return events;
}

export function __resetBlsCache(): void {
  cache = null;
}
