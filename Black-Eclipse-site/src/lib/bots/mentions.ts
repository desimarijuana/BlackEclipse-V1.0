// ── Bot / group-chat mention registry (pure) ─────────────────────────────────
// The `@` sibling of the slash-command registry: ONE pure module that turns the
// user's real bots (`AutomationView[]`) and group rooms (`BotGroup[]`) into a
// mentionable list, and resolves `@Name` tokens in composer text back to those
// targets. It owns NO execution and NO I/O — the palette and the dispatcher both
// read the same list so they can never disagree about who can be mentioned.
//
// Deliberately dependency-free (only type imports) so it is unit-testable without
// a DOM, mirroring `lib/harness/command-registry.ts`.

import type { AutomationView } from '@/lib/harness/automation-client';
import type { BotGroup } from '@/lib/bots/groups-store';

export type MentionKind = 'bot' | 'group';

/** One thing a user can `@`-mention from the main composer. */
export interface MentionTarget {
  kind: MentionKind;
  /** The bot's automation id, or the group's id. */
  id: string;
  /** The display name matched against the `@` token. */
  name: string;
  /** A short subtitle (bot purpose, or the group's member count). */
  description: string;
  /** Member bot ids (groups only; empty for a bot). */
  memberIds: string[];
}

/** Escape a string for safe use inside a RegExp (kept for callers that highlight). */
export function escapeRegExp(s: string): string {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * Project the live bots + groups into the mentionable list. A bot's subtitle is
 * its purpose (description, else the objective); a group's is its member count.
 * Names are never invented — an unnamed record contributes nothing useful and is
 * still surfaced by its fallback name so the list is never silently short.
 */
export function buildMentionTargets(
  bots: readonly AutomationView[],
  groups: readonly BotGroup[],
): MentionTarget[] {
  const out: MentionTarget[] = [];
  for (const bot of bots) {
    const name = (bot.name ?? '').trim();
    if (!name) continue;
    out.push({
      kind: 'bot',
      id: bot.id,
      name,
      description: (bot.description ?? bot.action?.objective ?? '').trim(),
      memberIds: [],
    });
  }
  for (const group of groups) {
    const name = (group.name ?? '').trim();
    if (!name) continue;
    out.push({
      kind: 'group',
      id: group.id,
      name,
      description: `${group.memberIds.length} member${group.memberIds.length === 1 ? '' : 's'}`,
      memberIds: [...group.memberIds],
    });
  }
  return out;
}

function isSubsequence(needle: string, haystack: string): boolean {
  let i = 0;
  for (const ch of haystack) {
    if (ch === needle[i]) i += 1;
    if (i === needle.length) return true;
  }
  return needle.length === 0;
}

/** Score a target against a query. Higher is better; 0 = no match. */
function scoreMention(target: MentionTarget, query: string): number {
  if (!query) return 1;
  const name = target.name.toLowerCase();
  if (name === query) return 1000;
  if (name.startsWith(query)) return 700 - name.length;
  if (name.includes(query)) return 400 - name.length;
  if (target.description.toLowerCase().includes(query)) return 200;
  if (isSubsequence(query, name)) return 100;
  return 0;
}

/**
 * Search mentionable targets by prefix/name/description/fuzzy match. Deterministic
 * (stable ordering) so the `@` palette does not reorder between keystrokes.
 */
export function searchMentions(
  targets: readonly MentionTarget[],
  query: string,
  limit = 8,
): MentionTarget[] {
  const q = (query ?? '').trim().toLowerCase();
  if (!q) {
    return [...targets].sort((a, b) => a.name.localeCompare(b.name)).slice(0, limit);
  }
  return targets
    .map((target) => ({ target, score: scoreMention(target, q) }))
    .filter((x) => x.score > 0)
    .sort((a, b) => (b.score - a.score) || a.target.name.localeCompare(b.target.name))
    .map((x) => x.target)
    .slice(0, limit);
}

/** One resolved `@Name` occurrence in a message. */
export interface ResolvedMention {
  target: MentionTarget;
  /** Index of the `@` in the source text. */
  start: number;
  /** Index just past the matched name. */
  end: number;
}

/**
 * Find every `@Name` token in `text` that resolves to a known target. Names are
 * matched case-insensitively, longest-name-first (so `@Portfolio Bot` beats
 * `@Portfolio`), and only at the start of the text or after whitespace (so an
 * email like `a@b` never matches). A name must be followed by a non-word
 * character or end-of-text (so `@Bob` does not match inside `@Bobby`). Duplicate
 * mentions of the same target are collapsed to their first occurrence.
 */
export function parseMentions(
  text: string | null | undefined,
  targets: readonly MentionTarget[],
): ResolvedMention[] {
  const src = text ?? '';
  if (!src || targets.length === 0) return [];
  // Longest name first so a longer name always wins over one that prefixes it.
  const ordered = [...targets].sort((a, b) => b.name.length - a.name.length);
  const out: ResolvedMention[] = [];
  const seen = new Set<string>();
  let i = 0;
  while (i < src.length) {
    const at = src.indexOf('@', i);
    if (at === -1) break;
    // `@` must start the text or follow whitespace — never sit inside a word.
    if (at > 0 && !/\s/.test(src[at - 1])) {
      i = at + 1;
      continue;
    }
    const rest = src.slice(at + 1);
    const lowerRest = rest.toLowerCase();
    // Longest matching name wins. If several targets share that name, resolve
    // them ALL (the palette may list two bots called "Desk", and silently
    // routing to whichever sorted first would be wrong).
    let matchedLen = 0;
    let matched: MentionTarget[] = [];
    for (const target of ordered) {
      const name = target.name.toLowerCase();
      if (!name || !lowerRest.startsWith(name)) continue;
      const after = rest[name.length];
      // Require a word boundary after the name; allow punctuation, whitespace, end.
      if (after !== undefined && /[\w-]/.test(after)) continue;
      if (name.length > matchedLen) {
        matchedLen = name.length;
        matched = [target];
      } else if (name.length === matchedLen) {
        matched.push(target);
      }
    }
    if (matchedLen > 0) {
      for (const target of matched) {
        const key = `${target.kind}:${target.id}`;
        if (!seen.has(key)) {
          seen.add(key);
          out.push({ target, start: at, end: at + 1 + matchedLen });
        }
      }
      i = at + 1 + matchedLen;
    } else {
      i = at + 1;
    }
  }
  return out;
}

/** The distinct targets mentioned in `text`, in first-appearance order. */
export function mentionedTargets(
  text: string | null | undefined,
  targets: readonly MentionTarget[],
): MentionTarget[] {
  return parseMentions(text, targets).map((m) => m.target);
}
