"use client";

// Git workflow panel — plan, review, commit, push, all in-app.
//
// The flow is intentionally explicit (like a careful operator, not an auto-pusher):
//   1. see what changed (status)
//   2. stage the files you mean
//   3. write a message (or draft one from the real diff)
//   4. commit
//   5. push — a SEPARATE action, never automatic
//
// The server refuses secret-looking staged paths and never force-pushes.

import React, { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  ArrowUp,
  Check,
  GitBranch,
  GitCommitHorizontal,
  Loader2,
  RefreshCw,
  Sparkles,
  Upload,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  commitChanges,
  draftCommitMessage,
  fetchGitLog,
  fetchGitStatus,
  pushChanges,
  stagePaths,
  unstagePaths,
  type GitCommitInfo,
  type GitStatus,
} from "@/lib/git/client";

function statusCode(f: { index: string; worktree: string }): string {
  if (f.index === "?" && f.worktree === "?") return "??";
  return `${f.index}${f.worktree}`.replace(/ /g, "·");
}

export function GitPanel() {
  const [status, setStatus] = useState<GitStatus | null>(null);
  const [log, setLog] = useState<GitCommitInfo[]>([]);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState<string>("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [s, l] = await Promise.all([fetchGitStatus(), fetchGitLog().catch(() => [])]);
      setStatus(s);
      setLog(l);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read git status");
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const act = async (name: string, fn: () => Promise<void>) => {
    setBusy(name);
    setError("");
    setNotice("");
    try {
      await fn();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Git action failed");
    } finally {
      setBusy("");
    }
  };

  const doDraft = () =>
    act("draft", async () => {
      const draft = await draftCommitMessage();
      if (draft) setMessage(draft);
    });

  const doCommit = () =>
    act("commit", async () => {
      const result = await commitChanges(message);
      setMessage("");
      setNotice(`Committed ${result.hash.slice(0, 7)} — ${result.subject}`);
      await refresh();
    });

  const doPush = () =>
    act("push", async () => {
      const result = await pushChanges(false);
      setNotice(`Pushed ${result.branch} to origin`);
      await refresh();
    });

  if (!status) {
    return (
      <div className="flex items-center gap-2 px-5 py-4 text-xs text-muted-foreground">
        <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" /> Reading repository…
      </div>
    );
  }

  if (!status.available) {
    return (
      <div className="flex items-center gap-2 px-5 py-4 text-xs text-muted-foreground">
        <AlertCircle className="h-3.5 w-3.5" /> {status.reason ?? "Git is not available here."}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Branch + counts */}
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 dark:border-white/5 glass-card px-4 py-3">
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-foreground">
          <GitBranch className="h-3.5 w-3.5 text-primary" />
          {status.branch ?? "detached"}
        </span>
        {status.upstream && (
          <span className="text-[10px] font-mono text-muted-foreground">
            {status.upstream}
            {status.ahead > 0 && <span className="ml-1 text-emerald-400">↑{status.ahead}</span>}
            {status.behind > 0 && <span className="ml-1 text-amber-400">↓{status.behind}</span>}
          </span>
        )}
        <span className="flex-1" />
        <button
          type="button"
          onClick={() => void refresh()}
          className="rounded-lg p-1.5 text-muted-foreground hover:text-primary cursor-pointer"
          title="Refresh"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", busy === "refresh" && "animate-spin")} />
        </button>
      </div>

      {(error || notice) && (
        <div
          className={cn(
            "flex items-center gap-2 rounded-xl border px-4 py-2.5 text-xs",
            error
              ? "border-rose-400/30 bg-rose-400/5 text-rose-400"
              : "border-emerald-400/30 bg-emerald-400/5 text-emerald-400"
          )}
        >
          {error ? <AlertCircle className="h-3.5 w-3.5" /> : <Check className="h-3.5 w-3.5" />}
          {error || notice}
        </div>
      )}

      {/* Changes */}
      <div className="overflow-hidden rounded-xl border border-white/10 dark:border-white/5 glass-card">
        <div className="flex items-center justify-between border-b border-border/10 px-4 py-2.5">
          <span className="text-xs font-semibold text-foreground">Changes</span>
          <span className="text-[10px] font-mono text-muted-foreground">
            {status.stagedCount} staged · {status.unstagedCount} modified · {status.untrackedCount} new
          </span>
        </div>
        {status.clean ? (
          <p className="px-4 py-3 text-[11px] text-muted-foreground">Working tree clean.</p>
        ) : (
          <ul className="max-h-[320px] divide-y divide-border/5 overflow-y-auto">
            {status.files.map((f) => (
              <li key={f.path} className="flex items-center gap-2 px-4 py-2 hover:bg-accent/20">
                <span
                  className={cn(
                    "w-7 shrink-0 rounded px-1 py-0.5 text-center text-[9px] font-mono",
                    f.staged ? "bg-emerald-400/15 text-emerald-400" : "bg-white/5 text-muted-foreground"
                  )}
                >
                  {statusCode(f)}
                </span>
                <span className="min-w-0 flex-1 truncate text-[11px] text-foreground" title={f.path}>
                  {f.path}
                </span>
                {f.staged ? (
                  <button
                    type="button"
                    onClick={() => act("unstage", async () => setStatus(await unstagePaths([f.path])))}
                    className="text-[10px] text-muted-foreground hover:text-foreground cursor-pointer"
                  >
                    unstage
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => act("stage", async () => setStatus(await stagePaths([f.path])))}
                    className="text-[10px] text-primary hover:underline cursor-pointer"
                  >
                    stage
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>

      {/* Commit */}
      <div className="rounded-xl border border-white/10 dark:border-white/5 glass-card p-4">
        <div className="mb-2 flex items-center gap-2">
          <GitCommitHorizontal className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-semibold text-foreground">Commit</span>
          <span className="flex-1" />
          <button
            type="button"
            onClick={doDraft}
            disabled={status.stagedCount === 0 || busy === "draft"}
            className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-2 py-1 text-[10px] text-muted-foreground transition-colors hover:text-primary disabled:opacity-30 cursor-pointer"
            title="Draft a message from the staged diff"
          >
            {busy === "draft" ? <Loader2 className="h-3 w-3 animate-spin" /> : <Sparkles className="h-3 w-3" />}
            Draft
          </button>
        </div>
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          rows={3}
          placeholder={status.stagedCount === 0 ? "Stage files to commit" : "Commit message…"}
          className="w-full resize-none rounded-lg border border-white/10 bg-transparent px-3 py-2 text-xs text-foreground outline-none placeholder:text-muted-foreground/60 focus:border-primary/40"
        />
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            onClick={doCommit}
            disabled={status.stagedCount === 0 || !message.trim() || busy === "commit"}
            className="inline-flex items-center gap-1.5 rounded-lg border border-primary/30 bg-primary/15 px-3 py-1.5 text-xs font-medium text-primary transition-colors hover:bg-primary/25 disabled:cursor-default disabled:opacity-30 cursor-pointer"
          >
            {busy === "commit" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
            Commit {status.stagedCount > 0 ? `(${status.stagedCount})` : ""}
          </button>
          <button
            type="button"
            onClick={doPush}
            disabled={status.ahead === 0 || busy === "push"}
            className="inline-flex items-center gap-1.5 rounded-lg border border-white/10 px-3 py-1.5 text-xs text-foreground transition-colors hover:border-primary/30 disabled:cursor-default disabled:opacity-30 cursor-pointer"
            title={status.ahead === 0 ? "Nothing to push" : `Push ${status.ahead} commit(s)`}
          >
            {busy === "push" ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Upload className="h-3.5 w-3.5" />}
            Push {status.ahead > 0 ? `↑${status.ahead}` : ""}
          </button>
        </div>
        <p className="mt-2 text-[10px] leading-relaxed text-muted-foreground/70">
          Secrets (.env, keys, databases) are refused automatically. Push is manual and never forced.
        </p>
      </div>

      {/* Recent commits */}
      {log.length > 0 && (
        <div className="overflow-hidden rounded-xl border border-white/10 dark:border-white/5 glass-card">
          <div className="flex items-center gap-2 border-b border-border/10 px-4 py-2.5">
            <ArrowUp className="h-3.5 w-3.5 text-muted-foreground" />
            <span className="text-xs font-semibold text-foreground">Recent commits</span>
          </div>
          <ul className="max-h-[240px] divide-y divide-border/5 overflow-y-auto">
            {log.map((c) => (
              <li key={c.hash} className="flex items-center gap-2 px-4 py-2">
                <span className="font-mono text-[10px] text-primary">{c.shortHash}</span>
                <span className="min-w-0 flex-1 truncate text-[11px] text-foreground">{c.subject}</span>
                <span className="text-[9px] text-muted-foreground">{c.author}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
