// ── Standing trading consent ("auto mode") ─────────────────────────────────
// The operator authorizes a bot ONCE. From then on the bot may prepare and renew
// its bounded mandates without retyping a phrase — until the consent expires, is
// revoked, or the bot changes version (an edit invalidates authority elsewhere).
//
// This module is intentionally conservative:
//   * a live consent ALWAYS has an expiry;
//   * a consent covers only the modes and symbols it names;
//   * a request above the agreed limits is NOT covered, even while active;
//   * renewal never widens a limit and never revives a revoked consent.
//
// Consent is not the arm. A live order still needs an armed connection and a
// bot-pinned mandate; consent only removes the repeated phrase step.

import { MAX_SYMBOLS } from "./types";
import type {
  ConsentLimits,
  TradingConsent,
  TradingMode,
} from "./types";

const DAY_MS = 86_400_000;

/** How long a standing consent lasts before the operator must re-grant. */
export const CONSENT_TTL_MS: Record<"demo" | "live", number> = {
  demo: 30 * DAY_MS,
  live: 30 * DAY_MS,
};

/** The mandate TTL a bot may request per mode (server enforces its own cap). */
export const MANDATE_TTL_S: Record<"demo" | "live", number> = {
  demo: 7 * 24 * 60 * 60,
  live: 24 * 60 * 60,
};

export type ConsentStatus = "missing" | "active" | "expired" | "revoked";

export interface ConsentRequest {
  mode: TradingMode;
  symbols: string[];
  maxOrdersPerDay: number;
  maxMarginPerOrder: number;
  maxOpenPositions: number;
}

export interface ConsentCheck {
  covered: boolean;
  status: ConsentStatus;
  /** Why it is not covered, in the words the UI shows. */
  reason: string | null;
  /** The field the operator must fix, when one exists. */
  field: keyof ConsentRequest | "consent" | null;
}

export function normalizeSymbols(symbols: readonly string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of symbols) {
    const symbol = String(raw ?? "").trim().toUpperCase();
    if (!symbol || seen.has(symbol)) continue;
    seen.add(symbol);
    out.push(symbol);
    if (out.length >= MAX_SYMBOLS) break;
  }
  return out;
}

export function normalizeLimits(limits: ConsentLimits): ConsentLimits {
  const symbols = normalizeSymbols(limits.symbols);
  return {
    symbols: symbols.length ? symbols : ["*"],
    maxOrdersPerDay: Math.max(1, Math.min(20, Math.round(limits.maxOrdersPerDay || 1))),
    maxMarginPerOrder: Math.max(0, Number(limits.maxMarginPerOrder) || 0),
    maxOpenPositions: Math.max(1, Math.min(10, Math.round(limits.maxOpenPositions || 1))),
  };
}

export interface GrantInput {
  modes: TradingMode[];
  limits: ConsentLimits;
  phrase: string;
  /** The phrase the server computed; the operator must have typed it. */
  expectedPhrase: string;
  grantedBy?: string;
  autoRenew?: boolean;
  now?: number;
}

export interface GrantResult {
  consent: TradingConsent | null;
  error: string | null;
}

/**
 * Grant a standing consent. The phrase is checked here as a second gate (the
 * server checks it too); it is stored only as proof that it was typed.
 */
export function grantConsent(input: GrantInput): GrantResult {
  const modes = Array.from(new Set(input.modes)).filter(
    (mode): mode is "demo" | "live" => mode === "demo" || mode === "live",
  );
  if (!modes.length) {
    return {
      consent: null,
      error: "Choose at least one execution mode (demo or live) to authorize.",
    };
  }
  if (String(input.phrase ?? "").trim() !== String(input.expectedPhrase ?? "").trim()) {
    return {
      consent: null,
      error: `Type ${input.expectedPhrase || "the consent phrase"} exactly to authorize.`,
    };
  }
  const now = input.now ?? Date.now();
  const ttl = Math.max(...modes.map((mode) => CONSENT_TTL_MS[mode]));
  return {
    consent: {
      version: 1,
      kind: "standing",
      modes,
      grantedAt: new Date(now).toISOString(),
      grantedBy: input.grantedBy ?? "operator",
      expiresAt: new Date(now + ttl).toISOString(),
      revokedAt: null,
      autoRenew: input.autoRenew ?? true,
      limits: normalizeLimits(input.limits),
      phrase: String(input.phrase).trim(),
    },
    error: null,
  };
}

export function consentStatus(
  consent: TradingConsent | null | undefined,
  now: number = Date.now(),
): ConsentStatus {
  if (!consent) return "missing";
  if (consent.revokedAt) return "revoked";
  if (!consent.expiresAt) return consent.modes.includes("live") ? "expired" : "active";
  const expires = new Date(consent.expiresAt).getTime();
  if (!Number.isFinite(expires) || expires <= now) return "expired";
  return "active";
}

/**
 * Does this consent cover the requested execution? Every dimension is checked;
 * the first failure names the field so the UI can point at it.
 */
export function consentCovers(
  consent: TradingConsent | null | undefined,
  request: ConsentRequest,
  now: number = Date.now(),
): ConsentCheck {
  const status = consentStatus(consent, now);
  if (status === "missing") {
    return {
      covered: false,
      status,
      reason: "This bot has no standing consent yet.",
      field: "consent",
    };
  }
  if (status === "revoked") {
    return {
      covered: false,
      status,
      reason: "The operator revoked this bot's trading consent.",
      field: "consent",
    };
  }
  if (status === "expired") {
    return {
      covered: false,
      status,
      reason: "The trading consent expired; re-authorize this bot.",
      field: "consent",
    };
  }
  if (request.mode !== "shadow" && !consent!.modes.includes(request.mode)) {
    return {
      covered: false,
      status,
      reason: `The consent does not cover ${request.mode} execution.`,
      field: "consent",
    };
  }

  const limits = consent!.limits;
  const wanted = normalizeSymbols(request.symbols);
  const all = limits.symbols.includes("*");
  const outside = all
    ? []
    : wanted.filter((symbol) => !limits.symbols.includes(symbol));
  if (outside.length) {
    return {
      covered: false,
      status,
      reason: `The consent does not cover ${outside.join(", ")}.`,
      field: "symbols",
    };
  }
  if (request.maxOrdersPerDay > limits.maxOrdersPerDay) {
    return {
      covered: false,
      status,
      reason: `The consent allows ${limits.maxOrdersPerDay} orders/day, below the requested ${request.maxOrdersPerDay}.`,
      field: "maxOrdersPerDay",
    };
  }
  if (
    limits.maxMarginPerOrder > 0 &&
    request.maxMarginPerOrder > limits.maxMarginPerOrder
  ) {
    return {
      covered: false,
      status,
      reason: `The consent caps margin at ${limits.maxMarginPerOrder} per order.`,
      field: "maxMarginPerOrder",
    };
  }
  if (request.maxOpenPositions > limits.maxOpenPositions) {
    return {
      covered: false,
      status,
      reason: `The consent allows ${limits.maxOpenPositions} open position(s).`,
      field: "maxOpenPositions",
    };
  }
  return { covered: true, status, reason: null, field: null };
}

/** The one question the creation/prepare flow asks: do we need the phrase? */
export function needsPhrase(
  consent: TradingConsent | null | undefined,
  request: ConsentRequest,
  now: number = Date.now(),
): boolean {
  if (request.mode === "shadow") return false;
  return !consentCovers(consent, request, now).covered;
}

/**
 * Renew an expiring consent without asking, but only when the operator enabled
 * auto-renew. A revoked consent can never be renewed.
 */
export function renewConsent(
  consent: TradingConsent,
  now: number = Date.now(),
): TradingConsent | null {
  if (consent.revokedAt || !consent.autoRenew) return null;
  const live = consent.modes.includes("live");
  const ttl = live ? CONSENT_TTL_MS.live : CONSENT_TTL_MS.demo;
  return {
    ...consent,
    expiresAt: new Date(now + ttl).toISOString(),
  };
}

export function revokeConsent(
  consent: TradingConsent | null,
  now: number = Date.now(),
): TradingConsent | null {
  if (!consent) return null;
  return { ...consent, revokedAt: new Date(now).toISOString(), autoRenew: false };
}

/**
 * Tighten the agreed limits. This is the only mutation an operator (or the
 * learning loop, with consent) may make without re-granting: it can only shrink.
 */
export function tightenConsent(
  consent: TradingConsent,
  limits: Partial<ConsentLimits>,
): TradingConsent {
  const current = normalizeLimits(consent.limits);
  const symbols = limits.symbols
    ? normalizeSymbols(limits.symbols)
    : current.symbols;
  const next: ConsentLimits = {
    symbols:
      current.symbols.includes("*") && limits.symbols
        ? symbols.length
          ? symbols
          : current.symbols
        : symbols.filter((symbol) => current.symbols.includes(symbol)),
    maxOrdersPerDay: Math.min(
      current.maxOrdersPerDay,
      Math.max(1, limits.maxOrdersPerDay ?? current.maxOrdersPerDay),
    ),
    maxMarginPerOrder:
      current.maxMarginPerOrder > 0
        ? Math.min(
            current.maxMarginPerOrder,
            limits.maxMarginPerOrder && limits.maxMarginPerOrder > 0
              ? limits.maxMarginPerOrder
              : current.maxMarginPerOrder,
          )
        : Math.max(0, limits.maxMarginPerOrder ?? 0),
    maxOpenPositions: Math.min(
      current.maxOpenPositions,
      Math.max(1, limits.maxOpenPositions ?? current.maxOpenPositions),
    ),
  };
  return { ...consent, limits: normalizeLimits(next) };
}

/** A stable signature for audit + de-duplicating re-grant prompts. */
export function consentSignature(consent: TradingConsent | null): string {
  if (!consent) return "none";
  return [
    consent.kind,
    consent.modes.slice().sort().join(","),
    consent.limits.symbols.slice().sort().join("+") || "*",
    consent.limits.maxOrdersPerDay,
    consent.limits.maxMarginPerOrder,
    consent.limits.maxOpenPositions,
    consent.grantedAt,
  ].join("|");
}

/** The limits a consent should carry from a bot's current envelope. */
export function limitsFromEnvelope(input: {
  symbols: string[];
  maxOrdersPerDay: number;
  maxMarginPerOrder: number;
  maxOpenPositions: number;
}): ConsentLimits {
  return normalizeLimits({
    symbols: input.symbols,
    maxOrdersPerDay: input.maxOrdersPerDay,
    maxMarginPerOrder: input.maxMarginPerOrder,
    maxOpenPositions: input.maxOpenPositions,
  });
}
