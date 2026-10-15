// ─── Agent-turn slash commands ────────────────────────────────────────────────
// Some commands do not execute directly — they rewrite the chat query into a
// directive and let the NORMAL agent turn do the work (preserving streaming and
// conversation history). `/skill` is the first: it tells Eclipse to author a new
// reusable skill. Pure: no clients, no I/O.

import { bindArgs, parseCommandInvocation, tokenizeArgs, type BoundArgs } from "./command-parser";
import type { CommandSpec } from "./command-registry";

export interface AgentCommand {
  /** The canonical command name (e.g. "skill"). */
  command: string;
  /** The rewritten instruction to send to the agent instead of the raw text. */
  instruction: string;
}

type InstructionBuilder = (spec: CommandSpec, args: BoundArgs) => string;

function str(v: unknown): string {
  return typeof v === "string" ? v : "";
}

const BUILDERS: Record<string, InstructionBuilder> = {
  "agent.skill.author": (_spec, args) => {
    const name = str(args.positionals.name).trim();
    const description = (Array.isArray(args.positionals.description) ? (args.positionals.description as string[]) : [])
      .join(" ")
      .trim();
    const category = typeof args.flags.category === "string" ? args.flags.category : "";
    return [
      "Author a new reusable skill for Eclipse itself.",
      "",
      `Skill name: ${name ? `\`${name}\`` : "(not given — choose a short kebab-case name)"}`,
      `What it should do: ${description || "(not given)"}`,
      category ? `Category: ${category}` : "",
      "",
      "Follow this exactly:",
      "1. If the name or what-it-should-do is missing or too vague to build a reusable procedure, ask the",
      "   user for the missing details and STOP — create nothing yet.",
      "2. Otherwise call the `skill_create` tool with: a short kebab-case id and name, a one-line",
      "   description, concise step-by-step instructions, the category, the MINIMAL required tools and",
      "   permissions, and an input schema if the skill takes inputs. Never request broad permissions.",
      "3. `skill_create` requires a single-use operator approval: say you are asking for approval before",
      "   you call it.",
      "4. After the tool result confirms creation, tell the user the skill id and that it is now on the",
      "   Skills page, where they can view, edit, enable, or run it. Never claim a skill was created",
      "   unless the tool result confirms it.",
    ]
      .filter((line) => line !== "")
      .join("\n");
  },
};

/**
 * If `text` is a leading `/command` whose handler is an agent turn, return the
 * command name and the rewritten instruction. Otherwise null (ordinary text, an
 * unknown token, or a directly-executed command).
 */
export function buildAgentInstruction(text: string | null | undefined): AgentCommand | null {
  const invocation = parseCommandInvocation(text);
  if (!invocation?.spec || invocation.spec.handler.type !== "agent") return null;
  const builder = BUILDERS[invocation.spec.handler.target];
  if (!builder) return null;
  const args = bindArgs(invocation.spec, tokenizeArgs(invocation.rest));
  return { command: invocation.spec.name, instruction: builder(invocation.spec, args) };
}
