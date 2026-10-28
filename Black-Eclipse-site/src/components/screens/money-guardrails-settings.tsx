"use client";

// ── Money guardrails settings ────────────────────────────────────────────────
// The operator surface for scam/coercion, impaired-spending, crisis, aggregate
// limits and the money confirm gate. The UI only edits the operator's own
// settings; every decision is enforced by the Python runtime, and the agent can
// never change these values.

import { useCallback, useEffect, useState } from "react";
import { Loader2, ShieldAlert, Wallet } from "@/lib/icons";
import { cn } from "@/lib/utils";
import { Field, Panel, SectionHeader, SubSection, Toggle } from "./settings-ui";
import {
  getMoneyGuardrailStatus,
  updateMoneyGuardrailConfig,
  type MoneyGuardrailConfig,
  type MoneyGuardrailStatus,
} from "@/lib/harness/finance-guardrails-client";

const DECISION_TONE: Record<string, string> = {
  deny: "text-rose-300",
  escalate: "text-rose-300",
  confirm: "text-amber-300",
  allow: "text-emerald-300",
};

export function MoneyGuardrailsSettings() {
  const [status, setStatus] = useState<MoneyGuardrailStatus | null>(null);
  const [config, setConfig] = useState<MoneyGuardrailConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saved, setSaved] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const next = await getMoneyGuardrailStatus();
      setStatus(next);
      setConfig(next.config);
    } catch (err) {
      setError(err instanceof Error ? err.message : "money guardrails unavailable");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const patch = (next: Partial<MoneyGuardrailConfig>) => {
    setConfig((current) => (current ? { ...current, ...next } : current));
    setSaved(false);
  };

  const save = async () => {
    if (!config) return;
    setSaving(true);
    setError(null);
    try {
      const next = await updateMoneyGuardrailConfig(config);
      setConfig(next);
      await load();
      setSaved(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : "could not save guardrails");
    } finally {
      setSaving(false);
    }
  };

  if (!config) {
    return (
      <div className="max-w-3xl">
        <SectionHeader
          icon={Wallet}
          title="Money guardrails"
          description="Scam and coercion checks, impaired-spending protection, crisis mode, aggregate limits and the money confirm gate."
        />
        <Panel className="p-6">
          {error ? (
            <p className="text-xs text-rose-300">{error}</p>
          ) : (
            <p className="flex items-center gap-2 text-xs text-muted-foreground">
              <Loader2 size={14} className="animate-spin" /> Loading guardrails…
            </p>
          )}
        </Panel>
      </div>
    );
  }

  const number = (key: keyof MoneyGuardrailConfig) => ({
    type: "number" as const,
    min: 0,
    value: String(config[key] ?? 0),
    onChange: (event: React.ChangeEvent<HTMLInputElement>) =>
      patch({ [key]: Number(event.target.value) || 0 } as Partial<MoneyGuardrailConfig>),
    className:
      "w-full rounded-xl border border-border/40 bg-transparent px-2.5 py-1.5 text-xs text-foreground focus:border-primary/40 focus:outline-none",
  });

  const inputClass =
    "w-full rounded-xl border border-border/40 bg-transparent px-2.5 py-1.5 text-xs text-foreground focus:border-primary/40 focus:outline-none";

  return (
    <div className="max-w-3xl space-y-6">
      <SectionHeader
        icon={Wallet}
        title="Money guardrails"
        description="Money movement always passes these checks. They can only add friction, never grant authority. The agent cannot change them — only you can."
      />

      {error && <p className="text-xs text-rose-300">{error}</p>}

      <Panel className="p-5">
        <SubSection title="Emergency" description="These apply immediately, across every channel.">
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-4 rounded-xl border border-rose-400/20 bg-rose-500/[0.06] p-3">
              <div>
                <p className="text-xs font-medium text-foreground">Panic pause</p>
                <p className="text-[10px] text-muted-foreground">
                  Stop all money movement now. Nothing is sent until you turn this off.
                </p>
              </div>
              <Toggle checked={config.panicPaused} onChange={(v) => patch({ panicPaused: v })} />
            </div>
            <div className="flex items-center justify-between gap-4 rounded-xl border border-border/30 p-3">
              <div>
                <p className="text-xs font-medium text-foreground">Crisis mode</p>
                <p className="text-[10px] text-muted-foreground">
                  Blocks discretionary trading; transfers need a long cooling-off and a check-in.
                </p>
              </div>
              <Toggle checked={config.crisisMode} onChange={(v) => patch({ crisisMode: v })} />
            </div>
            <div className="flex items-center justify-between gap-4 rounded-xl border border-border/30 p-3">
              <div>
                <p className="text-xs font-medium text-foreground">Impaired today</p>
                <p className="text-[10px] text-muted-foreground">
                  Adds a 30-minute pause and typed confirmation to every money movement.
                </p>
              </div>
              <Toggle checked={config.impairedMode} onChange={(v) => patch({ impairedMode: v })} />
            </div>
            <Field label="Trusted contact" hint="Named during crisis confirmation. Leave blank if you prefer.">
              <input
                value={config.trustedContact}
                onChange={(event) => patch({ trustedContact: event.target.value })}
                className={inputClass}
                placeholder="e.g. Sam — 555-0100"
              />
            </Field>
          </div>
        </SubSection>
      </Panel>

      <Panel className="p-5">
        <SubSection title="Limits" description="Bounds on repetition and size, measured against your own ledger.">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Per-transaction cap" hint="0 = no cap">
              <input {...number("perTxnCap")} />
            </Field>
            <Field label="Daily cap" hint="0 = no cap">
              <input {...number("dailyCap")} />
            </Field>
            <Field label="Movements per hour" hint="0 = no velocity limit">
              <input {...number("velocityPerHour")} />
            </Field>
            <Field label="High-value review from" hint="0 = off">
              <input {...number("highValue")} />
            </Field>
            <Field label="Cooling-off (seconds)">
              <input {...number("coolingSeconds")} />
            </Field>
            <Field label="Baseline multiplier" hint="Flag amounts above this multiple of your p95.">
              <input {...number("baselineMultiplier")} />
            </Field>
          </div>
          <Field label="Mode" hint="off disables the guardrails (panic pause still applies).">
            <select
              value={config.mode}
              onChange={(event) =>
                patch({ mode: event.target.value as MoneyGuardrailConfig["mode"] })
              }
              className={inputClass}
            >
              <option value="guard">guard (default)</option>
              <option value="strict">strict</option>
              <option value="off">off</option>
            </select>
          </Field>
        </SubSection>
      </Panel>

      <Panel className="p-5">
        <SubSection title="Counterparties" description="One per line, or comma-separated.">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Always allow" hint="When non-empty, only these may be paid.">
              <textarea
                value={config.allowlist.join(", ")}
                onChange={(event) =>
                  patch({
                    allowlist: event.target.value
                      .split(",")
                      .map((v) => v.trim())
                      .filter(Boolean),
                  })
                }
                rows={3}
                className={cn(inputClass, "font-mono")}
              />
            </Field>
            <Field label="Always block">
              <textarea
                value={config.blocklist.join(", ")}
                onChange={(event) =>
                  patch({
                    blocklist: event.target.value
                      .split(",")
                      .map((v) => v.trim())
                      .filter(Boolean),
                  })
                }
                rows={3}
                className={cn(inputClass, "font-mono")}
              />
            </Field>
          </div>
        </SubSection>
      </Panel>

      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={() => void save()}
          disabled={saving}
          className="inline-flex items-center gap-1.5 rounded-xl bg-primary px-3 py-1.5 text-xs font-medium text-primary-foreground disabled:opacity-50"
        >
          {saving && <Loader2 size={13} className="animate-spin" />}
          Save guardrails
        </button>
        {saved && <span className="text-[11px] text-emerald-300">Saved.</span>}
      </div>

      <Panel className="p-5">
        <SubSection title="Today" description="Aggregates from the runtime ledger.">
          <div className="grid grid-cols-3 gap-3">
            <Stat label="Moved today" value={fmt(status?.aggregates.spendToday)} />
            <Stat label="Last hour" value={String(status?.aggregates.countLastHour ?? 0)} />
            <Stat label="30 days" value={fmt(status?.aggregates.spend30d)} />
          </div>
        </SubSection>
        <div className="mt-5 space-y-2">
          <p className="text-xs font-semibold text-foreground">Recent decisions</p>
          {(status?.recent ?? []).length === 0 && (
            <p className="text-[11px] text-muted-foreground">No money intents recorded yet.</p>
          )}
          {(status?.recent ?? []).slice(0, 8).map((intent) => (
            <div
              key={intent.id}
              className="flex items-start justify-between gap-3 rounded-xl border border-border/25 px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate text-[11px] text-foreground">
                  {intent.action}
                  {intent.amount != null ? ` · ${fmt(intent.amount)} ${intent.currency ?? ""}` : ""}
                  {intent.counterparty ? ` → ${intent.counterparty}` : ""}
                </p>
                <p className="truncate text-[10px] text-muted-foreground">
                  {intent.reasons[0] ?? intent.rules.join(", ")}
                </p>
              </div>
              <span className={cn("shrink-0 text-[10px] font-bold uppercase", DECISION_TONE[intent.decision])}>
                {intent.decision}
              </span>
            </div>
          ))}
        </div>
      </Panel>

      <p className="flex items-start gap-2 text-[10px] leading-relaxed text-muted-foreground">
        <ShieldAlert size={13} className="mt-0.5 shrink-0 text-primary" />
        Guardrails are deterministic and explainable. They never fabricate data and they cannot be
        loosened by the agent, a skill, a plugin or an MCP server.
      </p>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-border/25 px-3 py-2">
      <p className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 font-mono text-sm text-foreground">{value}</p>
    </div>
  );
}

function fmt(value: number | null | undefined): string {
  if (value == null) return "—";
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}
