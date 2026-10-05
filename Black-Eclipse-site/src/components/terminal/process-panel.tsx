"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCw, RotateCcw, Square, XCircle } from "lucide-react";
import {
  killTerminalProcess,
  listTerminalProcesses,
  restartTerminalProcess,
  stopTerminalProcess,
  type ProcessInfo,
} from "@/lib/harness/terminal-browser";
import { cn } from "@/lib/utils";

const STATE_COLOR: Record<string, string> = {
  RUNNING: "text-emerald-300",
  STARTING: "text-amber-300",
  STOPPING: "text-amber-300",
  EXITED: "text-zinc-400",
  STOPPED: "text-zinc-400",
  CRASHED: "text-rose-300",
  FAILED: "text-rose-300",
  KILLED: "text-zinc-400",
  TIMEOUT: "text-rose-300",
  UNKNOWN: "text-muted-foreground",
};

export function ProcessPanel({ refreshKey = 0 }: { refreshKey?: number }) {
  const [processes, setProcesses] = useState<ProcessInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      setProcesses(await listTerminalProcesses());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "process list failed");
    } finally {
      setBusy(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 3000);
    return () => clearInterval(timer);
  }, [refresh, refreshKey]);

  const act = async (fn: (id: string) => Promise<unknown>, id: string) => {
    try {
      await fn(id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "action failed");
    }
    void refresh();
  };

  return (
    <div className="flex h-full flex-col">
      <div className="mb-1 flex items-center justify-between text-[11px] uppercase tracking-wide text-muted-foreground">
        <span>Processes</span>
        <button type="button" onClick={() => void refresh()} aria-label="Refresh processes" className="hover:text-foreground">
          <RefreshCw size={12} className={cn(busy && "animate-spin")} />
        </button>
      </div>
      {error ? <div className="text-[11px] text-rose-300">{error}</div> : null}
      <div className="flex-1 overflow-y-auto font-mono text-[11px]">
        {processes.length === 0 ? (
          <div className="text-muted-foreground">No background processes.</div>
        ) : (
          processes.map((p) => (
            <div key={p.processId} className="group flex items-center gap-2 border-b border-white/5 py-1">
              <span className={cn("w-16 shrink-0", STATE_COLOR[p.state] ?? "text-muted-foreground")}>{p.state}</span>
              <span className="min-w-0 flex-1 truncate text-zinc-200" title={p.command}>
                {p.command}
              </span>
              {p.pid ? <span className="shrink-0 text-muted-foreground">pid {p.pid}</span> : null}
              {p.ports.length ? <span className="shrink-0 text-sky-300">:{p.ports.join(",:")}</span> : null}
              <div className="flex shrink-0 items-center gap-1 opacity-0 transition group-hover:opacity-100">
                <button type="button" title="Stop" onClick={() => void act(stopTerminalProcess, p.processId)} className="hover:text-amber-300">
                  <Square size={11} />
                </button>
                <button type="button" title="Restart" onClick={() => void act(restartTerminalProcess, p.processId)} className="hover:text-emerald-300">
                  <RotateCcw size={11} />
                </button>
                <button type="button" title="Kill" onClick={() => void act(killTerminalProcess, p.processId)} className="hover:text-rose-300">
                  <XCircle size={11} />
                </button>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
