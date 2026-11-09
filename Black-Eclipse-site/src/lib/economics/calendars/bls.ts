// ── BLS release schedule (CPI + Employment Situation) ───────────────────────
// Both pages are the Bureau of Labor Statistics' own schedule tables
// (`table.release-list`: Reference Month | Release Date | Release Time).
// The release date is explicit — no month arithmetic, no guessing.

import * as cheerio from "cheerio";
import { safeGet } from "@/lib/connectors/security";
import { OUTBOUND_USER_AGENT } from "@/lib/web-research";
import { MONTHS, MONTHS_SHORT, isoDate, dedupe, type OfficialEvent } from "./types";

const CPI_URL = "https://www.bls.gov/schedule/news_release/cpi.htm";
const EMP_URL = "https://www.bls.gov/schedule/news_release/empsit.htm";

export function parseBlsSchedule(
  html: string,
  meta: { title: string; url: string },
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
      importance: "high",
      confirmed: true,
      url: meta.url,
    });
  });

  return dedupe(events);
}

async function fetchBls(url: string, title: string): Promise<OfficialEvent[]> {
  const res = await safeGet({
    url,
    headers: { "user-agent": OUTBOUND_USER_AGENT },
    timeoutMs: 10_000,
    maxBytes: 3 * 1024 * 1024,
  });
  if (res.status < 200 || res.status >= 300) throw new Error(`BLS HTTP ${res.status} (${url})`);
  const events = parseBlsSchedule(res.text, { title, url });
  if (events.length === 0) throw new Error(`BLS schedule had no parseable rows (${url})`);
  return events;
}

const CACHE_TTL_MS = 12 * 60 * 60 * 1000;
let cache: { at: number; events: OfficialEvent[] } | null = null;

export async function fetchBlsSchedules(now: () => number = Date.now): Promise<OfficialEvent[]> {
  if (cache && now() - cache.at < CACHE_TTL_MS) return cache.events;
  const [cpi, employment] = await Promise.all([
    fetchBls(CPI_URL, "US Consumer Price Index (CPI)"),
    fetchBls(EMP_URL, "US Nonfarm Payrolls (NFP)"),
  ]);
  const events = dedupe([...cpi, ...employment]);
  cache = { at: now(), events };
  return events;
}

export function __resetBlsCache(): void {
  cache = null;
}
