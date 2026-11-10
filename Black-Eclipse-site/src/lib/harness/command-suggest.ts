'use client';

// ─── Command argument completion (client) ─────────────────────────────────────
// Detects the argument the user is currently typing under a slash command and
// asks the read-only /api/harness/suggest route for candidates. This is a hint
// surface: no execution, no authority, and silence on failure.

import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  resolveCommand,
  type CommandArgSpec,
  type CommandSpec,
} from './command-registry';
import type { CommandSuggestion } from './command-suggest-types';

export type { CommandSuggestion } from './command-suggest-types';

export interface SuggestionContext {
  spec: CommandSpec;
  arg: CommandArgSpec;
  provider: string;
  /** The text already typed for this argument (may be empty). */
  prefix: string;
  /** Index in the draft where the replacement starts. */
  replaceStart: number;
}

/**
 * The active command + completion-bearing argument, or null. Only the FIRST
 * argument that declares a `completion` provider is considered; when that
 * argument is not variadic, suggestions stop once a second token is typed.
 * Pure; exported for tests.
 */
export function parseCommandCompletion(query: string): SuggestionContext | null {
  const match = /^\s*\/([A-Za-z][A-Za-z0-9_-]*)\s+([\s\S]*)$/.exec(query);
  if (!match) return null;
  const spec = resolveCommand(match[1]);
  const arg = spec?.args.find((candidate) => candidate.completion);
  if (!spec || !arg || !arg.completion) return null;

  const rest = match[2];
  const trimmed = rest.trim();
  const tokens = trimmed ? trimmed.split(/\s+/) : [];
  if (!arg.variadic && tokens.length > 1) return null;

  const prefix = arg.variadic ? (tokens[tokens.length - 1] ?? '') : (tokens[0] ?? '');
  // A trailing space means the next token has not started yet.
  const endsWithSpace = /\s$/.test(rest);
  const effectivePrefix = endsWithSpace ? '' : prefix;
  if (effectivePrefix.startsWith('-')) return null;
  return {
    spec,
    arg,
    provider: arg.completion,
    prefix: effectivePrefix,
    replaceStart: query.length - effectivePrefix.length,
  };
}

export interface CommandSuggestionsState {
  context: SuggestionContext | null;
  candidates: CommandSuggestion[];
  loading: boolean;
  highlight: number;
  setHighlight: (index: number) => void;
  visible: boolean;
  dismiss: () => void;
  /** The draft with the highlighted candidate substituted in. */
  apply: (value: string) => string | null;
}

export function useCommandSuggestions(query: string, enabled: boolean): CommandSuggestionsState {
  const context = useMemo(() => (enabled ? parseCommandCompletion(query) : null), [enabled, query]);
  const [candidates, setCandidates] = useState<CommandSuggestion[]>([]);
  const [loading, setLoading] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const [dismissedPrefix, setDismissedPrefix] = useState<string | null>(null);

  const provider = context?.provider;
  const prefix = context?.prefix;

  useEffect(() => {
    setHighlight(0);
  }, [provider, prefix]);

  useEffect(() => {
    if (!enabled || !provider || prefix === undefined) {
      setCandidates([]);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    let alive = true;
    setLoading(true);
    const timer = setTimeout(() => {
      fetch(
        `/api/harness/suggest?provider=${encodeURIComponent(provider)}&q=${encodeURIComponent(prefix)}`,
        { signal: controller.signal },
      )
        .then((res) => res.json())
        .then((data: { candidates?: unknown }) => {
          if (!alive) return;
          const list = Array.isArray(data.candidates)
            ? data.candidates.filter(
                (row): row is CommandSuggestion =>
                  Boolean(row) &&
                  typeof (row as CommandSuggestion).value === 'string' &&
                  typeof (row as CommandSuggestion).label === 'string',
              )
            : [];
          setCandidates(list.slice(0, 8));
        })
        .catch(() => {
          if (alive) setCandidates([]);
        })
        .finally(() => {
          if (alive) setLoading(false);
        });
    }, 180);
    return () => {
      alive = false;
      clearTimeout(timer);
      controller.abort();
    };
  }, [enabled, provider, prefix]);

  const visible =
    Boolean(context) && candidates.length > 0 && dismissedPrefix !== context?.prefix;

  const dismiss = useCallback(() => {
    if (context) setDismissedPrefix(context.prefix);
  }, [context]);

  const apply = useCallback(
    (value: string) => {
      if (!context) return null;
      const head = query.slice(0, context.replaceStart);
      return `${head}${value}`;
    },
    [context, query],
  );

  return {
    context,
    candidates,
    loading,
    highlight,
    setHighlight,
    visible,
    dismiss,
    apply,
  };
}
