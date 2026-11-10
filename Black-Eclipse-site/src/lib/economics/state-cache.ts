// ── Last-known-good persistence for slow-moving economy data ────────────────
// Snapshot metrics and the release calendar change slowly. When every provider
// is briefly unreachable, serving the last good answer (clearly marked CACHED)
// is more honest and more useful than a screen full of blanks. Nothing is ever
// mutated or synthesized here — the payload is exactly what a provider returned.

import { prisma } from "@/lib/db";

const KEY_PREFIX = "econ:last-good:";

export interface LastGood<T> {
  savedAt: string;
  data: T;
}

export async function readLastGood<T>(name: string): Promise<LastGood<T> | null> {
  try {
    const row = await prisma.systemConfig.findUnique({ where: { key: `${KEY_PREFIX}${name}` } });
    if (!row?.value) return null;
    const parsed = JSON.parse(row.value) as LastGood<T>;
    if (!parsed || typeof parsed.savedAt !== "string" || parsed.data === undefined) return null;
    return parsed;
  } catch {
    return null;
  }
}

export async function writeLastGood<T>(name: string, data: T): Promise<void> {
  try {
    const value = JSON.stringify({ savedAt: new Date().toISOString(), data });
    await prisma.systemConfig.upsert({
      where: { key: `${KEY_PREFIX}${name}` },
      update: { value },
      create: { key: `${KEY_PREFIX}${name}`, value },
    });
  } catch {
    // Best-effort: persistence must never fail a data response.
  }
}

// ── Plain JSON config (operator-tunable, not a last-good snapshot) ──────────

export async function readJsonConfig<T>(key: string): Promise<T | null> {
  try {
    const row = await prisma.systemConfig.findUnique({ where: { key } });
    if (!row?.value) return null;
    return JSON.parse(row.value) as T;
  } catch {
    return null;
  }
}

export async function writeJsonConfig<T>(key: string, value: T): Promise<void> {
  try {
    const serialized = JSON.stringify(value);
    await prisma.systemConfig.upsert({
      where: { key },
      update: { value: serialized },
      create: { key, value: serialized },
    });
  } catch {
    // Best-effort.
  }
}
