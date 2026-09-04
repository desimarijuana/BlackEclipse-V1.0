// Shared news-sentiment heuristic.
//
// Single source of truth — previously duplicated (with drifting keyword
// lists) between the news route and the agent tools.
//
// Scoring model:
//   · Weighted keywords — "crash" (-3) outweighs "slip" (-1); intensity
//     matters for net sentiment, a flat ±1 vote drowned strong signals.
//   · Negation handling — "not up", "fails to beat", "no growth" flip the
//     polarity of the word they scope (2-token lookahead).
//   · A ±1 dead-band returns neutral so single weak words don't classify
//     an otherwise-flat headline.

export type Sentiment = "bullish" | "bearish" | "neutral";

// Intensity-weighted sentiment lexicon.
const BULL_WORDS: Record<string, number> = {
  surge: 3, surges: 3, surged: 3, soar: 3, soars: 3, soared: 3, rocket: 3,
  rally: 2, rallies: 2, rallied: 2, jump: 2, jumps: 2, jumped: 2,
  record: 2, "all-time": 2, beat: 2, beats: 2, beatened: 0,
  gain: 1, gains: 1, gained: 1, up: 1, rise: 1, rises: 1, rose: 1,
  growth: 1, bullish: 2, profit: 1, profits: 1, upgrade: 2, upgraded: 2,
  outperform: 2, outperforms: 2, strong: 2, stronger: 2, boom: 3,
  adds: 1, add: 1, rebound: 2, rebounds: 2, recover: 2, recovers: 2, recovery: 2,
  expansion: 1, expand: 1, expands: 1, boost: 2, boosts: 2, boosted: 2,
  upbeat: 2, optimism: 2, optimistic: 2, top: 1, tops: 1, topped: 1,
  beatdown: 0, wins: 1, win: 1, breakthrough: 2, exceeds: 2, exceed: 2,
};

const BEAR_WORDS: Record<string, number> = {
  crash: 3, crashes: 3, crashed: 3, plunge: 3, plunges: 3, plunged: 3,
  collapse: 3, collapses: 3, collapsed: 3, meltdown: 3, crisis: 2,
  slump: 2, slumps: 2, slumped: 2, plungeing: 0, sink: 2, sinks: 2, sank: 2,
  drop: 2, drops: 2, dropped: 2, fall: 2, falls: 2, fell: 2,
  decline: 2, declines: 2, declined: 2, loss: 2, losses: 2, lose: 1, loses: 1,
  miss: 2, misses: 2, missed: 2, down: 1, bearish: 2, downgrade: 2,
  downgraded: 2, lawsuit: 1, sue: 1, sues: 1, fined: 1, probe: 1,
  weak: 2, weaker: 2, weakness: 2, recession: 3, bankruptcy: 3, bankrupt: 3,
  layoffs: 2, layoff: 2, selloff: 3, "sell-off": 3,
  tumble: 2, tumbles: 2, slid: 2, slide: 2, plungees: 0, default: 2,
  fraud: 3, scandal: 2, warning: 1, warns: 1, fear: 1, fears: 1,
  slowdown: 2, contraction: 2, shrink: 2, shrinks: 2, shrinking: 2,
};

// Negation tokens: if one of these precedes a sentiment word within 2 tokens,
// the polarity flips ("not up", "fails to beat", "without growth").
const NEGATORS = new Set([
  "not", "no", "never", "without", "fails", "fail", "failed", "failing",
  "denies", "denied", "rejects", "rejected", "avoids", "avoid", "halts",
  "halted", "ends", "cancels", "canceled", "scraps", "scrapped", "delayed",
  "delays", "postpones", "postponed", "despite", "although", "unless",
]);

/** Score a headline/summary pair. Returns "bullish" / "bearish" / "neutral". */
export function guessSentiment(text: string): Sentiment {
  const tokens = text.toLowerCase().split(/[^a-z&-]+/).filter(Boolean);
  let score = 0;
  for (let i = 0; i < tokens.length; i++) {
    const t = tokens[i];
    const polarity =
      (BULL_WORDS[t] ?? 0) - (BEAR_WORDS[t] ?? 0);
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