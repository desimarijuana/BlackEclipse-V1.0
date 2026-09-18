// Shared news-sentiment heuristic.
//
// Single source of truth — previously duplicated (with drifting keyword
// lists) between the news route and the agent tools.
//
// Scoring model (deterministic, dependency-free, offline):
//   · Weighted keywords — "crash" (-3) outweighs "slip" (-1); intensity
//     matters for net sentiment, a flat ±1 vote drowned strong signals.
//   · Phrase patterns — some words only carry polarity in context. "record"
//     alone is neutral, but "record high" is bullish and "record low" /
//     "record loss" are bearish. Phrases are matched greedily and consume
//     their tokens so a phrase is never double-counted as single words.
//   · Negation handling — "not up", "fails to beat", "no growth" flip the
//     polarity of the word they scope (2-token lookahead). Concessive
//     connectors ("despite", "although") are NOT negators: "shares rise
//     despite weak guidance" is still an up move; treating them as negators
//     inverted otherwise-correct headlines.
//   · A ±1 dead-band returns neutral so single weak words don't classify
//     an otherwise-flat headline.

export type Sentiment = "bullish" | "bearish" | "neutral";

// Intensity-weighted sentiment lexicon.
// NOTE: no zero-valued entries — a key that scores 0 is dead weight and
// silently does nothing (the old list carried four of them).
const BULL_WORDS: Record<string, number> = {
  surge: 3, surges: 3, surged: 3, soar: 3, soars: 3, soared: 3,
  rally: 2, rallies: 2, rallied: 2, jump: 2, jumps: 2, jumped: 2,
  beat: 2, beats: 2,
  gain: 1, gains: 1, gained: 1, up: 1, rise: 1, rises: 1, rose: 1,
  growth: 1, bullish: 2, profit: 1, profits: 1, upgrade: 2, upgraded: 2,
  outperform: 2, outperforms: 2, strong: 2, stronger: 2, boom: 3,
  rebound: 2, rebounds: 2, recover: 2, recovers: 2, recovery: 2,
  expansion: 1, expand: 1, expands: 1, boost: 2, boosts: 2, boosted: 2,
  upbeat: 2, optimism: 2, optimistic: 2, tops: 1, topped: 1,
  breakthrough: 2, exceeds: 2, exceed: 2,
  outperformed: 2, hikes: 1, hike: 1, climbs: 2, climb: 2,
  climbed: 2, advances: 1, advanced: 1, outperformance: 2,
};

const BEAR_WORDS: Record<string, number> = {
  crash: 3, crashes: 3, crashed: 3, plunge: 3, plunges: 3, plunged: 3,
  collapse: 3, collapses: 3, collapsed: 3, meltdown: 3, crisis: 2,
  slump: 2, slumps: 2, slumped: 2, sink: 2, sinks: 2, sank: 2,
  drop: 2, drops: 2, dropped: 2, fall: 2, falls: 2, fell: 2,
  decline: 2, declines: 2, declined: 2, loss: 2, losses: 2, lose: 1, loses: 1,
  miss: 2, misses: 2, missed: 2, down: 1, bearish: 2, downgrade: 2,
  downgraded: 2, lawsuit: 1, sue: 1, sues: 1, fined: 1, probe: 1,
  weak: 2, weaker: 2, weakness: 2, recession: 3, bankruptcy: 3, bankrupt: 3,
  layoffs: 2, layoff: 2, selloff: 3,
  tumble: 2, tumbles: 2, tumbled: 2, slid: 2, slide: 2, slides: 2,
  default: 2, fraud: 3, scandal: 2, warning: 1, warns: 1, warned: 1,
  fear: 1, fears: 1, slowdown: 2, contraction: 2, shrink: 2, shrinks: 2,
  shrinking: 2, cuts: 1, cut: 1, slashes: 2, slash: 2, slashed: 2,
  halts: 2, halted: 2, suspends: 2, suspended: 2, delisted: 2, delisting: 2,
  plunging: 3, tank: 2, tanks: 2, tanked: 2,
};

// Multi-word polarity patterns. Matched over the hyphen-normalized token
// stream; a match consumes its tokens (longest first) so "record high" is
// scored once as a phrase, never again as the bare word "record".
const PHRASES: Record<string, number> = {
  "record high": 3,
  "record low": -3,
  "all time high": 3,
  "all time low": -3,
  "record revenue": 2,
  "record profit": 2,
  "record earnings": 2,
  "record sales": 2,
  "record loss": -3,
  "record losses": -3,
  "record debt": -2,
  "profit warning": -3,
  "guidance cut": -3,
  "cuts guidance": -3,
  "cut guidance": -3,
  "lowers guidance": -3,
  "lowered guidance": -3,
  "raises guidance": 3,
  "raised guidance": 3,
  "raises outlook": 2,
  "cuts outlook": -3,
  "hikes dividend": 2,
  "cuts dividend": -2,
  "beats estimates": 3,
  "beat estimates": 3,
  "misses estimates": -3,
  "missed estimates": -3,
  "margin pressure": -2,
  "short squeeze": 2,
  "sell off": -3,
  "buy back": 1,
  "stock split": 1,
};

// Negation tokens: if one of these precedes a sentiment word within 2 tokens,
// the polarity flips ("not up", "fails to beat", "without growth").
// Concessive connectors are deliberately excluded — see the module header.
const NEGATORS = new Set([
  "not", "no", "never", "without", "fails", "fail", "failed", "failing",
  "denies", "denied", "rejects", "rejected", "avoids", "avoid",
  "cancels", "canceled", "scraps", "scrapped", "delayed",
  "delays", "postpones", "postponed",
]);

const MAX_PHRASE_LEN = 3;

/** Score a headline/summary pair. Returns "bullish" / "bearish" / "neutral". */
export function guessSentiment(text: string): Sentiment {
  // Hyphens/underscores/punctuation all become separators, so "record-breaking"
  // decomposes into "record" + "breaking" and "sell-off" into "sell" + "off"
  // (matched by the "sell off" phrase).
  const tokens = text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .split(" ")
    .filter(Boolean);

  const consumed = new Array<boolean>(tokens.length).fill(false);
  let score = 0;

  // Pass 1 — phrases, longest match first.
  for (let len = MAX_PHRASE_LEN; len >= 2; len--) {
    for (let i = 0; i + len <= tokens.length; i++) {
      if (consumed[i]) continue;
      let blocked = false;
      for (let k = 0; k < len; k++) if (consumed[i + k]) blocked = true;
      if (blocked) continue;
      const key = tokens.slice(i, i + len).join(" ");
      const weight = PHRASES[key];
      if (weight === undefined) continue;
      score += weight;
      for (let k = 0; k < len; k++) consumed[i + k] = true;
    }
  }

  // Pass 2 — single words (skipping tokens already used by a phrase).
  for (let i = 0; i < tokens.length; i++) {
    if (consumed[i]) continue;
    const t = tokens[i];
    const polarity = (BULL_WORDS[t] ?? 0) - (BEAR_WORDS[t] ?? 0);
    if (polarity === 0) continue;
    // Negation lookahead: a negator within the 2 tokens before the word
    // flips its polarity ("not up", "fails to beat", "no recovery").
    const prev1 = tokens[i - 1];
    const prev2 = tokens[i - 2];
    const negated =
      (prev1 !== undefined && NEGATORS.has(prev1)) ||
      (prev2 !== undefined && NEGATORS.has(prev2));
    score += negated ? -polarity : polarity;
  }

  // Dead-band: ±1 is noise ("top" alone, one "down" in a data-heavy headline).
  if (score >= 2) return "bullish";
  if (score <= -2) return "bearish";
  return "neutral";
}
