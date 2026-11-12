// ── Money guardrails client ──────────────────────────────────────────────────
// Client-safe: talks only to the Next.js `/api/finance-guardrails/*` front door,
// which proxies to the operator-gated Python routes. No Node APIs.

export interface MoneyGuardrailConfig {
  mode: "off" | "guard" | "strict";
  perTxnCap: number;
  dailyCap: number;
  velocityPerHour: number;
  baselineMultiplier: number;
  coolingSeconds: number;
  highValue: number;
  impairedMode: boolean;
  crisisMode: boolean;
  panicPaused: boolean;
  trustedContact: string;
  allowlist: string[];
  blocklist: string[];
  updatedAt: string;
}

export interface MoneyGuardrailAggregates {
  spendToday: number;
  spend30d: number;
  countLastHour: number;
  baselineP95: number | null;
  recentAmounts: number[];
}

export interface MoneyGuardrailIntentRecord {
  id: string;
  action: string;
  amount: number | null;
  currency: string | null;
  counterparty: string | null;
  instrument: string | null;
  decision: string;
  reasons: string[];
  rules: string[];
  risk: string | null;
  createdAt: string;
}

export interface MoneyGuardrailStatus {
  available: boolean;
  config: MoneyGuardrailConfig;
  aggregates: MoneyGuardrailAggregates;
  recent: MoneyGuardrailIntentRecord[];
}

export interface MoneyGuardrailVerdict {
  decision: "allow" | "confirm" | "deny" | "escalate";
  reasons: string[];
  rules: string[];
  risk: string;
  coolingOffSeconds: number;
  requiresTypedConfirmation: boolean;
  confirmPhrase: string;
  escalateTo: string | null;
}

async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init.headers ?? {}) },
  });
  const body = (await res.json().catch(() => ({}))) as T & { error?: string; detail?: string };
  if (!res.ok) throw new Error(body.error ?? body.detail ?? `request failed (${res.status})`);
  return body;
}

export async function getMoneyGuardrailStatus(limit = 25): Promise<MoneyGuardrailStatus> {
  return api<MoneyGuardrailStatus>(`/api/finance-guardrails/status?limit=${limit}`);
}

export async function updateMoneyGuardrailConfig(
  patch: Partial<MoneyGuardrailConfig>,
): Promise<MoneyGuardrailConfig> {
  const body = await api<{ config: MoneyGuardrailConfig }>("/api/finance-guardrails/config", {
    method: "PUT",
    body: JSON.stringify(patch),
  });
  return body.config;
}

export async function evaluateMoneyIntent(payload: {
  action: string;
  amount?: number;
  currency?: string;
  counterparty?: string;
  instrument?: string;
  account?: string;
  channel?: string;
  text?: string;
}): Promise<MoneyGuardrailVerdict> {
  const body = await api<{ verdict: MoneyGuardrailVerdict }>("/api/finance-guardrails/evaluate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return body.verdict;
}
