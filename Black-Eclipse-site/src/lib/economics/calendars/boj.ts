// ── Bank of Japan Monetary Policy Meeting dates ─────────────────────────────
// `boj.or.jp/en/mopo/mpmsche_minu/index.htm` lists meetings under
// `<h2 id="p2026">2026</h2>` tables. A meeting is announced as a two-day range
// ("Jan. 22 (Thurs.), 23 (Fri.)"); the decision lands on the final day.

import * as cheerio from "cheerio";
import { safeGet } from "@/lib/connectors/security";
import { OUTBOUND_USER_AGENT } from "@/lib/web-research";
import { MONTHS_SHORT, isoDate, dedupe, type OfficialEvent } from "./types";

const BOJ_URL = "https://www.boj.or.jp/en/mopo/mpmsche_minu/index.htm";

export function parseBojSchedule(html: string, url = BOJ_URL): OfficialEvent[] {
  const $ = cheerio.load(html);
  const events: OfficialEvent[] = [];

  $("h2[id]").each((_i, heading) => {
    const yearMatch = $(heading).text().trim().match(/^(20\d{2})$/);
    if (!yearMatch) return;
    const year = Number(yearMatch[1]);
    const scope = $(heading).nextUntil("h2");
    const direct = scope.filter("table").first();
    const table = direct.length > 0 ? direct : scope.find("table").first();
    if (table.length === 0) return;

    table.find("tbody tr").each((_r, row) => {
      const cell = $(row).find("td").first();
      if (cell.length === 0) return;
      const text = cell.text().replace(/\s+/g, " ").trim();
      // "Jan. 22 (Thurs.), 23 (Fri.) [PDF ...]" — the date part is before the
      // PDF marker; the final day number is the decision day.
      const datePart = text.split("[")[0];
      const monthMatch = datePart.match(/([A-Z][a-z]{2})\.?/);
      if (!monthMatch) return;
      const month = MONTHS_SHORT[monthMatch[1].toLowerCase()];
      const days = [...datePart.matchAll(/\b(\d{1,2})\b/g)].map((m) => Number(m[1]));
      if (month === undefined || days.length === 0) return;
      const day = days[days.length - 1];
      if (day < 1 || day > 31) return;

      events.push({
        date: isoDate(year, month, day),
        time: null,
        title: "BoJ Policy Rate Decision",
        country: "JP",
        importance: "high",
        confirmed: true,
        url,
      });
    });
  });

  return dedupe(events);
}

const CACHE_TTL_MS = 12 * 60 * 60 * 1000;
let cache: { at: number; events: OfficialEvent[] } | null = null;

export async function fetchBojSchedule(now: () => number = Date.now): Promise<OfficialEvent[]> {
  if (cache && now() - cache.at < CACHE_TTL_MS) return cache.events;
  const res = await safeGet({
    url: BOJ_URL,
    headers: { "user-agent": OUTBOUND_USER_AGENT },
    timeoutMs: 10_000,
    maxBytes: 3 * 1024 * 1024,
  });
  if (res.status < 200 || res.status >= 300) throw new Error(`BoJ HTTP ${res.status}`);
  const events = parseBojSchedule(res.text);
  if (events.length === 0) throw new Error("BoJ page had no parseable MPM dates");
  cache = { at: now(), events };
  return events;
}

export function __resetBojCache(): void {
  cache = null;
}
