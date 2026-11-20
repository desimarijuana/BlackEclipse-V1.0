"use client";

// ── Model picker ─────────────────────────────────────────────────────────────
// The runtime's declared models as a real dropdown, PLUS a free-text field so a
// custom id is always typeable (never an allowlist). The picker AUTO-detects the
// live list on mount and whenever the endpoint or key changes (debounced), so a
// provider's real catalog — Ollama's installed models, a router's hundreds, a
// hand-typed API's models — appears without clicking anything. "Discover models"
// remains the explicit re-probe and opens the curate dialog.

import { useEffect, useMemo, useRef, useState } from "react";
import { Layers, RefreshCw } from "@/lib/icons";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { discoverRuntimeModels } from "@/lib/harness/clients/model-runtime-browser";
import { sortModelsNewestFirst } from "@/lib/agent/model-recency";
import {
  compactModels,
  useEnabledModelsStore,
  useHydrateEnabledModels,
} from "@/lib/agent/enabled-models";
import { ManageModelsDialog } from "./manage-models-dialog";

/**
 * How long to wait after the provider/endpoint changes before probing, so
 * typing a base URL does not fire one request per keystroke.
 */
const AUTO_DISCOVER_DEBOUNCE_MS = 600;

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
  /** Called with the full, merged option list after a successful discovery. */
  onDiscovered?: (models: string[]) => void;
  /**
   * Changes when the provider's key/connection state changes (e.g. a key was
   * just saved). Included in the probe key so the picker re-detects models
   * without a manual click.
   */
  discoverSignal?: string | number;
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
  onDiscovered,
  discoverSignal,
}: Props) {
  useHydrateEnabledModels();
  const [extra, setExtra] = useState<string[]>([]);
  const [discovering, setDiscovering] = useState(false);
  const [note, setNote] = useState<{ kind: "ok" | "warn" | "error"; text: string } | null>(null);
  const [manageOpen, setManageOpen] = useState(false);

  // A discovered set belongs to one provider/endpoint; drop it when either
  // changes so a stale list never masquerades as this provider's models.
  useEffect(() => {
    setExtra([]);
    setNote(null);
  }, [providerId, baseUrl]);

  const enabled = useEnabledModelsStore((s) => (providerId ? s.providers[providerId] : undefined));

  // The FULL list (declared + discovered), NEWEST FIRST — what the Manage
  // dialog curates. Discovered ids lead, so a fresh probe never hides behind a
  // stale declared sample.
  const allModels = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const m of [...extra, ...options]) {
      if (m && !seen.has(m)) {
        seen.add(m);
        out.push(m);
      }
    }
    const sorted = sortModelsNewestFirst(out);
    if (value && !seen.has(value)) sorted.unshift(value);
    return sorted;
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

  const discover = async (silent = false): Promise<boolean> => {
    if (!providerId || discovering) return false;
    setDiscovering(true);
    if (!silent) setNote(null);
    try {
      const res = await discoverRuntimeModels(providerId, { baseUrl, apiKey, model: value });
      if (!res.ok) {
        if (!silent) setNote({ kind: "error", text: res.detail || "Discovery failed" });
        return false;
      }
      const ids = sortModelsNewestFirst(res.models.map((m) => m.id).filter(Boolean));
      setExtra(ids);
      const count = ids.length;
      const missing = Boolean(value) && count > 0 && !ids.includes(value);
      if (!value && count > 0) {
        // Nothing configured yet — adopting the newest served model is free.
        onChange(ids[0]);
        setNote({ kind: "ok", text: `Found ${count} model${count === 1 ? "" : "s"}` });
      } else if (missing && !silent) {
        // An explicit Discover: the saved model is not served here, so it would
        // fail with a 404 anyway. Switch and say so.
        onChange(ids[0]);
        setNote({
          kind: "ok",
          text: `Found ${count} model${count === 1 ? "" : "s"} · "${value}" is not served here — switched to ${ids[0]}`,
        });
      } else if (missing) {
        // The background probe only informs: never rewrite the saved model
        // behind the operator's back.
        setNote({
          kind: "warn",
          text: `"${value}" is not in the ${count} models this provider serves — pick one from the list`,
        });
      } else if (count > 0) {
        setNote({ kind: "ok", text: `Found ${count} model${count === 1 ? "" : "s"}` });
      } else if (!silent) {
        setNote({ kind: "ok", text: "The provider listed no models" });
      }
      onDiscovered?.(ids);
      return true;
    } catch (err) {
      if (!silent) {
        setNote({ kind: "error", text: err instanceof Error ? err.message : "Discovery failed" });
      }
      return false;
    } finally {
      setDiscovering(false);
    }
  };

  // Silently detect the live list on mount and whenever the operator points the
  // picker at a different server or connects a key. One probe per
  // (provider, endpoint, key-state) — the result is held durably server-side, so
  // a failed probe costs a single request rather than locking the provider out.
  const probedKey = useRef<string | null>(null);
  useEffect(() => {
    if (!providerId) return;
    // A half-typed base URL is not an endpoint yet; the declared catalog renders.
    if (baseUrl && !/^https?:\/\//i.test(baseUrl)) return;
    const key = `${providerId}|${baseUrl}|${discoverSignal ?? ""}`;
    if (probedKey.current === key) return;
    const timer = setTimeout(() => {
      probedKey.current = key;
      void discover(true);
    }, AUTO_DISCOVER_DEBOUNCE_MS);
    return () => clearTimeout(timer);
    // `discover` closes over the current provider/base URL; re-running on every
    // render would loop on its `discovering` flag.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [providerId, baseUrl, discoverSignal]);

  // A single "Discover" action that always curates: it probes, then opens the
  // Manage dialog so the operator picks what to surface (never a wall of ids).
  const discoverAndManage = async () => {
    if (!providerId) return;
    await discover();
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
          {allModels.length > 0 ? (
            <span className="text-muted-foreground/60">
              · {compact.curated
                ? `${compact.models.length} enabled of ${allModels.length}`
                : `${compact.models.length}${compact.truncated ? ` of ${allModels.length}` : ""} model${compact.models.length === 1 ? "" : "s"}`}
            </span>
          ) : providerId ? (
            <span className="text-muted-foreground/60">· no models loaded yet — use Discover models</span>
          ) : null}
        </p>
        {providerId && (
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
        <p
          className={
            note.kind === "ok"
              ? "text-[10px] text-emerald-400/90"
              : note.kind === "warn"
                ? "text-[10px] text-amber-400/90"
                : "text-[10px] text-rose-400/90"
          }
        >
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
          canDiscover
          onClose={() => setManageOpen(false)}
        />
      )}
    </div>
  );
}

