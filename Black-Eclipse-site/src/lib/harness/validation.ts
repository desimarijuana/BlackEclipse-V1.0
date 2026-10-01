// ─── External input validation (front door) ──────────────────────────────────
// The Next.js front door validates the untrusted request body and normalizes it
// into a RunInput before forwarding to the Python runtime. Agent-config
// validation lives on the Python side (`python/harness/schemas.py`), which is
// the runtime that actually consumes it.

import type { RunInput, RunWorkspaceRef } from "./types";
import { HarnessError } from "./errors";

export interface InputValidationResult {
  ok: boolean;
  value?: RunInput;
  issues: string[];
}

const MAX_QUERY_LENGTH = 4000;
const MAX_WORKSPACE_ROOT = 1024;
const MAX_BASE_REVISION = 128;

/**
 * Validate an optional workspace reference before forwarding it to the runtime.
 *
 * This is a NARROWING/confirmation only: the Python runtime binds the
 * server-resolved root and refuses any `root` that does not match it. Here we
 * only reject malformed input (control characters/NUL, over-length), so a bad
 * value fails at the front door rather than reaching the runtime.
 */
export function validateWorkspaceRef(raw: unknown): {
  ok: boolean;
  value?: RunWorkspaceRef;
  issues: string[];
} {
  const issues: string[] = [];
  if (raw === undefined || raw === null) return { ok: true, issues: [] };
  if (typeof raw !== "object" || Array.isArray(raw)) {
    return { ok: false, issues: ["workspace must be an object"] };
  }
  const body = raw as Record<string, unknown>;
  const hasControlChars = (s: string) => {
    for (let i = 0; i < s.length; i += 1) {
      const code = s.charCodeAt(i);
      if (code < 0x20 || code === 0x7f) return true;
    }
    return false;
  };

  const root = typeof body.root === "string" ? body.root.trim() : "";
  if (!root) issues.push("workspace.root is required");
  else if (root.length > MAX_WORKSPACE_ROOT) issues.push(`workspace.root too long (max ${MAX_WORKSPACE_ROOT} chars)`);
  else if (hasControlChars(root)) issues.push("workspace.root must not contain control characters");

  let baseRevision: string | undefined;
  if (body.baseRevision !== undefined && body.baseRevision !== null) {
    if (typeof body.baseRevision !== "string") issues.push("workspace.baseRevision must be a string");
    else {
      baseRevision = body.baseRevision.trim();
      if (baseRevision.length > MAX_BASE_REVISION) issues.push(`workspace.baseRevision too long (max ${MAX_BASE_REVISION} chars)`);
      else if (hasControlChars(baseRevision)) issues.push("workspace.baseRevision must not contain control characters");
    }
  }

  if (issues.length > 0) return { ok: false, issues };
  return { ok: true, value: { root, baseRevision }, issues: [] };
}

const MAX_CONTEXT_KEYS = 50;
const MAX_HISTORY_TURNS = 20;
const MAX_HISTORY_CONTENT = 20_000;
const MAX_DOCUMENTS = 20;
const MAX_DOCUMENT_CHARS = 20_000;
const MAX_TOTAL_DOCUMENT_CHARS = 60_000;

export function validateRunInput(raw: unknown): InputValidationResult {
  const issues: string[] = [];
  if (raw === null || typeof raw !== "object") {
    return { ok: false, issues: ["body must be a JSON object"] };
  }
  const body = raw as Record<string, unknown>;

  const query = typeof body.query === "string" ? body.query.trim() : "";
  if (!query) issues.push("query is required");
  else if (query.length > MAX_QUERY_LENGTH) issues.push(`query too long (max ${MAX_QUERY_LENGTH} chars)`);

  let ticker: string | undefined;
  if (body.ticker !== undefined && body.ticker !== null) {
    if (typeof body.ticker !== "string") issues.push("ticker must be a string");
    else ticker = body.ticker.trim().toUpperCase().slice(0, 20);
  }

  let market: string | undefined;
  if (body.market !== undefined && body.market !== null) {
    if (typeof body.market !== "string") issues.push("market must be a string");
    else market = body.market.trim().toUpperCase().slice(0, 20);
  }

  let context: Record<string, unknown> | undefined;
  if (body.context !== undefined && body.context !== null) {
    if (typeof body.context !== "object" || Array.isArray(body.context)) {
      issues.push("context must be an object");
    } else {
      const entries = Object.entries(body.context as Record<string, unknown>);
      if (entries.length > MAX_CONTEXT_KEYS) issues.push(`context has too many keys (max ${MAX_CONTEXT_KEYS})`);
      else context = Object.fromEntries(entries);
    }
  }

  let history: RunInput["history"];
  if (body.history !== undefined && body.history !== null) {
    if (!Array.isArray(body.history)) {
      issues.push("history must be an array");
    } else {
      const turns: RunInput["history"] = [];
      for (const [i, rawTurn] of body.history.entries()) {
        if (rawTurn === null || typeof rawTurn !== "object") {
          issues.push(`history[${i}] must be an object`);
          continue;
        }
        const turn = rawTurn as Record<string, unknown>;
        const role = turn.role;
        const content = typeof turn.content === "string" ? turn.content : "";
        if (role !== "user" && role !== "assistant") {
          issues.push(`history[${i}].role must be "user" or "assistant"`);
          continue;
        }
        // An empty turn is a legitimate partial: a cancelled or failed
        // assistant reply persists as `content: ""`. Skip it rather than
        // rejecting the whole request — otherwise one failed turn would poison
        // every later message in that conversation (front door returns 400).
        if (!content.trim()) continue;
        turns.push({ role, content: content.slice(0, MAX_HISTORY_CONTENT) });
      }
      if (turns.length > MAX_HISTORY_TURNS) turns.splice(0, turns.length - MAX_HISTORY_TURNS);
      history = turns;
    }
  }

  let documents: RunInput["documents"];
  if (body.documents !== undefined && body.documents !== null) {
    if (!Array.isArray(body.documents)) {
      issues.push("documents must be an array");
    } else {
      const docs: RunInput["documents"] = [];
      let total = 0;
      for (const [i, rawDoc] of body.documents.entries()) {
        if (rawDoc === null || typeof rawDoc !== "object") {
          issues.push(`documents[${i}] must be an object`);
          continue;
        }
        const doc = rawDoc as Record<string, unknown>;
        const name = typeof doc.name === "string" ? doc.name.trim().slice(0, 128) : "";
        const text = typeof doc.text === "string" ? doc.text : "";
        if (!name) {
          issues.push(`documents[${i}].name is required`);
          continue;
        }
        if (!text.trim()) {
          issues.push(`documents[${i}].text is required`);
          continue;
        }
        if (docs.length >= MAX_DOCUMENTS) {
          issues.push(`too many documents (max ${MAX_DOCUMENTS})`);
          break;
        }
        const remaining = MAX_TOTAL_DOCUMENT_CHARS - total;
        if (remaining <= 0) {
          issues.push(`documents exceed the ${MAX_TOTAL_DOCUMENT_CHARS} char limit`);
          break;
        }
        const bounded = text.slice(0, Math.min(MAX_DOCUMENT_CHARS, remaining));
        total += bounded.length;
        docs.push({ name, text: bounded });
      }
      documents = docs.length ? docs : undefined;
    }
  }

  if (issues.length > 0) return { ok: false, issues };
  return { ok: true, value: { query, ticker, market, context, history, documents }, issues: [] };
}

/** Throwing wrapper for callers that prefer exceptions. */
export function assertRunInput(raw: unknown): RunInput {
  const result = validateRunInput(raw);
  if (!result.ok || !result.value) {
    throw new HarnessError("INVALID_INPUT", "Invalid run input", result.issues.join("; "));
  }
  return result.value;
}
