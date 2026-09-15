// ── Investor Eye — event classification ──────────────────────────────────────
// Maps an unstructured event (title/summary + provider category) onto the
// normalized vocabulary: event type, severity, economic channels, commodities,
// sectors. Pure and deterministic — no LLM, so the event feed is reproducible
// and testable.
//
// "Economic channel" here means: a transmission route the event plausibly bears
// on (supply chain, energy, trade, rates...). It is a relevance signal derived
// from the words actually present. It is NOT a causal claim, and the UI must
// present it under "potential exposure", never as fact.

import type { EventSeverity, EventType } from './types';

interface Rule {
  type: EventType;
  /** Word-boundary keywords (lower-case) that indicate this type. */
  keywords: string[];
  /** Higher wins ties; the strongest signal in the text classifies the event. */
  weight: number;
}

// Ordered strongest-signal-first. A conflict story mentioning "economy" stays a
// conflict because conflict weight outranks other weight.
const TYPE_RULES: Rule[] = [
  { type: 'conflict', weight: 100, keywords: ['war', 'invasion', 'armed conflict', 'conflict', 'airstrike', 'air strike', 'missile', 'shelling', 'offensive', 'ceasefire', 'front line', 'frontline', 'combat', 'troops', 'military operation', 'insurgency', 'gunmen', 'bombing'] },
  { type: 'military', weight: 90, keywords: ['military drill', 'military exercise', 'naval', 'warship', 'fighter jet', 'deployment', 'defense ministry', 'defence ministry', 'arms deal', 'weapons', 'artillery'] },
  { type: 'sanction', weight: 88, keywords: ['sanction', 'sanctions', 'blacklist', 'asset freeze', 'export control', 'embargo', 'designated entities', 'ofac'] },
  { type: 'tariff', weight: 86, keywords: ['tariff', 'tariffs', 'import duty', 'export duty', 'countervailing', 'anti-dumping', 'anti dumping'] },
  { type: 'trade', weight: 80, keywords: ['trade deal', 'trade agreement', 'trade war', 'trade talks', 'trade dispute', 'export ban', 'import ban', 'supply chain', 'quota', 'wto', 'customs'] },
  { type: 'energy', weight: 78, keywords: ['oil', 'crude', 'opec', 'natural gas', 'lng', 'pipeline', 'refinery', 'drilling', 'energy security', 'power grid', 'electricity price', 'petroleum', 'brent', 'wti'] },
  { type: 'shipping', weight: 76, keywords: ['shipping', 'freight', 'cargo', 'tanker', 'port', 'strait', 'canal', 'vessel', 'maritime', 'container ship', 'logistics', 'red sea', 'hormuz', 'bab el mandeb', 'suez'] },
  { type: 'monetary', weight: 74, keywords: ['interest rate', 'rate hike', 'rate cut', 'central bank', 'federal reserve', 'fed ', 'ecb', 'monetary policy', 'inflation', 'bond purchase', 'quantitative', 'money supply'] },
  { type: 'fiscal', weight: 70, keywords: ['fiscal', 'budget deficit', 'stimulus', 'government spending', 'tax cut', 'tax hike', 'austerity', 'sovereign debt', 'treasury', 'debt ceiling'] },
  { type: 'regulatory', weight: 68, keywords: ['regulator', 'regulation', 'antitrust', 'compliance', 'licensing', 'ban', 'probe', 'investigation', 'fine', 'lawsuit', 'court ruling'] },
  { type: 'election', weight: 66, keywords: ['election', 'vote', 'ballot', 'referendum', 'polls', 'candidate', 'coalition government', 'parliament'] },
  { type: 'protest', weight: 64, keywords: ['protest', 'demonstration', 'strike action', 'unrest', 'riot', 'rally', 'marchers', 'civil unrest'] },
  { type: 'diplomatic', weight: 60, keywords: ['summit', 'diplomat', 'diplomatic', 'talks', 'negotiation', 'treaty', 'ambassador', 'state visit', 'bilateral', 'foreign minister'] },
  { type: 'cyber', weight: 58, keywords: ['cyberattack', 'cyber attack', 'ransomware', 'hacking', 'data breach', 'malware', 'phishing', 'cyber'] },
  { type: 'natural_disaster', weight: 56, keywords: ['earthquake', 'flood', 'flooding', 'hurricane', 'typhoon', 'cyclone', 'wildfire', 'drought', 'tsunami', 'volcano', 'landslide', 'storm'] },
];

const SEVERITY_LEXICON: Record<EventSeverity, string[]> = {
  critical: ['nuclear', 'declares war', 'declaration of war', 'invasion', 'catastrophic', 'mass casualties', 'state of emergency', 'martial law', 'total shutdown', 'collapse', 'meltdown', 'default', 'capitulation'],
  high: ['escalat', 'major', 'significant', 'emergency', 'crisis', 'surge', 'plunge', 'crash', 'sanctions', 'airstrike', 'attack', 'killed', 'dead', 'explosion', 'halt', 'suspend', 'blockade', 'cut off', 'record high', 'record low'],
  medium: ['warning', 'tension', 'concern', 'dispute', 'delay', 'shortage', 'pressure', 'slowdown', 'weaken', 'risk', 'threat', 'fall', 'rise', 'ban', 'probe', 'restrict'],
  low: ['talks', 'meeting', 'proposal', 'review', 'monitor', 'minor', 'slight', 'routine'],
};

// Channel keywords → the economic channel label shown in tooltips.
const CHANNEL_RULES: Array<{ channel: string; keywords: string[] }> = [
  { channel: 'Energy', keywords: ['oil', 'crude', 'gas', 'lng', 'opec', 'pipeline', 'refinery', 'energy', 'brent', 'wti', 'electricity', 'power'] },
  { channel: 'Shipping & Logistics', keywords: ['shipping', 'freight', 'cargo', 'tanker', 'port', 'strait', 'canal', 'vessel', 'maritime', 'logistics', 'container', 'suez', 'hormuz', 'red sea'] },
  { channel: 'Trade & Tariffs', keywords: ['tariff', 'trade', 'export', 'import', 'customs', 'quota', 'embargo', 'sanction', 'supply chain', 'wto'] },
  { channel: 'Semiconductors', keywords: ['semiconductor', 'chip', 'chips', 'foundry', 'tsmc', 'lithography', 'wafer', 'microchip', 'gpu'] },
  { channel: 'Rates & Credit', keywords: ['interest rate', 'central bank', 'yield', 'bond', 'credit', 'monetary', 'inflation', 'fed ', 'ecb', 'treasury', 'debt'] },
  { channel: 'Currency & FX', keywords: ['currency', 'exchange rate', 'devaluation', 'peso', 'lira', 'yuan', 'yen', 'dollar', 'forex', 'fx'] },
  { channel: 'Technology', keywords: ['technology', 'tech', 'software', 'ai ', 'artificial intelligence', 'data center', 'cloud', 'cyber'] },
  { channel: 'Defense & Aerospace', keywords: ['defense', 'defence', 'military', 'weapons', 'arms', 'aerospace', 'missile', 'fighter jet'] },
  { channel: 'Agriculture', keywords: ['wheat', 'grain', 'corn', 'soybean', 'harvest', 'crop', 'fertilizer', 'agriculture', 'food price'] },
  { channel: 'Metals & Mining', keywords: ['copper', 'lithium', 'aluminium', 'aluminum', 'iron ore', 'mining', 'rare earth', 'nickel', 'zinc', 'steel'] },
  { channel: 'Financial Markets', keywords: ['stock', 'equities', 'market', 'shares', 'index', 'ipo', 'earnings', 'valuation'] },
];

const COMMODITY_KEYWORDS: Array<{ name: string; keywords: string[] }> = [
  { name: 'Crude Oil', keywords: ['oil', 'crude', 'brent', 'wti', 'opec', 'petroleum'] },
  { name: 'Natural Gas', keywords: ['natural gas', 'lng', 'henry hub', 'gas pipeline'] },
  { name: 'Gold', keywords: ['gold', 'bullion', 'precious metal'] },
  { name: 'Silver', keywords: ['silver'] },
  { name: 'Copper', keywords: ['copper'] },
  { name: 'Wheat', keywords: ['wheat', 'grain'] },
  { name: 'Corn', keywords: ['corn', 'maize'] },
  { name: 'Lithium', keywords: ['lithium'] },
  { name: 'Rare Earths', keywords: ['rare earth', 'rare-earth'] },
  { name: 'Uranium', keywords: ['uranium'] },
  { name: 'Semiconductors', keywords: ['semiconductor', 'chips', 'chip', 'foundry'] },
];

const SECTOR_KEYWORDS: Array<{ name: string; keywords: string[] }> = [
  { name: 'Energy', keywords: ['oil', 'gas', 'opec', 'refinery', 'energy', 'pipeline'] },
  { name: 'Technology', keywords: ['technology', 'tech', 'software', 'semiconductor', 'chips', 'ai', 'cloud', 'data center'] },
  { name: 'Financials', keywords: ['bank', 'banking', 'lender', 'insurer', 'financial'] },
  { name: 'Industrials', keywords: ['manufacturing', 'industrial', 'factory', 'construction', 'machinery'] },
  { name: 'Materials', keywords: ['mining', 'metals', 'copper', 'steel', 'chemicals'] },
  { name: 'Consumer', keywords: ['retail', 'consumer', 'household', 'e-commerce'] },
  { name: 'Healthcare', keywords: ['pharma', 'healthcare', 'biotech', 'drug', 'vaccine'] },
  { name: 'Utilities', keywords: ['utility', 'utilities', 'power grid', 'electricity'] },
  { name: 'Defense', keywords: ['defense', 'defence', 'military', 'weapons', 'aerospace'] },
  { name: 'Transport', keywords: ['shipping', 'airline', 'rail', 'freight', 'logistics'] },
  { name: 'Agriculture', keywords: ['agriculture', 'farming', 'crop', 'fertilizer'] },
];

function hasWord(haystack: string, keyword: string): boolean {
  // Keywords may be multi-word; a normalized substring check with boundaries.
  const k = keyword.trim().toLowerCase();
  if (!k) return false;
  if (k.includes(' ')) return haystack.includes(k);
  const re = new RegExp(`(^|[^a-z0-9])${k.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}([^a-z0-9]|$)`, 'i');
  return re.test(haystack);
}

function matched(haystack: string, keywords: string[]): string[] {
  return keywords.filter((k) => hasWord(haystack, k));
}

/** Classify the event type. Falls back to 'other' when nothing matches. */
export function classifyType(text: string, providerCategory?: string): EventType {
  const hay = ` ${text.toLowerCase()} `;
  let best: { type: EventType; score: number } | null = null;
  for (const rule of TYPE_RULES) {
    const hits = matched(hay, rule.keywords);
    if (hits.length === 0) continue;
    // Score = rule weight + a small bonus per additional keyword.
    const score = rule.weight + (hits.length - 1) * 2;
    if (!best || score > best.score) best = { type: rule.type, score };
  }
  if (best) return best.type;

  // Provider hints (GDELT's root code, USGS = natural disaster).
  const cat = (providerCategory ?? '').toLowerCase();
  if (cat.includes('earthquake') || cat.includes('natural')) return 'natural_disaster';
  if (cat.includes('trade')) return 'trade';
  if (cat.includes('conflict') || cat.includes('war')) return 'conflict';
  if (cat.includes('energy')) return 'energy';
  return 'other';
}

/** Score severity from the text + event type. */
export function classifySeverity(text: string, eventType: EventType, magnitude?: number): EventSeverity {
  const hay = ` ${text.toLowerCase()} `;
  if (magnitude !== undefined) {
    if (magnitude >= 7) return 'critical';
    if (magnitude >= 6) return 'high';
    if (magnitude >= 4.5) return 'medium';
    return 'low';
  }
  if (matched(hay, SEVERITY_LEXICON.critical).length > 0) return 'critical';
  if (matched(hay, SEVERITY_LEXICON.high).length > 0) return 'high';

  // Type baseline: conflict/military/sanction are inherently above 'low'.
  const base: Record<EventType, EventSeverity> = {
    conflict: 'high', military: 'high', sanction: 'high', tariff: 'medium',
    trade: 'medium', energy: 'medium', shipping: 'medium', monetary: 'medium',
    fiscal: 'medium', regulatory: 'medium', cyber: 'medium', election: 'low',
    protest: 'low', diplomatic: 'low', natural_disaster: 'medium', other: 'low',
  };
  const baseline = base[eventType] ?? 'low';
  if (matched(hay, SEVERITY_LEXICON.medium).length > 0) {
    // A medium phrase cannot downgrade a high-baseline type.
    return baseline === 'high' ? 'high' : 'medium';
  }
  return baseline;
}

export function classifyChannels(text: string): string[] {
  const hay = ` ${text.toLowerCase()} `;
  return CHANNEL_RULES.filter((r) => matched(hay, r.keywords).length > 0).map((r) => r.channel);
}

export function classifyCommodities(text: string): string[] {
  const hay = ` ${text.toLowerCase()} `;
  return COMMODITY_KEYWORDS.filter((r) => matched(hay, r.keywords).length > 0).map((r) => r.name);
}

export function classifySectors(text: string): string[] {
  const hay = ` ${text.toLowerCase()} `;
  return SECTOR_KEYWORDS.filter((r) => matched(hay, r.keywords).length > 0).map((r) => r.name);
}

/** Severity ordering helper for sorting/aggregation. */
export const SEVERITY_RANK: Record<EventSeverity, number> = {
  critical: 3,
  high: 2,
  medium: 1,
  low: 0,
};

/** Numeric severity weight for risk decomposition. */
export function severityWeight(severity: EventSeverity): number {
  return { critical: 1, high: 0.75, medium: 0.45, low: 0.2 }[severity];
}

export const EVENT_TYPES: EventType[] = TYPE_RULES.map((r) => r.type).concat('other');
