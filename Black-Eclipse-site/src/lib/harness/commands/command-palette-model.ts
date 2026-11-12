// ─── Command palette ordering (pure) ──────────────────────────────────────────
// The palette can be filtered, grouped and pinned without React, so the ordering
// is unit-testable and the composer/dialog share exactly one implementation.
// Pinned and Recent commands are moved to the top; everything else keeps the
// registry's deterministic category order.

import {
  COMMAND_CATEGORIES,
  searchCommands,
  type CommandCategory,
  type CommandSpec,
} from "./command-registry";
import type { TranslationKey } from "@/lib/i18n/types";

export interface CommandPaletteSection {
  key: string;
  /** Heading when no translation key is supplied (category names). */
  title: string;
  titleKey?: TranslationKey;
  commands: readonly CommandSpec[];
}

export interface CommandPaletteModel {
  sections: CommandPaletteSection[];
  /** The same commands in render order; `highlight` indexes this array. */
  flat: readonly CommandSpec[];
}

export const COMMAND_CATEGORY_ORDER: readonly CommandCategory[] = COMMAND_CATEGORIES;

const MAX_RECENT_IN_PALETTE = 6;

/**
 * Search results stay a single flat section (so the highlighted index matches
 * what the user sees). An empty query opens the full catalog grouped as
 * Pinned → Recent → categories.
 */
export function buildCommandPalette(
  query: string,
  historyNames: readonly string[],
  favoriteNames: readonly string[],
  extraCommands: readonly CommandSpec[] = [],
): CommandPaletteModel {
  const matches = searchCommands(query, { includeUnavailable: true }, extraCommands);
  if (query.trim()) {
    return { sections: [{ key: "results", title: "", commands: matches }], flat: matches };
  }

  const byName = new Map(matches.map((spec) => [spec.name, spec]));
  const used = new Set<string>();
  const sections: CommandPaletteSection[] = [];

  const pinned = favoriteNames
    .map((name) => byName.get(name))
    .filter((spec): spec is CommandSpec => spec !== undefined);
  if (pinned.length) {
    for (const spec of pinned) used.add(spec.name);
    sections.push({
      key: "pinned",
      title: "Pinned",
      titleKey: "code.command.pinned",
      commands: pinned,
    });
  }

  const recent = historyNames
    .map((name) => byName.get(name))
    .filter((spec): spec is CommandSpec => spec !== undefined && !used.has(spec.name))
    .slice(0, MAX_RECENT_IN_PALETTE);
  if (recent.length) {
    for (const spec of recent) used.add(spec.name);
    sections.push({
      key: "recent",
      title: "Recent",
      titleKey: "code.command.recent",
      commands: recent,
    });
  }

  const byCategory = new Map<CommandCategory, CommandSpec[]>();
  for (const spec of matches) {
    if (used.has(spec.name)) continue;
    const list = byCategory.get(spec.category) ?? [];
    list.push(spec);
    byCategory.set(spec.category, list);
  }
  for (const category of COMMAND_CATEGORY_ORDER) {
    const commands = byCategory.get(category);
    if (commands?.length) sections.push({ key: `cat:${category}`, title: category, commands });
  }
  for (const [category, commands] of byCategory) {
    if (!COMMAND_CATEGORY_ORDER.includes(category)) {
      sections.push({ key: `cat:${category}`, title: category, commands });
    }
  }

  return { sections, flat: sections.flatMap((section) => section.commands) };
}
