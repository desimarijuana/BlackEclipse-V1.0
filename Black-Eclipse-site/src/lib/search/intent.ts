// ── Query intent classification ─────────────────────────────────────────────
// Deterministic, rule-based. Decides which resolver path a query takes without
// an LLM. Only genuinely-ambiguous, interrogative, sentence-like queries are
// flagged 'ai' (and even then the engine still falls back to deterministic
// results when no AI is configured).

import type { IntentResult } from './types';

const ACTION_VERBS =
  /^(?:go to|go|open|show|create|add|run|start|new|remove|delete|clear|set|export|import|switch|navigate to|take me to|view)\b/;

const INDICATOR_TERMS = [
  'nfp',
  'cpi',
  'gdp',
  'fomc',
  'pmi',
  'unemployment',
  'inflation',
  'interest rate',
  'rate decision',
  'monetary policy',
  'payroll',
  'jobs data',
  'jobs report',
  'non farm',
  'nonfarm',
];

const USER_TERMS = [
  'my ',
  'my trades',
  'winning trades',
  'losing trades',
  'portfolio performance',
  'my portfolio',
  'my strategy',
  'my setup',
  'my account',
];

const EVENT_TERMS = [
  'economic events',
  'today',
  'this month',
  'this week',
  'tomorrow',
  'upcoming',
  'calendar',
  'next nfp',
  'next fomc',
  'when is',
];

const INTERROGATIVES = /^(what|why|how|which|who|when|where|should|can|will|is|are)\b/;
const SENTENCE_LIKE = /\s{2,}|[.?!,]$/;

function hasAny(text: string, terms: string[]): boolean {
  return terms.some((t) => text.includes(t));
}

export function classifyIntent(raw: string): IntentResult {
  const query = raw.trim();
  const normalized = query.toLowerCase().replace(/\s+/g, ' ');

  // Action verbs win immediately.
  if (ACTION_VERBS.test(normalized)) {
    return { intent: 'action', query, normalized, isNavigation: false };
  }

  // Interrogative, sentence-like → ambiguous; escalate to AI if configured,
  // otherwise the engine falls back to deterministic entity search. Checked
  // before indicator terms so "What data before NFP?" reads as a question,
  // not a plain NFP lookup.
  if (INTERROGATIVES.test(normalized) && SENTENCE_LIKE.test(query)) {
    return { intent: 'ai', query, normalized, isNavigation: false };
  }

  // Event-style ("next nfp", "today's economic events"). Checked before
  // indicator terms because the temporal qualifier ("next", "this month")
  // is the more specific intent signal for the calendar.
  if (hasAny(normalized, EVENT_TERMS) && normalized.length > 6) {
    return { intent: 'event', query, normalized, isNavigation: true };
  }

  // Indicator keywords.
  if (hasAny(normalized, INDICATOR_TERMS)) {
    return { intent: 'indicator', query, normalized, isNavigation: true };
  }

  // User-owned data.
  if (hasAny(normalized, USER_TERMS)) {
    return { intent: 'user', query, normalized, isNavigation: true };
  }

  // Multi-word phrase that isn't clearly anything → treat as data/entity query.
  if (normalized.length >= 2) {
    return { intent: 'entity', query, normalized, isNavigation: true };
  }

  return { intent: 'unknown', query, normalized, isNavigation: false };
}

/** Tokens that should never be treated as a ticker symbol. */
const STOPWORDS = new Set([
  'my', 'the', 'to', 'of', 'in', 'on', 'for', 'a', 'an', 'and', 'or', 'is', 'at',
  'what', 'why', 'how', 'which', 'who', 'when', 'where', 'show', 'open', 'go',
]);

/** Extract a plausible symbol/ticker from a query (uppercased token). */
export function extractSymbol(raw: string): string | undefined {
  const tokens = raw
    .toUpperCase()
    .replace(/\s+/g, ' ')
    .trim()
    .split(' ');
  for (const tok of tokens) {
    if (STOPWORDS.has(tok.toLowerCase())) continue;
    if (tok.length >= 2 && tok.length <= 6 && /^[A-Z][A-Z0-9.=]+$/.test(tok)) {
      return tok;
    }
  }
  return undefined;
}
