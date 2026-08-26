// Shared news-sentiment heuristic.
//
// Single source of truth — previously duplicated (with drifting keyword
// lists) between the news route and the agent tools. Keyword-based scoring
// is intentionally simple; it will be upgraded to model-based scoring when
// the agent phase lands, but every caller must share one implementation.

export type Sentiment = "bullish" | "bearish" | "neutral";

const BULL_WORDS = [
  "surge", "surges", "gain", "gains", "rally", "record", "beat", "beats",
  "up", "jump", "jumps", "soar", "soars", "growth", "bullish", "profit",
  "profits", "upgrade", "upgraded", "outperform", "strong",
];

const BEAR_WORDS = [
  "drop", "drops", "fall", "falls", "decline", "declines", "loss", "losses",
  "miss", "misses", "down", "plunge", "plunges", "slump", "slumps",
  "bearish", "crash", "crashes", "downgrade", "downgraded", "lawsuit",
  "weak", "recession", "bankruptcy",
];

/**
 * Score a headline/summary pair with a keyword vote.
 * Returns "bullish" / "bearish" / "neutral".
 */
export function guessSentiment(text: string): Sentiment {
  // Tokenize so that e.g. "up" inside "startup" or "sup" doesn't count —
  // the old substring match produced false positives on short words.
  const tokens = new Set(text.toLowerCase().split(/[^a-z]+/).filter(Boolean));
  let score = 0;
  for (const w of BULL_WORDS) if (tokens.has(w)) score++;
  for (const w of BEAR_WORDS) if (tokens.has(w)) score--;
  if (score > 0) return "bullish";
  if (score < 0) return "bearish";
  return "neutral";
}
