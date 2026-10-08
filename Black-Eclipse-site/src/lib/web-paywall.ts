// ── Paywall / login-wall signals ────────────────────────────────────────────
// Shared, deterministic detection of a login-gated or subscription-gated page.
// Publishers commonly answer a crawler with a 200 and a shell that only contains
// "subscribe to continue" / "sign in" — that is NOT evidence of the article, and
// it is NOT the same as a page that simply has no text. This module names it so
// the transport can emit a `paywalled` diagnostic and the research layer can
// escalate to a credentialed browser session instead of fabricating a result.
//
// It deliberately errs toward NOT flagging a normal page: soft login words
// ("sign in") only count when they dominate an otherwise short body, which is the
// shape of a wall, not the shape of an article with a header sign-in link.

export interface PaywallSignal {
  paywalled: boolean;
  /** True when the wall asks for a login rather than a paid subscription. */
  loginGated: boolean;
  /** Short, user-safe reason. */
  reason: string;
}

// Unambiguous subscription/premium markers: enough on their own.
const STRONG_PATTERNS: Array<{ re: RegExp; login: boolean; label: string }> = [
  { re: /subscribe (?:now )?to (?:continue|read|keep reading)/i, login: false, label: "subscription wall" },
  { re: /(?:this (?:article|story|content) is (?:for|available to) (?:subscribers|members))/i, login: false, label: "subscriber-only content" },
  { re: /(?:subscribe|sign ?up) to (?:our|the) newsletter to (?:continue|read)/i, login: false, label: "newsletter wall" },
  { re: /(?:you(?:'ve| have) reached|you have exceeded) your (?:free )?article limit/i, login: false, label: "metered paywall" },
  { re: /(?:become a (?:member|subscriber)|start your (?:free )?trial to (?:read|continue))/i, login: false, label: "membership wall" },
  { re: /(?:premium|subscriber[- ]only|members[- ]only) (?:content|article|story)/i, login: false, label: "premium content" },
  { re: /(?:create (?:a )?free account|register|sign in|log in) to (?:continue|read|keep reading)/i, login: true, label: "login wall" },
  { re: /(?:please )?(?:sign in|log in) (?:to your account )?to (?:view|read|access)/i, login: true, label: "login wall" },
  { re: /access to this (?:page|content) requires (?:a subscription|an account|login)/i, login: true, label: "gated content" },
];

// Weak markers: only meaningful when the extracted body is short (a wall, not an
// article with a sign-in link in the masthead).
const SOFT_RE = /\b(sign in|log in|log-in|subscribe|subscription|register|membership|paywall|premium)\b/i;
const SHORT_BODY_CHARS = 1500;

/**
 * Detect a paywall/login wall from extracted text and/or the raw HTML plus the
 * HTTP status. A 401/402/403 with a small body is treated as gated too.
 */
export function detectPaywall(opts: {
  text?: string | null;
  html?: string | null;
  httpStatus?: number | null;
}): PaywallSignal {
  const text = (opts.text ?? "").trim();
  const html = opts.html ?? "";
  const haystack = text || html.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();

  for (const { re, login, label } of STRONG_PATTERNS) {
    if (re.test(haystack)) {
      return { paywalled: true, loginGated: login, reason: `the page returned a ${label}` };
    }
  }

  // 402 Payment Required is unambiguously a paywall even with an empty body.
  // A 401/403 is NOT sufficient on its own: a bare 403 may be a bot-wall/geo
  // block, not a subscription gate. Those only count when the body carries a
  // login/subscription signal, which the text checks above already catch.
  if (opts.httpStatus === 402) {
    return { paywalled: true, loginGated: false, reason: "the source requires payment (HTTP 402)" };
  }

  if (haystack.length > 0 && haystack.length < SHORT_BODY_CHARS && SOFT_RE.test(haystack)) {
    return { paywalled: true, loginGated: true, reason: "the page body is a login/subscription shell" };
  }

  return { paywalled: false, loginGated: false, reason: "" };
}

export { STRONG_PATTERNS, SOFT_RE, SHORT_BODY_CHARS };
