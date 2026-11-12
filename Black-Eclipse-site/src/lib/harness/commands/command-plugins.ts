// ─── Project command packs (server-only) ──────────────────────────────────────
// Local, user-owned commands in `.black-eclipse/commands.json`. They are
// AGENT-TURN commands only: a pack supplies a prompt template, and the normal
// agent turn runs with its normal tool policy. A pack can never register a routed
// handler, widen authority, or shadow a builtin name/alias.

import fs from "node:fs/promises";
import path from "node:path";
import {
  COMMAND_CATEGORIES,
  COMMAND_REGISTRY,
  type CommandArgSpec,
  type CommandCategory,
  type CommandFlagSpec,
  type CommandSpec,
} from "./command-registry";

const MAX_COMMANDS = 50;
const MAX_ARGS = 10;
const MAX_FLAGS = 10;
const NAME_RE = /^[a-z][a-z0-9-]{1,31}$/;

export interface ProjectCommandLoad {
  commands: CommandSpec[];
  errors: string[];
}

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function text(value: unknown, max: number): string {
  return typeof value === "string" ? value.trim().slice(0, max) : "";
}

function stringList(value: unknown, maxItems: number, maxLength: number): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => item.trim().slice(0, maxLength))
    .filter(Boolean)
    .slice(0, maxItems);
}

function builtinClaims(): Set<string> {
  const claims = new Set<string>();
  for (const spec of COMMAND_REGISTRY) {
    claims.add(spec.name);
    for (const alias of spec.aliases) claims.add(alias);
  }
  return claims;
}

function parseArgs(raw: unknown, command: string, errors: string[]): CommandArgSpec[] {
  if (raw === undefined) return [];
  if (!Array.isArray(raw)) {
    errors.push(`${command}: args must be an array`);
    return [];
  }
  const out: CommandArgSpec[] = [];
  raw.slice(0, MAX_ARGS).forEach((item, index) => {
    const row = record(item);
    const name = text(row.name, 32);
    if (!NAME_RE.test(name)) {
      errors.push(`${command}: args[${index}].name is invalid`);
      return;
    }
    const type = text(row.type, 16) || "string";
    if (!["string", "number", "boolean", "enum"].includes(type)) {
      errors.push(`${command}: args[${index}].type is invalid`);
      return;
    }
    if (type === "enum" && !stringList(row.values, 20, 32).length) {
      errors.push(`${command}: enum arg \`${name}\` needs values[]`);
      return;
    }
    out.push({
      name,
      description: text(row.description, 300) || name,
      required: row.required === true,
      type: type as CommandArgSpec["type"],
      ...(type === "enum" ? { values: stringList(row.values, 20, 32) } : {}),
      ...(row.variadic === true ? { variadic: true } : {}),
      ...(typeof row.default === "string" || typeof row.default === "number" || typeof row.default === "boolean"
        ? { default: row.default }
        : {}),
    });
  });
  return out;
}

function parseFlags(raw: unknown, command: string, errors: string[]): CommandFlagSpec[] {
  if (raw === undefined) return [];
  if (!Array.isArray(raw)) {
    errors.push(`${command}: flags must be an array`);
    return [];
  }
  const out: CommandFlagSpec[] = [];
  raw.slice(0, MAX_FLAGS).forEach((item, index) => {
    const row = record(item);
    const name = text(row.name, 32);
    if (!NAME_RE.test(name)) {
      errors.push(`${command}: flags[${index}].name is invalid`);
      return;
    }
    const type = text(row.type, 16) || "boolean";
    if (!["boolean", "string", "number"].includes(type)) {
      errors.push(`${command}: flags[${index}].type is invalid`);
      return;
    }
    const alias = text(row.alias, 2);
    if (alias && !/^[a-z]$/.test(alias)) {
      errors.push(`${command}: flags[${index}].alias must be one lowercase letter`);
      return;
    }
    out.push({
      name,
      description: text(row.description, 300) || name,
      type: type as CommandFlagSpec["type"],
      ...(alias ? { alias } : {}),
      ...(stringList(row.values, 20, 32).length ? { values: stringList(row.values, 20, 32) } : {}),
      ...(typeof row.default === "string" || typeof row.default === "number" || typeof row.default === "boolean"
        ? { default: row.default }
        : {}),
    });
  });
  return out;
}

/** Validate one pack document. Pure; exported for tests. */
export function parseProjectCommandPack(
  value: unknown,
  existingClaims: ReadonlySet<string> = builtinClaims(),
): ProjectCommandLoad {
  const errors: string[] = [];
  const commands: CommandSpec[] = [];
  const root = record(value);
  if (!Array.isArray(root.commands)) {
    return { commands: [], errors: ["commands.json must have a commands[] array"] };
  }
  if (root.commands.length > MAX_COMMANDS) {
    errors.push(`commands.json has more than ${MAX_COMMANDS} commands; only the first ${MAX_COMMANDS} are loaded`);
  }

  const claimed = new Set(existingClaims);
  for (const raw of root.commands.slice(0, MAX_COMMANDS)) {
    const row = record(raw);
    const name = text(row.name, 32);
    if (!NAME_RE.test(name)) {
      errors.push(`command \`${name || "(unnamed)"}\`: name must match ${NAME_RE}`);
      continue;
    }
    if (claimed.has(name)) {
      errors.push(`command \`${name}\`: name or alias collides with an existing command`);
      continue;
    }
    const summary = text(row.summary, 200);
    const description = text(row.description, 2_000);
    const prompt = text(row.prompt, 4_000);
    if (!summary || !description || !prompt) {
      errors.push(`command \`${name}\`: summary, description and prompt are required`);
      continue;
    }
    const categoryValue = text(row.category, 32) as CommandCategory;
    const category = COMMAND_CATEGORIES.includes(categoryValue) ? categoryValue : "research";
    const aliases = stringList(row.aliases, 8, 32).filter((alias) => {
      if (!NAME_RE.test(alias)) {
        errors.push(`command \`${name}\`: alias \`${alias}\` is invalid`);
        return false;
      }
      if (claimed.has(alias)) {
        errors.push(`command \`${name}\`: alias \`${alias}\` collides with an existing command`);
        return false;
      }
      return true;
    });
    if (category !== categoryValue) {
      errors.push(`command \`${name}\`: unknown category \`${categoryValue}\`, using research`);
    }

    const args = parseArgs(row.args, name, errors);
    const flags = parseFlags(row.flags, name, errors);
    const examples = stringList(row.examples, 5, 200);
    const tags = stringList(row.tags, 10, 32);

    claimed.add(name);
    for (const alias of aliases) claimed.add(alias);

    commands.push({
      id: `project.${name}`,
      name,
      aliases,
      summary,
      description,
      category,
      tags: tags.length ? tags : ["project"],
      version: "1.0.0",
      status: "available",
      args,
      flags,
      handler: { type: "agent", target: "agent.plugin" },
      permissions: { approval: "none" },
      risk: "low",
      executionMode: "async",
      output: { type: "markdown", summary: `The agent answers using the project command /${name}.` },
      examples: examples.length ? examples : [`/${name}`],
      source: "project",
      agentPrompt: prompt,
    });
  }
  return { commands, errors };
}

/** Load `.black-eclipse/commands.json`; a missing file is an empty pack. */
export async function loadProjectCommands(root = process.cwd()): Promise<ProjectCommandLoad> {
  const file = path.join(root, ".black-eclipse", "commands.json");
  let raw: string;
  try {
    raw = await fs.readFile(file, "utf8");
  } catch (err) {
    if ((err as NodeJS.ErrnoException).code === "ENOENT") return { commands: [], errors: [] };
    return { commands: [], errors: [`could not read ${file}`] };
  }
  try {
    return parseProjectCommandPack(JSON.parse(raw));
  } catch {
    return { commands: [], errors: [`${file} is not valid JSON`] };
  }
}
