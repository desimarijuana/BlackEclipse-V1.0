"use client";

// ── Setup danger zone (Settings → Data & Storage) ──────────────────────────
// Two explicit scopes, never one ambiguous "clear" button:
//   - Reset setup & API keys: config only, keeps chats/portfolio/research.
//   - Factory reset: wipes personal data, but is SCHEDULED because the running
//     web process cannot safely delete live SQLite on Windows. doctor.js runs
//     the wipe on the next boot, before it opens jdds.db.

import { useEffect, useState } from "react";
import { AlertTriangle, Database, Loader2, RotateCcw, Trash2 } from "@/lib/icons";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

type Mode = null | "setup" | "factory";

export function SetupDangerZone() {
  const [mode, setMode] = useState<Mode>(null);
  const [confirm, setConfirm] = useState("");
  const [backup, setBackup] = useState(true);
  const [includeEnv, setIncludeEnv] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [scheduled, setScheduled] = useState<Record<string, unknown> | null>(null);

  const refreshScheduled = async () => {
    try {
      const res = await fetch("/api/setup/reset", { cache: "no-store" });
      const data = (await res.json()) as { scheduled?: boolean; marker?: Record<string, unknown> | null };
      setScheduled(data.scheduled ? data.marker ?? {} : null);
    } catch {
      setScheduled(null);
    }
  };

  useEffect(() => {
    void refreshScheduled();
  }, []);

  const cancelScheduled = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/setup/reset", { method: "DELETE" });
      const data = (await res.json()) as { error?: string };
      if (!res.ok) throw new Error(data.error || "Could not cancel");
      setScheduled(null);
      setMessage("Scheduled factory reset cancelled. Nothing will be deleted.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not cancel");
    } finally {
      setBusy(false);
    }
  };

  const close = () => {
    setMode(null);
    setConfirm("");
    setError(null);
  };

  const submit = async () => {
    if (!mode) return;
    setBusy(true);
    setError(null);
    setMessage(null);
    try {
      const res = await fetch("/api/setup/reset", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          scope: mode,
          confirm,
          backup,
          includeEnv,
        }),
      });
      const data = (await res.json()) as {
        error?: string;
        reload?: string;
        scheduled?: boolean;
        command?: string;
        message?: string;
      };
      if (!res.ok) throw new Error(data.error || "Reset failed");

      if (data.reload) {
        window.location.assign(data.reload);
        return;
      }
      setMessage(
        data.message ||
          "Reset scheduled. Restart Eclipse to finish (or run `black reset --factory`).",
      );
      if (data.scheduled) setScheduled({});
      setMode(null);
      setConfirm("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Reset failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="mt-4 space-y-3">
      <div className="rounded-2xl border border-rose-500/20 bg-rose-500/[0.03] p-4">
        <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-rose-300">
          <AlertTriangle size={12} /> Setup &amp; reset
        </p>
        <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
          These actions change Eclipse itself, not just this browser. Read the scope before
          confirming.
        </p>

        {scheduled && (
          <div className="mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-amber-500/25 bg-amber-500/[0.06] p-2.5">
            <span className="text-[10px] text-amber-200">
              A factory reset is scheduled and will run on the next start.
            </span>
            <Button
              size="sm"
              variant="outline"
              className="ml-auto cursor-pointer rounded-lg border-amber-500/30 text-[10px] text-amber-200 hover:bg-amber-500/10"
              disabled={busy}
              onClick={() => void cancelScheduled()}
            >
              Cancel scheduled reset
            </Button>
          </div>
        )}

        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold text-foreground">
              <Database size={13} /> Reset setup &amp; API keys
            </p>
            <p className="mt-1 text-[9px] leading-relaxed text-muted-foreground">
              Clears onboarding, source choices, the AI config and all stored provider keys.
              Chats, portfolio, journal and research are kept.
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-2 cursor-pointer rounded-lg text-[10px]"
              onClick={() => { setMode("setup"); setConfirm(""); setError(null); setMessage(null); }}
            >
              <RotateCcw size={12} /> Reset setup
            </Button>
          </div>

          <div className="rounded-xl border border-rose-500/20 bg-rose-500/[0.03] p-3">
            <p className="flex items-center gap-1.5 text-[11px] font-semibold text-rose-200">
              <Trash2 size={13} /> Factory reset — start from scratch
            </p>
            <p className="mt-1 text-[9px] leading-relaxed text-muted-foreground">
              Wipes the databases, runtime state, backups, keys, chats, portfolio, journal,
              research, skills and artifacts. Source code is never touched.
            </p>
            <Button
              variant="outline"
              size="sm"
              className="mt-2 cursor-pointer rounded-lg border-rose-500/30 text-[10px] text-rose-300 hover:bg-rose-500/10"
              onClick={() => { setMode("factory"); setConfirm(""); setError(null); setMessage(null); }}
            >
              <Trash2 size={12} /> Factory reset
            </Button>
          </div>
        </div>

        {mode && (
          <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3">
            <p className="text-[10px] font-semibold text-foreground">
              {mode === "setup"
                ? "Type RESET to clear setup and API keys."
                : "Type WIPE to permanently remove all local Eclipse data."}
            </p>
            <Input
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              placeholder={mode === "setup" ? "RESET" : "WIPE"}
              className="mt-2 h-7 max-w-[220px] font-mono text-[11px]"
              autoComplete="off"
            />

            {mode === "factory" && (
              <div className="mt-2 space-y-1.5">
                <label className="flex items-start gap-2 text-[9px] text-muted-foreground">
                  <input type="checkbox" className="mt-0.5" checked={backup} onChange={(e) => setBackup(e.target.checked)} />
                  <span>Create a backup first (saved outside the wipe targets).</span>
                </label>
                <label className="flex items-start gap-2 text-[9px] text-muted-foreground">
                  <input type="checkbox" className="mt-0.5" checked={includeEnv} onChange={(e) => setIncludeEnv(e.target.checked)} />
                  <span>Also delete <code>.env</code> — this removes host configuration and secrets.</span>
                </label>
                <p className="text-[9px] text-amber-300/90">
                  This is scheduled. Restart Eclipse to finish (or run <code>black reset --factory</code>).
                </p>
              </div>
            )}

            <div className="mt-2 flex items-center gap-2">
              <Button
                size="sm"
                variant="outline"
                className={cn(
                  "cursor-pointer rounded-lg text-[10px]",
                  mode === "factory" && "border-rose-500/30 text-rose-300 hover:bg-rose-500/10",
                )}
                disabled={busy || confirm !== (mode === "setup" ? "RESET" : "WIPE")}
                onClick={() => void submit()}
              >
                {busy ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                {mode === "setup" ? "Reset setup" : "Schedule factory reset"}
              </Button>
              <Button size="sm" variant="ghost" className="cursor-pointer rounded-lg text-[10px]" onClick={close}>
                Cancel
              </Button>
            </div>
            {error && <p className="mt-2 text-[9px] text-rose-300">{error}</p>}
          </div>
        )}

        {message && (
          <p className="mt-3 rounded-xl border border-emerald-500/20 bg-emerald-500/[0.05] p-2.5 text-[10px] text-emerald-200">
            {message}
          </p>
        )}
      </div>
    </div>
  );
}
