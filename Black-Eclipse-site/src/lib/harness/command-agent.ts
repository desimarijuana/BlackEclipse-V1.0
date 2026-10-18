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
  "agent.anatomy": (_spec, args) => {
    const subject = (Array.isArray(args.positionals.subject) ? (args.positionals.subject as string[]) : [])
      .join(" ")
      .trim();
    const audience = typeof args.flags.audience === "string" ? args.flags.audience : "";
    const animated = args.flags.animated === true;
    return [
      "Explain the following as ONE interactive 3D mechanism model, rendered inline in chat as a `model3d` block (the /anatomy 3D figure):",
      "",
      `Subject: ${subject || "(not given — ask the user what to illustrate and STOP, building nothing yet)"}`,
      audience ? `Audience: ${audience}` : "",
      "",
      "Follow this exactly:",
      "1. Consult `response_block_schema` for the `model3d` block and use its EXACT field names; a drifted field degrades the model.",
      "2. Author a SCENE, never meshes, shaders or code. `parts[]` — each with an id, a placement (`position`/`rotation`/`scale`),",
      "   an optional `parent` for assemblies, `material`/`tone`/`lit`/`label`, and geometry: either a `kind` or a `recipe`.",
      "   KINDS: `box` · `cylinder` · `cone` · `sphere` · `torus` · `lathe` (a `profile` of `[z, radius]` pairs) · `extrude`",
      "   (a `points` polygon) · `tube` (a `path` of [x,y,z]) · `gear` (`teeth`/`toothDepth`).",
      "   RECIPES (PREFER these for real machines): `motor` · `gearbox` · `pump` · `valve` · `gauge` · `tank` · `bearing` ·",
      "   `gear` · `pulley` · `belt-drive` · `frame` · `bracket` · `fan` · `heat-exchanger` · `pcb` · `lever` · `spring`.",
      "   A recipe node takes `params` (numbers) plus the same transform; it expands into a detailed assembly. Use only the",
      "   recipe's real parameter keys — an unknown key is reported as a diagnostic. `tone` is the",
      "   shared status vocabulary (neutral/info/success/warning/danger).",
      "3. Build a real machine, not a diagram: compose 8–30 nodes from RECIPES and primitives, add structure (a `frame` or",
      "   `bracket`), the moving mechanism (a `gear`, `pulley`, `lever`), and exactly one lit subject (`lit: true`). Place",
      "   parts in world units with z up; the whole scene is dropped onto the ground automatically. Give each node a short id",
      "   and a descriptive label (it is listed in a numbered key under the model). Do not claim hover/inspection it lacks.",
      "4. Give each REAL component a node and each REAL connection a `wire`; every label must be true to how it actually works.",
      "   Never invent a component, a recipe or a value.",
      animated
        ? "4. Add `stages` (label, note, readout, lit[] of part ids) that step through the mechanism, and set `animate: true`."
        : "4. Add `stages` only if the mechanism has a natural sequence of steps.",
      "5. Emit the SAME labels/numbers in your prose as in the model; keep prose to a short lead-in and an explanation of what",
      "   the model shows. Do not repeat the model's content as a list.",
      "6. Wrap it in ONE ```eclipse-response fence and nothing else that duplicates it:",
      '   {"blocks":[{"type":"model3d", ...}]}',
    ]
      .filter((line) => line !== "")
      .join("\n");
  },
  "agent.visual": (_spec, args) => {
    const subject = (Array.isArray(args.positionals.subject) ? (args.positionals.subject as string[]) : [])
      .join(" ")
      .trim();
    const forcedType = typeof args.flags.type === "string" ? args.flags.type.trim() : "";
    const symbol = typeof args.flags.symbol === "string" ? args.flags.symbol.trim() : "";
    return [
      "Render the following as ONE data visualization, inline in chat as a `chart` block (the /visual chart):",
      "",
      `Subject: ${subject || "(not given — ask the user what to chart and STOP, plotting nothing yet)"}`,
      forcedType ? `Requested chart type: ${forcedType}` : "",
      symbol ? `Symbol to plot: ${symbol}` : "",
      "",
      "Follow this exactly:",
      "1. Consult `response_block_schema` for the `chart` block and use its EXACT field names; a drifted field degrades the chart.",
      "2. Choose the best `chartType` for the data: `line` · `area` · `bar` · `stacked_bar` · `grouped_bar` · `histogram` ·",
      "   `pie` · `scatter` · `bubble` · `heatmap` · `treemap` · `sunburst` · `funnel` · `gauge` · `radar` · `waterfall`.",
      "   Use the app's default green/red palette — do not pass per-series colours unless the user asks for specific ones.",
      "3. Retrieve REAL data with your tools (JDdS, market data, portfolio, research) or use figures already present in the",
      "   conversation. NEVER invent, estimate or smooth a value. If the data is unavailable, say so plainly and emit NO chart.",
      "4. Put each line in `series[]` with a `name` and `data` (numbers; `[x, y]` pairs for scatter; `[x, y, value]` triples for",
      "   bubble/heatmap). Use `categories` for the x-axis or the slice/label names, and set `unit`/`currency`/`xLabel`/`yLabel`/",
      "   `source`/`asOf` whenever they are known so the chart is honest about where its numbers came from.",
      "5. Wrap it in ONE ```eclipse-response fence as `{\"blocks\":[{\"type\":\"chart\", ...}]}` and keep prose to a short lead-in",
      "   plus a sentence on what the chart shows. Do not repeat the chart's data as a list or table.",
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
