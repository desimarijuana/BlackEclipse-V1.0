"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "@/lib/icons";
import { listPorts, type PortEntry } from "@/lib/harness/clients/terminal-browser";
import { cn } from "@/lib/utils";

export function PortPanel() {
  const [ports, setPorts] = useState<PortEntry[]>([]);
  const [error, setError] = useState<string | null>(null);

  const refresh = async () => {
    try {
      const { ports: listed } = await listPorts();
      setPorts(listed);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "port list failed");
    }
  };

  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 4000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="flex h-full flex-col">
      <div className="mb-1 flex items-center justify-between text-[11px] uppercase tracking-wide text-muted-foreground">
        <span>Ports in use</span>
        <button type="button" onClick={() => void refresh()} aria-label="Refresh ports" className="hover:text-foreground">
          <RefreshCw size={12} />
        </button>
      </div>
      {error ? <div className="text-[11px] text-rose-300">{error}</div> : null}
      <div className="flex-1 overflow-y-auto font-mono text-[11px]">
        {ports.length === 0 ? (
          <div className="text-muted-foreground">No listening ports.</div>
        ) : (
          ports.map((p, i) => (
            <div key={`${p.port}-${p.pid}-${i}`} className="flex items-center gap-2 border-b border-white/5 py-1">
              <span className={cn("w-14 shrink-0", p.processId ? "text-sky-300" : "text-zinc-300")}>{p.port}</span>
              <span className="min-w-0 flex-1 truncate text-muted-foreground">{p.address ?? ""}</span>
              <span className="shrink-0 text-zinc-300">pid {p.pid ?? "?"}</span>
              {p.processId ? <span className="shrink-0 text-emerald-300">Eclipse</span> : null}
            </div>
          ))
        )}
      </div>
    </div>
  );
}
