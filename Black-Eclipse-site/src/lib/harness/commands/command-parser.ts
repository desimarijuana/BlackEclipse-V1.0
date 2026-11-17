// ─── Slash-command parser ────────────────────────────────────────────────────
// A real tokenizer (not a naive `split(' ')`) that preserves quoted strings,
// Unicode, filenames with spaces, and backslash escapes; then binds the tokens to
// a command's declared argument/flag schema and validates them. Pure and
// framework-free so it can be unit-tested and reused by client and server.

import {
  resolveCommand,
  type CommandArgSpec,
  type CommandSpec,
} from "./command-registry";

export interface ArgParseError {
  code:
    | "UNTERMINATED_QUOTE"
    | "UNKNOWN_FLAG"
    | "MISSING_FLAG_VALUE"
    | "MISSING_ARG"
    | "UNEXPECTED_ARG"
    | "INVALID_ENUM"
    | "INVALID_NUMBER";
  message: string;
  /** The offending arg/flag name, when applicable. */
  arg?: string;
}

export interface CommandInvocation {
  /** Resolved canonical spec, or null for an unknown `/token`. */
  spec: CommandSpec | null;
  /** The command token, lowercased, without the leading slash. */
  name: string;
  /** The raw text after the command token. */
  rest: string;
  /** True when the token resolved to no command. */
  unknown: boolean;
  /** The original text. */
  raw: string;
}

export interface TokenizeResult {
  tokens: string[];
  errors: ArgParseError[];
}

/**
 * Split an argument string into tokens, honouring single/double quotes and
 * backslash escapes. A quoted segment may contain whitespace. Unterminated quotes
 * are reported (never silently swallowed).
 */
export function tokenizeArgs(input: string): TokenizeResult {
  const tokens: string[] = [];
  const errors: ArgParseError[] = [];
  let current = "";
  let quote: '"' | "'" | null = null;
  let started = false;

  const flush = () => {
    if (started) {
      tokens.push(current);
      current = "";
      started = false;
    }
  };

  let i = 0;
  while (i < input.length) {
    const ch = input[i];
    if (quote) {
      if (ch === "\\" && i + 1 < input.length) {
        current += input[i + 1];
        started = true;
        i += 2;
        continue;
      }
      if (ch === quote) {
        quote = null;
        i += 1;
        continue;
      }
      current += ch;
      started = true;
      i += 1;
      continue;
    }
    if (ch === '"' || ch === "'") {
      quote = ch;
      started = true;
      i += 1;
      continue;
    }
    if (ch === "\\" && i + 1 < input.length) {
      current += input[i + 1];
      started = true;
      i += 2;
      continue;
    }
    if (/\s/.test(ch)) {
      flush();
      i += 1;
      continue;
    }
    current += ch;
    started = true;
    i += 1;
  }
  if (quote) {
    errors.push({ code: "UNTERMINATED_QUOTE", message: `Unterminated ${quote} quote.` });
  }
  flush();
  return { tokens, errors };
}

export interface BoundArgs {
  /** Positional args mapped to their declared names. */
  positionals: Record<string, unknown>;
  /** Recognized flags (booleans or valued), keyed by canonical flag name. */
  flags: Record<string, string | boolean | string[]>;
  /** Pass-through `--key value` flags, as a string map (skill inputs). */
  input: Record<string, string>;
  /** Every positional token, in order (for variadic access). */
  all: string[];
  errors: ArgParseError[];
}

function isLongFlag(token: string): boolean {
  return token.startsWith("--") && token.length > 2;
}

function isShortFlag(token: string): boolean {
  return token.startsWith("-") && !token.startsWith("--") && token.length > 1;
}

function coerce(spec: CommandArgSpec, raw: string): { value: unknown; error?: ArgParseError } {
  switch (spec.type) {
    case "number": {
      const n = Number(raw);
      if (!Number.isFinite(n)) {
        return { value: raw, error: { code: "INVALID_NUMBER", message: `\`${spec.name}\` must be a number.`, arg: spec.name } };
      }
      return { value: n };
    }
    case "boolean":
      return { value: !/^(false|0|no)$/i.test(raw) };
    case "enum": {
      if (spec.values && !spec.values.includes(raw)) {
        return {
          value: raw,
          error: {
            code: "INVALID_ENUM",
            message: `\`${spec.name}\` must be one of: ${spec.values.join(", ")}.`,
            arg: spec.name,
          },
        };
      }
      return { value: raw };
    }
    default:
      return { value: raw };
  }
}

/**
 * Bind tokens to a command's schema. Unknown flags are errors unless the command
 * opts into pass-through (`passThroughFlags`), in which case they become `input`
 * entries — the mechanism `/skill --asset BTC` uses to build a skill's input.
 */
export function bindArgs(spec: CommandSpec, tokenResult: TokenizeResult): BoundArgs {
  const errors: ArgParseError[] = [...tokenResult.errors];
  const positionals: Record<string, unknown> = {};
  const flags: Record<string, string | boolean | string[]> = {};
  const passThrough: Record<string, string> = {};
  const positionalTokens: string[] = [];

  const findFlag = (name: string) => spec.flags.find((f) => f.name === name);
  const findAlias = (alias: string) => spec.flags.find((f) => f.alias === alias);
  const isSpecFlag = (name: string) => Boolean(findFlag(name));

  /**
   * Set a valued flag. A `repeatable` flag accumulates instead of overwriting:
   * a spec that documents "repeatable" must not silently keep only the last
   * value (that is how `/goal --gate a --gate b` lost a gate).
   */
  const setValue = (flag: { name: string; repeatable?: boolean }, value: string) => {
    if (flag.repeatable) {
      const current = flags[flag.name];
      const list = Array.isArray(current) ? current : [];
      flags[flag.name] = [...list, value];
      return;
    }
    flags[flag.name] = value;
  };

  const { tokens } = tokenResult;
  let i = 0;
  while (i < tokens.length) {
    const token = tokens[i];
    if (isLongFlag(token)) {
      const body = token.slice(2);
      const eq = body.indexOf("=");
      const name = eq >= 0 ? body.slice(0, eq) : body;
      const inlineValue = eq >= 0 ? body.slice(eq + 1) : undefined;
      const flag = findFlag(name);
      if (!flag) {
        if (spec.passThroughFlags && !isSpecFlag(name)) {
          const value = inlineValue ?? (i + 1 < tokens.length ? tokens[i + 1] : "");
          passThrough[name] = value;
          i += inlineValue === undefined ? 2 : 1;
          continue;
        }
        errors.push({ code: "UNKNOWN_FLAG", message: `Unknown flag \`--${name}\`.`, arg: name });
        i += 1;
        continue;
      }
      if (flag.type === "boolean") {
        flags[flag.name] = inlineValue === undefined ? true : !/^(false|0|no)$/i.test(inlineValue);
        i += 1;
        continue;
      }
      if (inlineValue !== undefined) {
        setValue(flag, inlineValue);
        i += 1;
        continue;
      }
      if (i + 1 < tokens.length) {
        setValue(flag, tokens[i + 1]);
        i += 2;
        continue;
      }
      errors.push({ code: "MISSING_FLAG_VALUE", message: `Flag \`--${name}\` needs a value.`, arg: name });
      i += 1;
      continue;
    }
    if (isShortFlag(token) && !/^-\d/.test(token)) {
      const alias = findAlias(token.slice(1));
      // A `-x` token is a flag ONLY when the command declares that alias.
      // Otherwise it is an ordinary argument (e.g. `ls -la` for `/terminal`).
      if (alias) {
        if (alias.type === "boolean") {
          flags[alias.name] = true;
          i += 1;
          continue;
        }
        if (i + 1 < tokens.length) {
          setValue(alias, tokens[i + 1]);
          i += 2;
          continue;
        }
        errors.push({ code: "MISSING_FLAG_VALUE", message: `Flag \`${token}\` needs a value.`, arg: alias.name });
        i += 1;
        continue;
      }
    }
    positionalTokens.push(token);
    i += 1;
  }

  // Map positionals onto the declared args, in order.
  let pi = 0;
  for (const arg of spec.args) {
    if (arg.variadic) {
      positionals[arg.name] = positionalTokens.slice(pi);
      pi = positionalTokens.length;
      continue;
    }
    if (pi < positionalTokens.length) {
      const { value, error } = coerce(arg, positionalTokens[pi]);
      positionals[arg.name] = value;
      if (error) errors.push(error);
      pi += 1;
      continue;
    }
    if (arg.default !== undefined) {
      positionals[arg.name] = arg.default;
    } else if (arg.required) {
      errors.push({ code: "MISSING_ARG", message: `Missing required argument \`${arg.name}\`.`, arg: arg.name });
    }
  }
  if (pi < positionalTokens.length) {
    errors.push({
      code: "UNEXPECTED_ARG",
      message: `Unexpected argument \`${positionalTokens[pi]}\`.`,
      arg: positionalTokens[pi],
    });
  }

  return { positionals, flags, input: passThrough, all: positionalTokens, errors };
}

/**
 * Parse a leading `/command` from text. Returns null when the text has no leading
 * slash-command at all (ordinary prose). An unknown `/token` yields an invocation
 * with `unknown: true` so the caller can report a helpful unknown-command error.
 * A path such as `/usr/bin` is NOT a command (the token must be followed by
 * whitespace or end-of-text).
 */
export function parseCommandInvocation(
  text: string | null | undefined,
  extra: readonly CommandSpec[] = [],
): CommandInvocation | null {
  const raw = text ?? "";
  const match = /^\s*\/([A-Za-z][A-Za-z0-9_-]*)(?:\s+([\s\S]*))?$/.exec(raw);
  if (!match) return null;
  const name = match[1].toLowerCase();
  const rest = (match[2] ?? "").trim();
  const spec = resolveCommand(name, extra) ?? null;
  return { spec, name, rest, unknown: !spec, raw };
}

/** Convenience: parse and bind in one call. Returns null for ordinary text. */
export function parseAndBind(
  text: string,
  extra: readonly CommandSpec[] = [],
): { invocation: CommandInvocation; args: BoundArgs } | null {
  const invocation = parseCommandInvocation(text, extra);
  if (!invocation) return null;
  const tokenized = tokenizeArgs(invocation.rest);
  const args = invocation.spec
    ? bindArgs(invocation.spec, tokenized)
    : { positionals: {}, flags: {}, input: {}, all: tokenized.tokens, errors: tokenized.errors };
  return { invocation, args };
}
