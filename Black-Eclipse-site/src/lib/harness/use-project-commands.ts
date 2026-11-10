'use client';

// ─── Project command packs in the composer (client) ───────────────────────────
// The manifest endpoint is the single source: it returns builtins + validated
// project commands. The composer only needs the project ones (builtins are
// already in the bundle), and caches them for the session.

import { useEffect, useState } from 'react';
import type { CommandSpec } from './command-registry';

const EMPTY: readonly CommandSpec[] = Object.freeze([]);
let cache: CommandSpec[] | null = null;
let pending: Promise<CommandSpec[]> | null = null;

function isCommand(row: unknown): row is CommandSpec {
  if (!row || typeof row !== 'object') return false;
  const spec = row as Partial<CommandSpec>;
  return typeof spec.name === 'string' && typeof spec.summary === 'string' && Boolean(spec.handler);
}

export function fetchProjectCommands(): Promise<CommandSpec[]> {
  if (cache) return Promise.resolve(cache);
  if (!pending) {
    pending = fetch('/api/harness/commands', { headers: { Accept: 'application/json' } })
      .then((res) => (res.ok ? res.json() : { commands: [] }))
      .then((data: { commands?: unknown }) => {
        const rows = Array.isArray(data.commands) ? data.commands : [];
        cache = rows
          .filter((row): row is CommandSpec => isCommand(row) && (row as CommandSpec).source === 'project')
          .slice(0, 50);
        return cache;
      })
      .catch(() => {
        cache = [];
        return cache;
      })
      .finally(() => {
        pending = null;
      });
  }
  return pending;
}

export function useProjectCommands(): readonly CommandSpec[] {
  const [commands, setCommands] = useState<readonly CommandSpec[]>(cache ?? EMPTY);
  useEffect(() => {
    if (cache) {
      setCommands(cache);
      return;
    }
    let alive = true;
    void fetchProjectCommands().then((rows) => {
      if (alive) setCommands(rows);
    });
    return () => {
      alive = false;
    };
  }, []);
  return commands;
}

/** Test-only: drop the session cache. */
export function resetProjectCommandsForTests(): void {
  cache = null;
  pending = null;
}
