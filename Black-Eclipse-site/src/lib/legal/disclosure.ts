// ── Canonical risk / AI output disclosure ─────────────────────────────────────
// Client-safe: no Node or Prisma imports, so the same words are used by the
// first-run wizard, the chat surfaces and the server-side acceptance recorder.
//
// Bump RISK_DISCLOSURE_VERSION whenever the substance of the notice changes.
// A stored acceptance only counts for the exact version it names, so the
// wizard re-asks after a material edit (docs/legal/disclosures.md).

export const RISK_DISCLOSURE_VERSION = "2026-11-12";

/**
 * The one-line label shown with every settled AI answer. Short enough to read
 * on every turn, direct without making the product sound unreliable.
 */
export const AI_OUTPUT_LABEL = "AI agent — can be wrong. Verify before you act.";

/**
 * The compact responsibility clause under an answer. One short phrase, not a
 * paragraph: repeating the whole notice every turn causes banner blindness,
 * which weakens the conspicuousness it is meant to create. The full text is
 * always one click away in the expander.
 */
export const AI_OUTPUT_INLINE = "AI agent — can be wrong. Verify before you act.";

/** The full AI-agent statement used by first-run and Settings. */
export const AI_OUTPUT_FULL =
  "Eclipse is an AI agent. It can be wrong — verify the facts and make the call yourself.";

/** The shortest form, kept permanently near the composer. */
export const AI_COMPOSER_NOTICE =
  "AI can be wrong. Not financial advice — verify with your broker.";

/**
 * The company's position in one paragraph. This is the sentence every surface
 * must agree with: the user owns the decision, the account, and the outcome.
 */
export const RESPONSIBILITY_STATEMENT =
  "Eclipse is a self-directed research and order-entry tool. You own the decision, the account, and the outcome. Eclipse does not manage money, guarantee results, or share profits or losses.";

/** The ownership half of the statement, for tight placements. */
export const RESPONSIBILITY_SHORT =
  "You own the decision, the account, and the outcome.";

/**
 * The full notice. Deliberately specific: vague "use at your own risk" wording
 * is weak evidence and is contradicted by the product's own provenance labels.
 */
export const RISK_DISCLOSURE_FULL = [
  RESPONSIBILITY_STATEMENT,
  "Eclipse uses probabilistic AI models and third-party market data. Output can be incomplete, outdated, wrong, or fabricated even when it sounds confident.",
  "It is not investment, tax, legal, or accounting advice, and Eclipse is not your adviser, broker, or fiduciary.",
  "Market data may be delayed or incorrect. Backtests and simulations are hypothetical.",
  "Verify every price, order, and position with your broker before acting. Any order you place is your decision and your responsibility.",
  "You can lose money, including more than you invest where leverage applies. Eclipse does not guarantee results and, to the extent permitted by law, is not liable for losses arising from your use of its output.",
].join(" ");

/** The checkbox text the first-run wizard requires. */
export const RISK_ACK_LABEL =
  "I understand Eclipse is a research and order-entry tool, not my adviser or broker. Its AI can be wrong, and every trade I place is at my own risk.";

/** The responsibility checkbox on a pending order. */
export const TRADE_RESPONSIBILITY_LABEL =
  "I understand this order is my decision and my responsibility. Trading is at my own risk, and I verified the order with my broker.";

/** Shown on the order approval card before anything is sent to the broker. */
export const ORDER_PREVIEW_NOTICE =
  "You are about to send this order to your broker. Check the symbol, side, size, stop and target. The broker may reject, partially fill, or fill at a different price. Eclipse does not guarantee execution.";

/** Shown wherever a broker account is connected or armed. */
export const BROKER_RESPONSIBILITY_NOTICE =
  "Eclipse connects to your broker but never holds your funds. Your broker is the source of truth for orders, fills and positions. Trading is at your own risk.";
