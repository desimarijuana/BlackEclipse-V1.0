"use client";

// ── Feature packs (Settings → Data & Storage) ──────────────────────────────
// The slim installer ships the core only. Five optional Python capabilities are
// separate archives so the download stays small. Before this panel existed a
// slim install simply lacked them, with no in-app way to add them — the user
// hit "this feature is unavailable" and had nothing to click.
//
// The panel polls while a download runs (one job at a time, server-held), shows
// real received/total bytes, and never claims success before the server's
// checksum check passes.

import { useCallback, useEffect, useRef, useState } from "react";
import { AlertTriangle, Boxes, CheckCircle2, Download, Loader2, Trash2 } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Panel, SubSection } from "@/components/screens/settings-ui";
import { cn } from "@/lib/utils";

interface PackStatus {
  name: string;
  label: string;
  summary: string;
  unlocks: string[];
  packages: string[];
  installed: boolean;
  bytes: number;
  downloadable: boolean;
  blockedReason?: string;
}

interface PackJob {
  pack: string;
  phase: "downloading" | "verifying" | "installing" | "done" | "error";
  received: number;
  total: number;
  message?: string;
  startedAt: string;
  finishedAt?: string;
}

interface Snapshot {
  supported: boolean;
  reason?: string;
  version?: string;
  target?: string;
  packs: PackStatus[];
  active: PackJob | null;
  last: PackJob | null;
}

function mb(bytes: number): string {
  if (!bytes) return "—";
  const value = bytes / (1024 * 1024);
  return `${value >= 10 ? Math.round(value) : value.toFixed(1)} MB`;
}

const PHASE_COPY: Record<PackJob["phase"], string> = {
  downloading: "Downloading",
  verifying: "Checking the download",
  installing: "Installing",
  done: "Installed",
  error: "Failed",
};

export function FeaturePacksSettings() {
  const [state, setState] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/desktop/packs", { cache: "no-store" });
      const data = (await res.json()) as Snapshot & { error?: string };
      if (!res.ok) throw new Error(data.error || "Could not read the feature packs");
      setState(data);
      setError(null);
      return data;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not read the feature packs");
      return null;
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [load]);

  // Poll only while a job is running; stop as soon as the server reports idle.
  useEffect(() => {
    const running = Boolean(state?.active);
    if (running && !pollRef.current) {
      pollRef.current = setInterval(() => {
        void load();
      }, 900);
    }
    if (!running && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, [state?.active, load]);

  const act = async (action: "install" | "remove", pack: string) => {
    setBusy(pack);
    setError(null);
    try {
      const res = await fetch("/api/desktop/packs", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ action, pack }),
      });
      const data = (await res.json()) as { error?: string } & Partial<Snapshot>;
      if (!res.ok) throw new Error(data.error || "Request failed");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Request failed");
    } finally {
      setBusy(null);
    }
  };

  const active = state?.active ?? null;
  const lastError = state?.last?.phase === "error" ? state.last : null;

  return (
    <Panel className="mt-4 p-5 md:p-6">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 rounded-xl border border-white/10 bg-white/[0.04] p-2">
          <Boxes size={15} className="text-primary" />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <h3 className="text-xs font-semibold tracking-tight text-foreground">Feature packs</h3>
            {state?.version ? (
              <span className="font-mono text-[9px] text-muted-foreground/70">
                {state.target ?? "this platform"} · v{state.version}
              </span>
            ) : null}
          </div>
          <p className="mt-1 max-w-xl text-[10px] leading-relaxed text-muted-foreground">
            The installer ships the core only to keep the download small. Anything missing here is a
            single click away. Downloads come from the same release as the app and are checked
            against a published SHA-256 before anything is installed.
          </p>
        </div>
      </div>

      {!state && !error && (
        <div className="mt-4 flex items-center gap-2 text-[10px] text-muted-foreground">
          <Loader2 size={12} className="animate-spin" /> Reading components…
        </div>
      )}

      {state && !state.supported && (
        <div className="mt-4 rounded-xl border border-white/10 bg-white/[0.02] p-3">
          <p className="flex items-start gap-2 text-[10px] leading-relaxed text-muted-foreground">
            <AlertTriangle size={12} className="mt-0.5 shrink-0 text-amber-300" />
            <span>{state.reason}</span>
          </p>
        </div>
      )}

      {state?.supported && state.packs.length === 0 && (
        <p className="mt-4 text-[10px] text-muted-foreground">
          This build includes every pack already — nothing to download.
        </p>
      )}

      {state?.supported && state.packs.length > 0 && (
        <SubSection title="Optional components" className="mt-4">
          <div className="space-y-2">
            {state.packs.map((pack) => {
              const running = active?.pack === pack.name;
              const donePct =
                running && active && active.total > 0
                  ? Math.min(100, Math.round((active.received / active.total) * 100))
                  : 0;
              return (
                <div
                  key={pack.name}
                  className={cn(
                    "rounded-xl border p-3 transition-colors",
                    pack.installed
                      ? "border-emerald-500/20 bg-emerald-500/[0.04]"
                      : "border-white/10 bg-white/[0.02]",
                  )}
                >
                  <div className="flex flex-wrap items-start gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-[11px] font-semibold text-foreground">{pack.label}</p>
                        {pack.installed ? (
                          <span className="inline-flex items-center gap-1 rounded-full border border-emerald-500/25 bg-emerald-500/10 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wide text-emerald-300">
                            <CheckCircle2 size={9} /> Installed
                          </span>
                        ) : (
                          <span className="rounded-full border border-white/10 bg-white/[0.04] px-1.5 py-0.5 text-[9px] text-muted-foreground">
                            {mb(pack.bytes)} download
                          </span>
                        )}
                      </div>
                      <p className="mt-1 max-w-md text-[10px] leading-relaxed text-muted-foreground">
                        {pack.summary}
                      </p>
                      {pack.unlocks.length > 0 && (
                        <p className="mt-1 text-[9px] text-muted-foreground/70">
                          {pack.unlocks.join(" · ")}
                        </p>
                      )}
                      {!pack.installed && !pack.downloadable && pack.blockedReason && (
                        <p className="mt-1 text-[9px] text-amber-300/90">{pack.blockedReason}</p>
                      )}
                    </div>

                    <div className="ml-auto flex items-center gap-2">
                      {running ? (
                        <span className="inline-flex items-center gap-1.5 text-[10px] text-muted-foreground">
                          <Loader2 size={11} className="animate-spin" />
                          {PHASE_COPY[active.phase]}
                          {active.phase === "downloading" && active.total > 0
                            ? ` · ${donePct}%`
                            : ""}
                        </span>
                      ) : pack.installed ? (
                        <Button
                          variant="ghost"
                          size="sm"
                          className="cursor-pointer rounded-lg text-[10px] text-muted-foreground hover:text-rose-300"
                          disabled={Boolean(active) || busy === pack.name}
                          onClick={() => void act("remove", pack.name)}
                        >
                          <Trash2 size={11} /> Remove
                        </Button>
                      ) : (
                        <Button
                          variant="outline"
                          size="sm"
                          className="cursor-pointer rounded-lg border-primary/30 text-[10px] text-primary hover:bg-primary/10"
                          disabled={Boolean(active) || busy === pack.name || !pack.downloadable}
                          onClick={() => void act("install", pack.name)}
                        >
                          {busy === pack.name ? (
                            <Loader2 size={11} className="animate-spin" />
                          ) : (
                            <Download size={11} />
                          )}
                          Download
                        </Button>
                      )}
                    </div>
                  </div>

                  {running && (
                    <div className="mt-2.5 h-1 overflow-hidden rounded-full bg-white/[0.06]">
                      <div
                        className={cn(
                          "h-full rounded-full bg-primary transition-[width] duration-300",
                          active?.phase !== "downloading" && "animate-pulse",
                        )}
                        style={{
                          width:
                            active?.phase === "downloading" && active.total > 0
                              ? `${donePct}%`
                              : "100%",
                        }}
                      />
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </SubSection>
      )}

      {lastError && (
        <p className="mt-3 flex items-start gap-2 rounded-xl border border-rose-500/20 bg-rose-500/[0.05] p-2.5 text-[10px] text-rose-300">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          <span>{lastError.message ?? "That pack could not be installed."}</span>
        </p>
      )}

      {error && (
        <p className="mt-3 flex items-start gap-2 rounded-xl border border-rose-500/20 bg-rose-500/[0.05] p-2.5 text-[10px] text-rose-300">
          <AlertTriangle size={12} className="mt-0.5 shrink-0" />
          <span>{error}</span>
        </p>
      )}

      {state?.supported && (
        <p className="mt-3 text-[9px] leading-relaxed text-muted-foreground/70">
          A pack becomes available as soon as its files land — no restart needed. Removing one frees
          the space and only disables that capability; nothing else changes.
        </p>
      )}
    </Panel>
  );
}
