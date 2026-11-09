// ── Canonical risk / AI output disclosure ───────────────────────────────────
// Client-safe: no Node or Prisma imports, so the same words are used by the
// first-run wizard, the chat surfaces and the server-side acceptance recorder.
//
// Bump RISK_DISCLOSURE_VERSION whenever the substance of the notice changes.
// A stored acceptance only counts for the exact version it names, so the
// wizard re-asks after a material edit (docs/legal/disclosures.md).

export const RISK_DISCLOSURE_VERSION = "2026-11-09";

/** The one-line label shown with every settled AI answer. */
export const AI_OUTPUT_LABEL = "AI-generated · not financial advice";

/** The compact sentence under an answer (expandable to the full notice). */
export const AI_OUTPUT_SHORT =
  "Output can be wrong, outdated or incomplete. Verify prices, orders and positions with your broker before acting. You are responsible for your decisions.";

/** The shortest form, kept permanently near the composer. */
export const AI_COMPOSER_NOTICE =
  "AI can be wrong. Not financial advice — verify with your broker.";

/**
 * The full notice. Deliberately specific: vague "use at your own risk" wording
 * is weak evidence and is contradicted by the product's own provenance labels.
 */
export const RISK_DISCLOSURE_FULL = [
  "Eclipse uses probabilistic AI models and third-party market data. Output can be incomplete, outdated, wrong, or fabricated even when it sounds confident.",
  "It is not investment, tax, legal, or accounting advice, and Eclipse is not your adviser, broker, or fiduciary.",
  "Market data may be delayed or incorrect. Backtests and simulations are hypothetical.",
  "Verify every price, order, and position with your broker before acting. Any order you place is your decision and your responsibility.",
  "You can lose money, including more than you invest where leverage applies. Eclipse does not guarantee results and, to the extent permitted by law, is not liable for losses arising from your use of its output.",
].join(" ");

/** The checkbox text the first-run wizard requires. */
export const RISK_ACK_LABEL =
  "I understand Eclipse is not my adviser or broker, its output can be wrong, and my financial decisions are my own responsibility.";
