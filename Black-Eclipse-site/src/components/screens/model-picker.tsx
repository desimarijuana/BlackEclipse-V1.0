"use client";

// ── Model picker ─────────────────────────────────────────────────────────────
// The runtime's declared models as a real dropdown, PLUS a free-text field so a
// custom id is always typeable (never an allowlist). For a provider the runtime
// can only enumerate at RUNTIME (Ollama, LM Studio, a router), a "Discover" action
// probes the live endpoint and merges the models it actually serves — so the
// operator sees their installed models, not a static sample.

import { useEffect, useMemo, useState } from "react";
import { Layers, RefreshCw } from "@/lib/icons";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { discoverRuntimeModels } from "@/lib/harness/model-runtime-browser";
import {
  compactModels,
  MODEL_LIST_SOFT_LIMIT,
  useEnabledModelsStore,
  useHydrateEnabledModels,
} from "@/lib/agent/enabled-models";
import { ManageModelsDialog } from "./manage-models-dialog";

interface Props {
  value: string;
  options: string[];
  windowKnown: boolean;
  windowLabel: string | null;
  onChange: (model: string) => void;
  /** The runtime provider id, for a live discovery probe. */
  providerId?: string;
  baseUrl: string;
  apiKey?: string;
  /** Whether this provider can enumerate its models at runtime. */
  canDiscover?: boolean;
  /** Called with the full, merged option list after a successful discovery. */
  onDiscovered?: (models: string[]) => void;
}

export function ModelPicker({
  value,
  options,
  windowKnown,
  windowLabel,
  onChange,
  providerId,
  baseUrl,
  apiKey,
  canDiscover,
  onDiscovered,
}: Props) {
  useHydrateEnabledModels();
  const [extra, setExtra] = useState<string[]>([]);
  const [discovering, setDiscovering] = useState(false);
  const [note, setNote] = useState<{ kind: "ok" | "error"; text: string } | null>(null);
  const [manageOpen, setManageOpen] = useState(false);

  // A discovered set belongs to one provider/endpoint; drop it when either
  // changes so a stale list never masquerades as this provider's models.
  useEffect(() => {
    setExtra([]);
    setNote(null);
  }, [providerId, baseUrl]);

  const enabled = useEnabledModelsStore((s) => (providerId ? s.providers[providerId] : undefined));
  const enable = useEnabledModelsStore((s) => s.enable);

  // The FULL list (declared + discovered) — what the Manage dialog curates.
  const allModels = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const m of [...options, ...extra]) {
      if (m && !seen.has(m)) {
        seen.add(m);
        out.push(m);
      }
    }
    if (value && !seen.has(value)) out.unshift(value);
    return out;
  }, [options, extra, value]);

  // Only the ENABLED (or, when uncurated, a capped slice) reach the dropdown, so
  // a provider listing hundreds of models never floods the list.
  const compact = useMemo(
    () => compactModels(providerId ?? "", allModels, { explicitEnabled: enabled, selected: value }),
    [providerId, allModels, enabled, value],
  );

  // The current value is always present in the list (even when the catalog has
  // never heard of it), so the select shows the real model id — never a raw
  // `__custom__` sentinel. The free-text field below is how a brand-new id is
  // typed (the catalog is a convenience list, never an allowlist).
  const list = useMemo(() => {
    if (value && !compact.models.includes(value)) return [value, ...compact.models];
    return compact.models;
  }, [compact.models, value]);

  const discover = async (): Promise<boolean> => {
    if (!providerId || discovering) return false;
    setDiscovering(true);
    setNote(null);
    try {
      const res = await discoverRuntimeModels(providerId, { baseUrl, apiKey, model: value });
      if (!res.ok) {
        setNote({ kind: "error", text: res.detail || "Discovery failed" });
        return false;
      }
      const ids = res.models.map((m) => m.id).filter(Boolean);
      setExtra(ids);
      setNote({
        kind: "ok",
        text: ids.length ? `Found ${ids.length} model${ids.length === 1 ? "" : "s"}` : "The provider listed no models",
      });
      onDiscovered?.(ids);
      // If nothing is selected yet, adopt the provider's first model.
      if (!value && ids.length) onChange(ids[0]);
      return true;
    } catch (err) {
      setNote({ kind: "error", text: err instanceof Error ? err.message : "Discovery failed" });
      return false;
    } finally {
      setDiscovering(false);
    }
  };

  // A single "Discover" action that always curates: it probes, then opens the
  // Manage dialog so the operator picks what to surface (never a wall of ids).
  const discoverAndManage = async () => {
    if (!providerId) return;
    if (canDiscover) await discover();
    setManageOpen(true);
  };

  const [custom, setCustom] = useState(false);

  return (
    <div className="space-y-2">
      {!custom && (
        <Select
          value={value}
          onValueChange={(v) => {
            if (v) onChange(v);
          }}
        >
          <SelectTrigger className="w-full font-mono">
            <SelectValue placeholder="Select a model" />
          </SelectTrigger>
          <SelectContent>
            {list.map((m) => (
              <SelectItem key={m} value={m}>
                {m}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}
      {custom && (
        <Input
          value={value}
          autoFocus
          onChange={(e) => onChange(e.target.value)}
          placeholder="Type a custom model id"
          className="font-mono"
        />
      )}
      <div className="flex items-center gap-2 flex-wrap">
        <p className="text-[10px] text-muted-foreground flex items-center gap-1.5">
          {windowKnown ? (
            <span className="text-emerald-400/90">{windowLabel}</span>
          ) : (
            <span className="text-muted-foreground/80">Context window unknown</span>
          )}
          {allModels.length > 0 && (
            <span className="text-muted-foreground/60">
              · {compact.curated
                ? `${compact.models.length} enabled of ${allModels.length}`
                : `${compact.models.length}${compact.truncated ? ` of ${allModels.length}` : ""} model${compact.models.length === 1 ? "" : "s"}`}
            </span>
          )}
        </p>
        {providerId && canDiscover && (
          <button
            type="button"
            onClick={() => void discoverAndManage()}
            disabled={discovering}
            className="text-[10px] text-primary/90 hover:text-primary disabled:opacity-50 flex items-center gap-1"
          >
            <RefreshCw className={discovering ? "w-3 h-3 animate-spin" : "w-3 h-3"} />
            {discovering ? "Discovering…" : "Discover models"}
          </button>
        )}
        {providerId && allModels.length > 0 && (
          <button
            type="button"
            onClick={() => setManageOpen(true)}
            className="inline-flex items-center gap-1 text-[10px] text-muted-foreground hover:text-foreground"
          >
            <Layers size={11} /> Manage{compact.curated ? ` (${compact.models.length})` : ""}
          </button>
        )}
        <button
          type="button"
          onClick={() => {
            setCustom((v) => !v);
            if (custom) onChange("");
          }}
          className="text-[10px] text-muted-foreground hover:text-foreground"
        >
          {custom ? "Choose from list" : "Custom model id…"}
        </button>
      </div>
      {note && (
        <p className={note.kind === "ok" ? "text-[10px] text-emerald-400/90" : "text-[10px] text-rose-400/90"}>
          {note.text}
        </p>
      )}
      {manageOpen && providerId && (
        <ManageModelsDialog
          providerId={providerId}
          providerLabel={providerId}
          allModels={allModels}
          selected={value}
          onDiscover={discover}
          canDiscover={Boolean(canDiscover)}
          onClose={() => setManageOpen(false)}
        />
      )}
    </div>
  );
}

