"use client";

// ── API Keys & Connections ───────────────────────────────────────────────────
// The dedicated "plug your data in" menu. Every credential BlackEclipse accepts
// is listed here, grouped by what it powers, with a real Test button.
//
// Design rules this follows:
//   - The key value is NEVER rendered back: the field starts empty and the row
//     shows only a masked hint plus where the key came from.
//   - A key set by a real environment variable is shown as authoritative and is
//     not editable from the browser (a deployment owns it); the vault is for
//     local installs that have no env var.
//   - "Test" makes a real request and reports the real result — never a
//     success inferred from the key merely existing.
//   - Saving and removing are honest about the outcome.

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertCircle, Check, ExternalLink, Eye, EyeOff, KeyRound, Loader2,
  Plug, RefreshCcw, Save, ShieldCheck, Trash2, Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { cn } from "@/lib/utils";

interface ProviderKeyStatus {
  envVar: string;
  label: string;
  provider: string;
  category: "ai" | "market" | "crypto" | "economics";
  description: string;
  docsUrl?: string;
  publicValue: boolean;
  testable: boolean;
  fromEnv: boolean;
  stored: boolean;
  configured: boolean;
  hint?: string;
}

type TestResult = { ok: boolean; message: string; httpStatus?: number; latencyMs?: number };

const CATEGORY_ORDER: Array<{ id: ProviderKeyStatus["category"]; label: string; hint: string }> = [
  { id: "ai", label: "AI & LLM", hint: "Models for chat, research and the Investor Eye analyst." },
  { id: "market", label: "Market Data", hint: "Alternative quote, fundamental and news providers." },
  { id: "crypto", label: "Crypto", hint: "Higher-limit digital-asset market data." },
  { id: "economics", label: "Economics & Macro", hint: "Macro releases and indicator series." },
];

export function ApiKeysPanel() {
  const [keys, setKeys] = useState<ProviderKeyStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, TestResult>>({});
  const [reveal, setReveal] = useState<Record<string, boolean>>({});

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/provider-keys");
      const data = (await res.json()) as { keys?: ProviderKeyStatus[]; error?: string };
      if (Array.isArray(data.keys)) setKeys(data.keys);
      else setMessage(data.error ?? "Failed to load provider keys");
    } catch {
      setMessage("Failed to load provider keys");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async (envVar: string) => {
    const value = (drafts[envVar] ?? "").trim();
    setBusy(envVar);
    setMessage(null);
    try {
      const res = await fetch("/api/provider-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ envVar, value }),
      });
      const data = (await res.json()) as { ok?: boolean; keys?: ProviderKeyStatus[]; error?: string };
      if (!res.ok) {
        setMessage(data.error ?? "Failed to save the key");
        return;
      }
      if (Array.isArray(data.keys)) setKeys(data.keys);
      setDrafts((d) => ({ ...d, [envVar]: "" }));
      setEditing(null);
      const def = keys.find((k) => k.envVar === envVar);
      setMessage(value === "" ? `Cleared ${def?.label ?? envVar}.` : `Saved ${def?.label ?? envVar}.`);
    } catch {
      setMessage("Failed to save the key");
    } finally {
      setBusy(null);
    }
  };

  const remove = async (envVar: string) => {
    setBusy(envVar);
    setMessage(null);
    try {
      const res = await fetch(`/api/provider-keys?envVar=${encodeURIComponent(envVar)}`, { method: "DELETE" });
      const data = (await res.json()) as { keys?: ProviderKeyStatus[]; error?: string };
      if (!res.ok) {
        setMessage(data.error ?? "Failed to remove the key");
        return;
      }
      if (Array.isArray(data.keys)) setKeys(data.keys);
      const def = keys.find((k) => k.envVar === envVar);
      setMessage(`Removed ${def?.label ?? envVar}.`);
    } catch {
      setMessage("Failed to remove the key");
    } finally {
      setBusy(null);
    }
  };

  const runTest = async (envVar: string) => {
    setTesting(envVar);
    setResults((r) => ({ ...r, [envVar]: { ok: false, message: "Testing…" } }));
    try {
      const res = await fetch("/api/provider-keys", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ envVar, action: "test" }),
      });
      const data = (await res.json()) as TestResult & { error?: string };
      setResults((r) => ({
        ...r,
        [envVar]: data.error
          ? { ok: false, message: data.error }
          : { ok: data.ok, message: data.message, httpStatus: data.httpStatus, latencyMs: data.latencyMs },
      }));
    } catch {
      setResults((r) => ({ ...r, [envVar]: { ok: false, message: "Test request failed" } }));
    } finally {
      setTesting(null);
    }
  };

  const grouped = useMemo(
    () =>
      CATEGORY_ORDER.map((c) => ({
        ...c,
        items: keys.filter((k) => k.category === c.id),
      })).filter((g) => g.items.length > 0),
    [keys],
  );

  const configuredCount = keys.filter((k) => k.configured).length;

  return (
    <div className="animate-fade-in-up">
      <div className="flex items-start justify-between gap-4 mb-6">
        <div>
          <p className="text-[10px] uppercase tracking-[0.2em] text-primary font-bold mb-2 flex items-center gap-1.5">
            <Plug size={11} /> Connections
          </p>
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-primary/10 border border-primary/20 flex items-center justify-center shrink-0 shadow-sm shadow-primary/10">
              <KeyRound className="text-primary w-[18px] h-[18px]" />
            </div>
            <h2 className="font-serif text-lg font-semibold tracking-tight text-foreground">API Keys</h2>
          </div>
          <p className="text-xs text-muted-foreground mt-2 leading-relaxed max-w-xl">
            Plug your own data in. Keys are encrypted at rest in JDDS and never sent back to the
            browser — the field always starts empty. A key set by an environment variable is
            authoritative and shown as read-only.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <span className="text-[10px] font-mono text-muted-foreground">
            {configuredCount}/{keys.length} configured
          </span>
          <Button variant="outline" size="sm" className="cursor-pointer rounded-xl" onClick={() => void load()}>
            <RefreshCcw className="w-4 h-4" />
          </Button>
        </div>
      </div>

      {message && (
        <p className="text-xs text-muted-foreground mb-4 flex items-center gap-1.5">
          <AlertCircle className="w-3.5 h-3.5 text-primary" /> {message}
        </p>
      )}

      <div className="mb-5 flex items-center gap-2 rounded-xl border border-primary/20 bg-primary/5 px-4 py-2.5">
        <ShieldCheck className="w-3.5 h-3.5 text-primary shrink-0" />
        <p className="text-[10px] text-foreground/80 leading-relaxed">
          Zero-config is preserved: the app runs fully without any of these. A key only widens a
          provider&apos;s rate limit or unlocks an optional source.
        </p>
      </div>

      {loading ? (
        <p className="text-xs text-muted-foreground flex items-center gap-2">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading connections…
        </p>
      ) : (
        <div className="space-y-7">
          {grouped.map((group) => (
            <div key={group.id}>
              <div className="mb-2.5">
                <p className="text-[10px] uppercase tracking-[0.15em] font-bold text-primary">{group.label}</p>
                <p className="text-[10px] text-muted-foreground mt-0.5">{group.hint}</p>
              </div>
              <div className="space-y-2">
                {group.items.map((k) => (
                  <KeyRow
                    key={k.envVar}
                    item={k}
                    editing={editing === k.envVar}
                    draft={drafts[k.envVar] ?? ""}
                    reveal={Boolean(reveal[k.envVar])}
                    busy={busy === k.envVar}
                    testing={testing === k.envVar}
                    result={results[k.envVar]}
                    onEdit={() => setEditing(editing === k.envVar ? null : k.envVar)}
                    onDraft={(v) => setDrafts((d) => ({ ...d, [k.envVar]: v }))}
                    onReveal={() => setReveal((r) => ({ ...r, [k.envVar]: !r[k.envVar] }))}
                    onSave={() => void save(k.envVar)}
                    onRemove={() => void remove(k.envVar)}
                    onTest={() => void runTest(k.envVar)}
                  />
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      <p className="mt-6 text-[10px] text-muted-foreground/70 leading-relaxed">
        <Zap size={10} className="inline mr-1" />
        Keys resolve in this order: a real environment variable first, then the encrypted vault.
        Removing a vault key takes effect immediately.
      </p>
    </div>
  );
}

function KeyRow({
  item,
  editing,
  draft,
  reveal,
  busy,
  testing,
  result,
  onEdit,
  onDraft,
  onReveal,
  onSave,
  onRemove,
  onTest,
}: {
  item: ProviderKeyStatus;
  editing: boolean;
  draft: string;
  reveal: boolean;
  busy: boolean;
  testing: boolean;
  result?: TestResult;
  onEdit: () => void;
  onDraft: (v: string) => void;
  onReveal: () => void;
  onSave: () => void;
  onRemove: () => void;
  onTest: () => void;
}) {
  // A real env var owns the key; the browser cannot change it.
  const envOwned = item.fromEnv;

  return (
    <div
      className={cn(
        "rounded-2xl border px-4 py-3 transition-colors",
        item.configured ? "border-primary/25 bg-primary/[0.04]" : "border-border/20 glass-card",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <p className="text-[12px] font-semibold text-foreground flex items-center gap-2 flex-wrap">
            {item.label}
            <span className="text-[9px] font-mono text-muted-foreground/70">{item.envVar}</span>
            {item.configured ? (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[8px] font-bold border border-emerald-500/30 bg-emerald-500/10 text-emerald-300">
                <span className="w-1 h-1 rounded-full bg-emerald-400" />
                {envOwned ? "ENV" : "STORED"}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[8px] font-bold border border-border/40 text-muted-foreground">
                NOT SET
              </span>
            )}
          </p>
          <p className="text-[10px] text-muted-foreground mt-1 leading-relaxed">{item.description}</p>
          {item.hint && (
            <p className="text-[10px] font-mono text-muted-foreground/70 mt-1">{item.hint}</p>
          )}
        </div>

        <div className="flex items-center gap-1.5 shrink-0">
          {item.docsUrl && (
            <a
              href={item.docsUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 rounded-lg border border-border/30 px-2 py-1 text-[10px] text-muted-foreground hover:text-foreground hover:border-border/60"
            >
              Get key <ExternalLink size={10} />
            </a>
          )}
          {!envOwned && (
            <Button variant="outline" size="sm" className="cursor-pointer rounded-xl text-[10px] h-7 px-2.5" onClick={onEdit}>
              {item.configured ? "Replace" : "Add"}
            </Button>
          )}
          {item.testable && item.configured && (
            <Button
              variant="outline"
              size="sm"
              className="cursor-pointer rounded-xl text-[10px] h-7 px-2.5"
              disabled={testing}
              onClick={onTest}
            >
              {testing ? <Loader2 className="w-3 h-3 animate-spin" /> : "Test"}
            </Button>
          )}
          {item.stored && !envOwned && (
            <Button
              variant="outline"
              size="sm"
              className="cursor-pointer rounded-xl text-[10px] h-7 px-2 text-rose-400 hover:text-rose-300"
              disabled={busy}
              onClick={onRemove}
              title="Remove stored key"
            >
              {busy ? <Loader2 className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
            </Button>
          )}
        </div>
      </div>

      {editing && !envOwned && (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <div className="relative min-w-[220px] flex-1">
            <KeyRound className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
            <Input
              type={reveal || item.publicValue ? "text" : "password"}
              value={draft}
              autoFocus
              onChange={(e) => onDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onSave();
                if (e.key === "Escape") onEdit();
              }}
              placeholder={item.publicValue ? "http://localhost:11434/v1" : "Paste the key…"}
              className="pl-8 pr-9 font-mono text-xs"
            />
            {!item.publicValue && (
              <button
                type="button"
                onClick={onReveal}
                className="absolute right-2 top-1/2 -translate-y-1/2 p-1 rounded-md text-muted-foreground hover:text-primary cursor-pointer"
              >
                {reveal ? <EyeOff size={13} /> : <Eye size={13} />}
              </button>
            )}
          </div>
          <Button size="sm" className="cursor-pointer rounded-xl text-[11px]" disabled={busy} onClick={onSave}>
            {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin mr-1" /> : <Save className="w-3.5 h-3.5 mr-1" />}
            Save
          </Button>
          <span className="text-[10px] text-muted-foreground">Encrypted at rest · never returned</span>
        </div>
      )}

      {envOwned && (
        <p className="mt-2.5 text-[10px] text-muted-foreground/80 flex items-center gap-1.5">
          <Check size={11} className="text-emerald-400 shrink-0" />
          Set by the {item.envVar} environment variable — authoritative; the browser cannot change it.
        </p>
      )}

      {result && (
        <p
          className={cn(
            "mt-2.5 text-[10px] flex items-center gap-1.5",
            result.message === "Testing…"
              ? "text-muted-foreground"
              : result.ok ? "text-emerald-400" : "text-rose-400",
          )}
        >
          {result.message === "Testing…" ? (
            <Loader2 size={11} className="animate-spin shrink-0" />
          ) : result.ok ? (
            <Check size={11} className="shrink-0" />
          ) : (
            <AlertCircle size={11} className="shrink-0" />
          )}
          {result.message}
          {result.latencyMs !== undefined && <span className="text-muted-foreground/60">· {result.latencyMs} ms</span>}
        </p>
      )}
    </div>
  );
}
