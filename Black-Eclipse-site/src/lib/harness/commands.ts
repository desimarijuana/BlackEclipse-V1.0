// ─── Chat slash commands (Eclipse's first command) ────────────────────────────
// A leading `/` in a chat message may name a COMMAND. A command is a
// deterministic, user-invoked switch that forces a run profile — the opposite of
// the fuzzy classifier in `chat-capability.ts`, which infers intent from prose.
// The front door parses the command here, strips it, and sends the remainder as
// the run's instruction together with the forced profile.
//
// This module owns NO agentic logic: it parses a token and names a profile. The
// runtime still enforces the actual grant (`code.policy.allowed_tools`), so a
// command can never widen authority — it only selects the code path explicitly.
//
// The composer's `/` (command palette) is distinct from the global `/` search
// shortcut, which is bound only when the composer is NOT focused.

import type { TranslationKey } from "@/lib/i18n/types";

export interface ChatCommandProfile {
  /** The autonomy profile this command forces for the turn. */
  autonomy: "plan_only" | "edit_verify";
  /** Whether the analysis sandbox is enabled for the turn. */
  analysisEnabled: boolean;
}

export interface ChatCommand {
  /** Canonical name, no leading slash, lowercase. */
  name: string;
  /** Additional accepted names, no slash, lowercase. */
  aliases: readonly string[];
  /** i18n key for the one-line description shown in the palette / badge. */
  summaryKey: TranslationKey;
  /** Plain-English fallback (server-side / tests); the UI uses `summaryKey`. */
  summary: string;
  /** The profile forced for a turn that invokes this command. */
  profile: ChatCommandProfile;
}

/**
 * `/eclipsesdk` — build or change something inside Eclipse.
 *
 * Forces the chat code profile (`edit_verify`: read + write + execute, no
 * external action) and the analysis sandbox, so a self-edit request is served by
 * the code capability instead of the finance surface. Case-insensitive.
 */
export const ECLIPSESDK_COMMAND: ChatCommand = {
  name: "eclipsesdk",
  aliases: ["esdk"],
  summaryKey: "code.command.eclipsesdk",
  summary: "Build or change something inside Eclipse.",
  profile: { autonomy: "edit_verify", analysisEnabled: true },
};

export const CHAT_COMMANDS: readonly ChatCommand[] = [ECLIPSESDK_COMMAND];

/** The instruction sent when a command carries no text after it. */
export const COMMAND_EMPTY_INSTRUCTION =
  "Tell me what you'd like to build or change inside Eclipse.";

export interface ParsedChatCommand {
  command: ChatCommand;
  /** The text after the command token, trimmed (may be empty). */
  instruction: string;
  /** What to send as the run's query: the instruction, or a clarifying default. */
  query: string;
}

/**
 * Parse a leading `/command` from a chat message.
 *
 * Returns null for ordinary text, for an unknown `/token`, and for a value that
 * only looks like a slash command (a path such as `/usr/bin` — the token must be
 * followed by whitespace or end-of-message). Never throws.
 */
export function parseChatCommand(text: string | null | undefined): ParsedChatCommand | null {
  const match = /^\s*\/([A-Za-z][A-Za-z0-9_-]*)(?:\s+([\s\S]*))?$/.exec(text ?? "");
  if (!match) return null;
  const token = match[1].toLowerCase();
  const command = CHAT_COMMANDS.find((c) => c.name === token || c.aliases.includes(token));
  if (!command) return null;
  const instruction = (match[2] ?? "").trim();
  return { command, instruction, query: instruction || COMMAND_EMPTY_INSTRUCTION };
}

/** Look up a command by its (case-insensitive) name or alias, or undefined. */
export function findChatCommand(name: string): ChatCommand | undefined {
  const token = (name ?? "").replace(/^\//, "").toLowerCase();
  return CHAT_COMMANDS.find((c) => c.name === token || c.aliases.includes(token));
}
