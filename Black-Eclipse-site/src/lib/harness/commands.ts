// ─── Chat slash commands (profile switches) ──────────────────────────────────
// A leading `/` in a chat message may name a COMMAND. Most commands are routed
// through the shared command executor (`command-router.ts`); a small class of
// PROFILE commands (e.g. `/eclipsesdk`) instead force a deterministic run
// profile — the opposite of the fuzzy classifier in `chat-capability.ts`, which
// infers intent from prose. This module parses the profile-command subset, strips
// it, and names the forced profile; the runtime still enforces the actual grant
// (`code.policy.allowed_tools`), so a command can never widen authority.
//
// The canonical catalog lives in `command-registry.ts`; this module derives its
// profile command list from it so the two can never disagree.
//
// The composer's `/` (command palette) is distinct from the global `/` search
// shortcut, which is bound only when the composer is NOT focused.

import type { TranslationKey } from "@/lib/i18n/types";
import { COMMAND_REGISTRY, type ChatCommandProfile, type CommandSpec } from "./command-registry";

export type { ChatCommandProfile } from "./command-registry";

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

/** Project a registry spec that carries a forced profile into a `ChatCommand`. */
function toChatCommand(spec: CommandSpec): ChatCommand {
  return {
    name: spec.name,
    aliases: spec.aliases,
    summaryKey: spec.summaryKey ?? ("code.command.eclipsesdk" as TranslationKey),
    summary: spec.summary,
    profile: spec.profile as ChatCommandProfile,
  };
}

function isProfileSpec(spec: CommandSpec): boolean {
  return spec.handler.type === "profile" && !!spec.profile;
}

const PROFILE_SPECS = COMMAND_REGISTRY.filter(isProfileSpec);

/** `/eclipsesdk` — build or change something inside Eclipse. */
export const ECLIPSESDK_COMMAND: ChatCommand =
  toChatCommand(PROFILE_SPECS.find((s) => s.name === "eclipsesdk")!);

export const CHAT_COMMANDS: readonly ChatCommand[] = [
  ECLIPSESDK_COMMAND,
  ...PROFILE_SPECS.filter((s) => s.name !== "eclipsesdk").map(toChatCommand),
];

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
 * Parse a leading `/command` from a chat message — but ONLY when it is a profile
 * command. Returns null for ordinary text, for an unknown `/token`, for a
 * non-profile command (those are routed by the command executor), and for a value
 * that only looks like a slash command (a path such as `/usr/bin`). Never throws.
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

/** Look up a profile command by its (case-insensitive) name or alias, or undefined. */
export function findChatCommand(name: string): ChatCommand | undefined {
  const token = (name ?? "").replace(/^\//, "").toLowerCase();
  return CHAT_COMMANDS.find((c) => c.name === token || c.aliases.includes(token));
}
