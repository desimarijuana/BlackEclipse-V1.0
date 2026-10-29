'use client';

// ── Attach a strategy to a Project ──────────────────────────────────────────
// A project is the named scope for one piece of work: its strategies, backtests,
// artifacts and notes. The studio can attach the strategy it is editing without
// making the user leave for the dashboard. The runtime owns the member record;
// this panel only sends the (kind, ref) pair and reports what came back.

import React, { useCallback, useEffect, useState } from 'react';
import {
  projectClient,
  type ProjectSummary,
} from '@/lib/projects/project-client';
import type { StrategyRecord } from '@/lib/backtest/backtest-client';
import { FolderPlus, Loader2 } from '@/lib/icons';

export function ProjectLink({ strategy }: { strategy: StrategyRecord | null }) {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [selected, setSelected] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setProjects(await projectClient.list());
    } catch {
      /* the project layer is optional here; the panel says so when it is used */
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const attach = async () => {
    if (!strategy || !selected) return;
    const project = projects.find((item) => item.id === selected);
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await projectClient.addMember(selected, {
        kind: 'strategy',
        ref: strategy.id,
        label: strategy.name || strategy.id,
        meta: {
          version: String(strategy.version ?? strategy.latestVersion ?? ''),
          symbols: ((strategy.spec.universe as { symbols?: string[] } | undefined)?.symbols ?? []) as string[],
        },
      });
      setNotice(`Attached ${strategy.name || strategy.id} to ${project?.name ?? selected}.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'could not attach the strategy');
    } finally {
      setBusy(false);
    }
  };

  const create = async () => {
    if (!name.trim()) return;
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      const project = await projectClient.create({ name: name.trim() });
      setProjects((prev) => [project, ...prev]);
      setSelected(project.id);
      setName('');
      setNotice(`Created ${project.name}. Attach the strategy when ready.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'could not create the project');
    } finally {
      setBusy(false);
    }
  };

  return (
    <details className="glass-card rounded-2xl p-4">
      <summary className="flex cursor-pointer items-center gap-2 text-sm font-semibold">
        <FolderPlus className="h-4 w-4 text-primary" />
        Project
        <span className="font-mono text-[10px] font-normal text-muted-foreground">
          {projects.length ? `${projects.length} available` : 'none yet'}
        </span>
      </summary>

      <div className="mt-3 flex flex-col gap-2">
        {!strategy ? (
          <p className="text-[11px] leading-relaxed text-muted-foreground">
            Save and run a strategy first; then you can attach it to a project.
          </p>
        ) : (
          <>
            <p className="text-[10px] leading-relaxed text-muted-foreground">
              Attaching records this strategy in a project so its experiments, artifacts and notes stay together.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={selected}
                onChange={(event) => setSelected(event.target.value)}
                aria-label="Project"
                className="glass-card-subtle min-w-[160px] rounded-lg px-2 py-1 text-[11px] text-foreground outline-none"
              >
                <option value="">— select a project —</option>
                {projects.map((project) => (
                  <option key={project.id} value={project.id}>
                    {project.name}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => void attach()}
                disabled={busy || !selected}
                className="glass-button flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-[10px] disabled:opacity-50"
              >
                {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <FolderPlus className="h-3 w-3" />}
                Attach strategy
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-2 border-t border-white/10 pt-2">
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="New project name"
                className="glass-card-subtle flex-1 rounded-lg px-2 py-1 text-[11px] text-foreground outline-none placeholder:text-muted-foreground"
              />
              <button
                type="button"
                onClick={() => void create()}
                disabled={busy || !name.trim()}
                className="glass-button rounded-lg px-2.5 py-1 text-[10px] disabled:opacity-50"
              >
                Create
              </button>
            </div>
          </>
        )}

        {notice ? <p className="text-[10px] text-emerald-300">{notice}</p> : null}
        {error ? <p className="text-[10px] text-rose-300">{error}</p> : null}
      </div>
    </details>
  );
}
