"use client";

import { useCallback, useEffect, useState } from "react";
import { AlertCircle, Play, RefreshCw, Square } from "@/lib/icons";
import {
  diagnoseRuntime,
  listAdapters,
  listRuntimes,
  recoverRuntime,
  restartApplication,
  startApplication,
  stopApplication,
  type AdapterView,
  type RuntimeView,
} from "@/lib/harness/clients/application-browser";
import { cn } from "@/lib/utils";

//: Health status → a tint. `RUNNING` is NOT `HEALTHY`: the state column and the
//: health column are shown separately so "the process exists" is never mistaken
//: for "the application works".
function stateTint(state: string): string {
  switch (state) {
    case "RUNNING":
      return "text-emerald-300";
    case "DEGRADED":
      return "text-amber-300";
    case "FAILED":
      return "text-rose-300";
    case "STOPPED":
      return "text-zinc-400";
    default:
      return "text-sky-300";
  }
}

function healthTint(status: string): string {
  if (status === "HEALTHY") return "text-emerald-300";
  if (status === "DEGRADED") return "text-amber-300";
  if (status === "UNHEALTHY") return "text-rose-300";
  return "text-muted-foreground";
}

export function ApplicationRuntimePanel() {
  const [runtimes, setRuntimes] = useState<RuntimeView[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [diagnosis, setDiagnosis] = useState<{ runtimeId: string; text: string } | null>(null);
  const [adapters, setAdapters] = useState<{
    orchestrators: AdapterView[];
    infrastructure: AdapterView[];
    cloudProviders: AdapterView[];
  } | null>(null);

  const refresh = useCallback(async () => {
    try {
      setRuntimes(await listRuntimes());
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "runtime list failed");
    }
  }, []);

  useEffect(() => {
    void refresh();
    listAdapters()
      .then(setAdapters)
      .catch(() => undefined);
    const timer = setInterval(() => void refresh(), 5000);
    return () => clearInterval(timer);
  }, [refresh]);

  const run = async (key: string, fn: () => Promise<unknown>) => {
    setBusy(key);
    try {
      await fn();
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "action failed");
    } finally {
      setBusy(null);
    }
  };

  const onDiagnose = async (runtimeId: string) => {
    try {
      const body = await diagnoseRuntime(runtimeId);
      setDiagnosis({ runtimeId, text: `${body.diagnosis.category}: ${body.diagnosis.message}` });
    } catch (err) {
      setError(err instanceof Error ? err.message : "diagnosis failed");
    }
  };

  return (
    <div className="flex h-full flex-col text-[11px]">
      <div className="mb-1 flex items-center justify-between uppercase tracking-wide text-muted-foreground">
        <span>Applications</span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            disabled={busy === "start"}
            onClick={() => void run("start", () => startApplication({ install: true }))}
            aria-label="Start the project"
            className="hover:text-foreground disabled:opacity-40"
          >
            <Play size={12} />
          </button>
          <button type="button" onClick={() => void refresh()} aria-label="Refresh" className="hover:text-foreground">
            <RefreshCw size={12} />
          </button>
        </div>
      </div>
      {error ? <div className="mb-1 text-[11px] text-rose-300">{error}</div> : null}
      <div className="flex-1 overflow-y-auto">
        {runtimes.length === 0 ? (
          <div className="text-muted-foreground">No applications are running.</div>
        ) : (
          runtimes.map((rt) => (
            <div key={rt.runtimeId} className="border-b border-white/5 py-1.5">
              <div className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-zinc-200">
                  {rt.descriptor?.name ?? rt.applicationId}
                </span>
                <span className={cn("shrink-0", stateTint(rt.state))}>{rt.state}</span>
                <span className={cn("shrink-0", healthTint(rt.health?.status ?? "UNKNOWN"))}>
                  {rt.health?.status ?? "UNKNOWN"}
                </span>
              </div>
              {rt.descriptor ? (
                <div className="mt-0.5 truncate text-muted-foreground">
                  {rt.descriptor.framework || rt.descriptor.language || "project"}
                  {rt.descriptor.packageManager ? ` · ${rt.descriptor.packageManager}` : ""}
                  {rt.ports.length ? ` · ports ${rt.ports.map((p) => p.port).join(", ")}` : ""}
                </div>
              ) : null}
              {rt.services.length ? (
                <div className="mt-0.5 truncate text-muted-foreground">
                  {rt.services.map((s) => s).join(" · ")}
                </div>
              ) : null}
              {rt.lastError ? (
                <div className="mt-0.5 flex items-center gap-1 text-rose-300">
                  <AlertCircle size={11} /> {rt.lastError.category ?? "error"}
                </div>
              ) : null}
              <div className="mt-1 flex items-center gap-3 text-muted-foreground">
                {rt.state !== "STOPPED" ? (
                  <button type="button" onClick={() => void run(`stop:${rt.runtimeId}`, () => stopApplication(rt.runtimeId))} className="flex items-center gap-1 hover:text-foreground">
                    <Square size={10} /> Stop
                  </button>
                ) : null}
                <button type="button" onClick={() => void run(`restart:${rt.runtimeId}`, () => restartApplication(rt.runtimeId))} className="hover:text-foreground">
                  Restart
                </button>
                <button type="button" onClick={() => void onDiagnose(rt.runtimeId)} className="hover:text-foreground">
                  Diagnose
                </button>
                {rt.state === "DEGRADED" || rt.state === "FAILED" ? (
                  <button type="button" onClick={() => void run(`recover:${rt.runtimeId}`, () => recoverRuntime(rt.runtimeId))} className="hover:text-foreground">
                    Recover
                  </button>
                ) : null}
              </div>
              {diagnosis && diagnosis.runtimeId === rt.runtimeId ? (
                <div className="mt-1 text-amber-200">{diagnosis.text}</div>
              ) : null}
            </div>
          ))
        )}
      </div>
      {adapters ? <RuntimeAdapterFooter adapters={adapters} /> : null}
    </div>
  );
}

/** The provider availability footer: orchestration / infrastructure / cloud.
 *  A provider whose tool is absent is listed plainly as unavailable — never a
 *  fabricated capability. */
function RuntimeAdapterFooter({
  adapters,
}: {
  adapters: { orchestrators: AdapterView[]; infrastructure: AdapterView[]; cloudProviders: AdapterView[] };
}) {
  const all = [
    ...adapters.orchestrators,
    ...adapters.infrastructure,
    ...adapters.cloudProviders,
  ];
  if (all.length === 0) return null;
  return (
    <div className="mt-auto border-t border-white/5 pt-1.5 text-[10px] text-muted-foreground">
      <span className="uppercase tracking-wide">Providers</span>
      <div className="mt-0.5 flex flex-wrap gap-x-2 gap-y-0.5">
        {all.map((adapter) => (
          <span key={adapter.name} className={cn(adapter.available ? "text-emerald-300" : "text-zinc-500")}>
            {adapter.name}
          </span>
        ))}
      </div>
    </div>
  );
}
