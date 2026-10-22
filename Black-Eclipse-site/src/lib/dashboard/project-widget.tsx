'use client';

// ── Project scope widget ─────────────────────────────────────────────────────
// The project the chat is currently in, and the projects that exist. The
// widget is the front door of the project concept: it lists what the runtime
// holds, lets the user pin the chat to one, and creates a new scope.
//
// It shows exactly what the runtime returned. A project that cannot be listed
// says so; a failure to create says so. Nothing is invented locally.

import React, { useCallback, useEffect, useState } from 'react';
import {
  getActiveProjectId,
  projectClient,
  setActiveProjectId,
  type ProjectDigest,
  type ProjectProposals,
  type ProjectSummary,
} from '@/lib/projects/project-client';
import { cn } from '@/lib/utils';
import { FolderPlus, Loader2, Play, Plus } from '@/lib/icons';

export function ProjectScopeWidget() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [digest, setDigest] = useState<ProjectDigest | null>(null);
  const [proposals, setProposals] = useState<ProjectProposals | null>(null);
  const [running, setRunning] = useState(false);
  const [runNote, setRunNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState('');
  const [symbols, setSymbols] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setProjects(await projectClient.list());
    } catch (err) {
      setError(err instanceof Error ? err.message : 'the project layer is unavailable');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setActiveId(getActiveProjectId());
    void load();
  }, [load]);

  // The active project's curated view: what it is, and what it still lacks.
  useEffect(() => {
    if (!activeId) {
      setDigest(null);
      setProposals(null);
      return;
    }
    let cancelled = false;
    void projectClient
      .digest(activeId)
      .then((d) => {
        if (!cancelled) setDigest(d);
      })
      .catch(() => {
        if (!cancelled) setDigest(null);
      });
    void projectClient
      .proposals(activeId)
      .then((p) => {
        if (!cancelled) setProposals(p);
      })
      .catch(() => {
        if (!cancelled) setProposals(null);
      });
    return () => {
      cancelled = true;
    };
  }, [activeId]);

  const choose = useCallback((id: string | null) => {
    setActiveProjectId(id);
    setActiveId(id);
  }, []);

  // Run the project's own next proposal, then re-read it: the project now
  // knows what just happened, so its next proposal is made against that.
  const runTopProposal = useCallback(async () => {
    const top = proposals?.proposals?.[0];
    if (!activeId || !top || running) return;
    setRunning(true);
    setRunNote(null);
    try {
      const { run } = await projectClient.runProposal(activeId, top.id);
      setRunNote(run.summary || `the proposal ${run.status}`);
      const [digest, next] = await Promise.all([
        projectClient.digest(activeId).catch(() => null),
        projectClient.proposals(activeId).catch(() => null),
      ]);
      if (digest) setDigest(digest);
      if (next) setProposals(next);
    } catch (err) {
      setRunNote(err instanceof Error ? err.message : 'the proposal could not be run');
    } finally {
      setRunning(false);
    }
  }, [activeId, proposals, running]);

  const create = useCallback(async () => {
    const clean = name.trim();
    if (!clean || busy) return;
    setBusy(true);
    setError(null);
    try {
      const project = await projectClient.create({
        name: clean,
        symbols: symbols
          .split(/[,\s]+/)
          .map((s) => s.trim())
          .filter(Boolean),
      });
      setName('');
      setSymbols('');
      setProjects((prev) => [project, ...prev.filter((p) => p.id !== project.id)]);
      choose(project.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'the project could not be created');
    } finally {
      setBusy(false);
    }
  }, [name, symbols, busy, choose]);

  const active = projects.find((p) => p.id === activeId) ?? null;

  return (
    <div className="flex h-full flex-col gap-2 p-3">
      <div className="flex items-center gap-2">
        <FolderPlus className="h-3.5 w-3.5 text-primary" />
        <span className="text-[11px] font-semibold text-foreground">Project scope</span>
        {active ? (
          <span className="ml-auto truncate font-mono text-[9px] text-primary">
            {active.name}
          </span>
        ) : (
          <span className="ml-auto font-mono text-[9px] text-muted-foreground">
            no project
          </span>
        )}
      </div>

      {loading ? (
        <p className="font-mono text-[9px] text-muted-foreground">Loading projects…</p>
      ) : error ? (
        <p className="font-mono text-[9px] text-rose-300">{error}</p>
      ) : projects.length === 0 ? (
        <p className="font-mono text-[9px] text-muted-foreground">
          No projects yet. Create one below.
        </p>
      ) : (
        <ul className="max-h-[150px] space-y-0.5 overflow-y-auto scrollbar-hide">
          {projects.map((project) => (
            <li key={project.id}>
              <button
                type="button"
                onClick={() => choose(project.id === activeId ? null : project.id)}
                className={cn(
                  'flex w-full items-center gap-2 rounded px-2 py-1 text-left transition',
                  project.id === activeId
                    ? 'border border-primary/40 bg-primary/10'
                    : 'border border-transparent hover:bg-white/5',
                )}
              >
                <span className="min-w-0 flex-1 truncate text-[10px] text-foreground">
                  {project.name}
                </span>
                {project.symbols.length > 0 && (
                  <span className="shrink-0 font-mono text-[8px] text-muted-foreground">
                    {project.symbols.slice(0, 3).join(' ')}
                  </span>
                )}
              </button>
            </li>
          ))}
        </ul>
      )}

      {active && (
        <div className="rounded-lg border border-white/10 bg-black/20 px-2 py-1.5">
          <p className="text-[10px] text-foreground">{active.name}</p>
          {digest ? (
            <>
              <p className="mt-0.5 text-[9px] leading-relaxed text-muted-foreground">
                {digest.headline}
              </p>
              {digest.members.length > 0 && (
                <ul className="mt-1 space-y-0.5">
                  {digest.members.slice(0, 3).map((m) => (
                    <li key={m.id} className="font-mono text-[9px] text-muted-foreground">
                      <span className="text-foreground">{m.kind}</span> {m.ref}
                      <span className="text-muted-foreground/70"> — {m.reason}</span>
                    </li>
                  ))}
                </ul>
              )}
              {digest.gaps.length > 0 && (
                <p className="mt-1 text-[9px] leading-relaxed text-amber-300">
                  Still missing: {digest.gaps.join('; ')}
                </p>
              )}
            </>
          ) : (
            <p className="mt-0.5 text-[9px] text-muted-foreground">
              {active.description || 'No description yet.'}
            </p>
          )}
          {proposals && proposals.proposals.length > 0 && (
            <div className="mt-1 border-t border-white/10 pt-1">
              <p className="font-mono text-[9px] text-primary">Next step</p>
              <p className="text-[9px] leading-relaxed text-foreground">
                {proposals.proposals[0].title}
              </p>
              <p className="mt-0.5 text-[9px] leading-relaxed text-muted-foreground/80">
                {proposals.proposals[0].rationale}
              </p>
              <button
                type="button"
                onClick={() => void runTopProposal()}
                disabled={running}
                className="glass-button mt-1 flex w-full items-center justify-center gap-1 rounded px-2 py-1 text-[9px] disabled:opacity-40"
              >
                {running ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
                {running ? 'Running…' : 'Run it'}
              </button>
              {runNote && (
                <p className="mt-1 text-[9px] leading-relaxed text-muted-foreground">
                  {runNote}
                </p>
              )}
            </div>
          )}
        </div>
      )}

      <div className="mt-auto flex flex-col gap-1 border-t border-border/10 pt-2">
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="New project name"
          className="h-7 w-full rounded border border-border/30 bg-transparent px-2 text-[10px] text-foreground placeholder:text-muted-foreground focus:border-primary/40 focus:outline-none"
        />
        <input
          value={symbols}
          onChange={(e) => setSymbols(e.target.value)}
          placeholder="Instruments (e.g. NQ ES)"
          className="h-7 w-full rounded border border-border/30 bg-transparent px-2 font-mono text-[10px] text-foreground placeholder:text-muted-foreground focus:border-primary/40 focus:outline-none"
        />
        <button
          type="button"
          onClick={() => void create()}
          disabled={busy || !name.trim()}
          className="glass-button flex items-center justify-center gap-1.5 rounded px-2 py-1 text-[10px] disabled:opacity-40"
        >
          {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <Plus className="h-3 w-3" />}
          Create project
        </button>
        <p className="text-[8px] leading-relaxed text-muted-foreground/70">
          The active project scopes the next chat turn: its strategies, backtests and
          artifacts are put in front of the agent. It grants nothing.
        </p>
      </div>
    </div>
  );
}
