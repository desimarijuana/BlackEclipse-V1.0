// ── Why "Authorize" is blocked ──────────────────────────────────────────────
// One pure rule used by the create panel and the bot's Trading section, so the
// button and the explanation can never disagree. A block is a sentence for the
// operator; `null` means the action may proceed.

export interface AuthorizeCheckInput {
  mode: "shadow" | "demo" | "live";
  tier: "l0" | "l1" | "l2";
  connection?: {
    label?: string;
    status?: string;
    statusReason?: string | null;
    armedUntil?: string | null;
  } | null;
  now?: number;
}

export function authorizeBlockReason(input: AuthorizeCheckInput): string | null {
  if (input.mode === "shadow") return null;
  const connection = input.connection;
  if (!connection) return "Choose the broker connection.";
  if (connection.status === "unavailable") {
    return connection.statusReason
      ? `This broker is unavailable: ${connection.statusReason}`
      : "This broker connection is unavailable.";
  }
  if (input.mode === "live") {
    if (input.tier !== "l2") {
      return "Live execution needs tier L2 first.";
    }
    const until = connection.armedUntil ? new Date(connection.armedUntil).getTime() : 0;
    if (!until || until <= (input.now ?? Date.now())) {
      return "Arm the live connection before authorizing live trading.";
    }
  }
  return null;
}
