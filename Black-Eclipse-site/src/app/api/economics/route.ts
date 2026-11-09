import { NextResponse } from "next/server";
import { createHash } from "crypto";
import { prisma } from "@/lib/db";
import { ECON_SOURCES, getSource } from "@/lib/economics/sources";
import { normalizeEconomicSeries, sortByDate, type EconPoint } from "@/lib/economics/fetch";
import { isDataSourceEnabled } from "@/lib/data-source-preferences";
import type { SourceId } from "@/lib/setup/types";

const ECON_PREF_SOURCE: Record<string, SourceId> = {
  fred: "fred",
  worldbank: "worldbank",
  bea: "bea",
  bls: "bls",
  eurostat: "eurostat",
};

export const dynamic = "force-dynamic";

// GET /api/economics?source=<id>&<control>=<value>...
// Normalizes any provider response into { date, value, ...rest } rows, cached
// in-memory (SWR) and persisted to the JDDS MacroSeries vault so repeat visits
// load instantly.
//
// Responses:
//   { source, seriesKey, rows, asOf, cached }
//   { keyRequired: true, keyEnv }       → source needs a key that isn't set
//   { error } with 400/500

const CACHE_TTL_MS = 10 * 60 * 1000;
const cache = new Map<string, { t: number; rows: EconPoint[]; asOf: string | null }>();
const rebuildInFlight = new Set<string>();

function cacheKey(sourceId: string, params: Record<string, string>): string {
  return `${sourceId}:${createHash("sha256").update(JSON.stringify(params)).digest("hex").slice(0, 16)}`;
}

function seriesKey(sourceId: string, params: Record<string, string>): string {
  const meaningful = Object.entries(params)
    .filter(([, v]) => v)
    .map(([k, v]) => `${k}=${v}`)
    .join(",");
  return `${sourceId}${meaningful ? " · " + meaningful : ""}`;
}

async function fetchRows(sourceId: string, params: Record<string, string>): Promise<{ rows: EconPoint[]; asOf: string | null }> {
  const prefId = ECON_PREF_SOURCE[sourceId];
  if (prefId && !(await isDataSourceEnabled(prefId))) {
    const err = new Error(`SOURCE_DISABLED:${sourceId}`);
    (err as Error & { disabled?: boolean; sourceId?: string }).disabled = true;
    (err as Error & { disabled?: boolean; sourceId?: string }).sourceId = sourceId;
    throw err;
  }
  const key = cacheKey(sourceId, params);
  const hit = cache.get(key);
  if (hit && Date.now() - hit.t > CACHE_TTL_MS && !rebuildInFlight.has(key)) {
    // SWR: serve stale instantly, rebuild in the background.
    rebuildInFlight.add(key);
    void fetchFresh(sourceId, params)
      .then((fresh) => { cache.set(key, { t: Date.now(), ...fresh }); })
      .catch((err) => console.error("[api/economics] background rebuild:", err instanceof Error ? err.message : err))
      .finally(() => rebuildInFlight.delete(key));
    return { rows: hit.rows, asOf: hit.asOf };
  }
  if (hit) return { rows: hit.rows, asOf: hit.asOf };

  // Memory miss → try the JDDS vault before hitting the provider.
  try {
    const stored = await prisma.macroSeries.findUnique({ where: { cacheKey: key } });
    if (stored) {
      const rows = JSON.parse(stored.payload) as EconPoint[];
      const age = Date.now() - stored.updatedAt.getTime();
      const entry = { t: stored.updatedAt.getTime(), rows, asOf: rows.length > 0 ? rows[rows.length - 1].date : null };
      cache.set(key, entry);
      if (age > CACHE_TTL_MS && !rebuildInFlight.has(key)) {
        rebuildInFlight.add(key);
        void fetchFresh(sourceId, params)
          .then(async (fresh) => {
            cache.set(key, { t: Date.now(), ...fresh });
            await prisma.macroSeries.update({
              where: { cacheKey: key },
              data: { payload: JSON.stringify(fresh.rows) },
            });
          })
          .catch((err) => console.error("[api/economics] vault refresh:", err instanceof Error ? err.message : err))
          .finally(() => rebuildInFlight.delete(key));
      }
      return { rows, asOf: entry.asOf };
    }
  } catch (err) {
    console.error("[api/economics] vault read error:", err instanceof Error ? err.message : err);
  }

  const fresh = await fetchFresh(sourceId, params);
  cache.set(key, { t: Date.now(), ...fresh });
  // Persist to JDDS (best-effort — never block the response on vault errors).
  try {
    await prisma.macroSeries.upsert({
      where: { cacheKey: key },
      update: { payload: JSON.stringify(fresh.rows), source: sourceId, seriesKey: seriesKey(sourceId, params) },
      create: { cacheKey: key, payload: JSON.stringify(fresh.rows), source: sourceId, seriesKey: seriesKey(sourceId, params) },
    });
  } catch (err) {
    console.error("[api/economics] vault write error:", err instanceof Error ? err.message : err);
  }
  return fresh;
}

async function fetchFresh(sourceId: string, params: Record<string, string>): Promise<{ rows: EconPoint[]; asOf: string | null }> {
  const source = getSource(sourceId);
  if (!source) throw new Error(`Unknown source: ${sourceId}`);
  const prefId = ECON_PREF_SOURCE[sourceId];
  if (prefId && !(await isDataSourceEnabled(prefId))) {
    const err = new Error(`SOURCE_DISABLED:${sourceId}`);
    (err as Error & { disabled?: boolean; sourceId?: string }).disabled = true;
    (err as Error & { disabled?: boolean; sourceId?: string }).sourceId = sourceId;
    throw err;
  }
  if (source.keyRequired && source.keyEnv && !process.env[source.keyEnv]) {
    const err = new Error(`KEY_REQUIRED:${source.keyEnv}`);
    (err as Error & { keyRequired?: boolean; keyEnv?: string }).keyRequired = true;
    (err as Error & { keyEnv?: string }).keyEnv = source.keyEnv;
    throw err;
  }
  const raw = await source.fetch(params);
  const rows = sortByDate(normalizeEconomicSeries(raw, sourceId));
  return { rows, asOf: rows.length > 0 ? rows[rows.length - 1].date : null };
}

// GET /api/economics?source=worldbank&country=US&indicator=NY.GDP.MKTP.CD
export async function GET(request: Request) {
  try {
    const url = new URL(request.url);
    const sourceId = url.searchParams.get("source") || ECON_SOURCES[0].id;
    const source = getSource(sourceId);
    if (!source) {
      return NextResponse.json({ error: `Unknown source: ${sourceId}` }, { status: 400 });
    }
    if (source.keyRequired && source.keyEnv && !process.env[source.keyEnv]) {
      return NextResponse.json({ keyRequired: true, keyEnv: source.keyEnv, source: sourceId });
    }
    const params: Record<string, string> = {};
    for (const control of source.controls) {
      const v = url.searchParams.get(control.name);
      if (v) params[control.name] = v;
      else if (control.defaultValue) params[control.name] = control.defaultValue;
    }
    const { rows, asOf } = await fetchRows(sourceId, params);
    return NextResponse.json({ source: sourceId, seriesKey: seriesKey(sourceId, params), rows, asOf, count: rows.length });
  } catch (err) {
    const e = err as Error & { keyRequired?: boolean; keyEnv?: string; disabled?: boolean; sourceId?: string };
    if (e.keyRequired) {
      return NextResponse.json({ keyRequired: true, keyEnv: e.keyEnv });
    }
    if (e.disabled) {
      return NextResponse.json(
        { disabled: true, source: e.sourceId, error: "This source is disabled in setup." },
        { status: 503 },
      );
    }
    console.error("[api/economics] GET error:", e.message);
    return NextResponse.json({ error: e.message || "Fetch failed" }, { status: 500 });
  }
}