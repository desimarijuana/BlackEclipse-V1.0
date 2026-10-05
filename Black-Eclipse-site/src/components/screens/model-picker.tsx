"use client";

// ── Model picker ─────────────────────────────────────────────────────────────
// The runtime's declared models as a real dropdown, PLUS a free-text field so a
// custom id is always typeable (never an allowlist). For a provider the runtime
// can only enumerate at RUNTIME (Ollama, LM Studio, a router), a "Discover" action
// probes the live endpoint and merges the models it actually serves — so the
// operator sees their installed models, not a static sample.

import { useEffect, useMemo, useState } from "react";
import { RefreshCw } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { discoverRuntimeModels } from "@/lib/harness/model-runtime-browser";

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

const CUSTOM = "__custom__";

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
  const [extra, setExtra] = useState<string[]>([]);
  const [discovering, setDiscovering] = useState(false);
  const [note, setNote] = useState<{ kind: "ok" | "error"; text: string } | null>(null);

  // A discovered set belongs to one provider/endpoint; drop it when either
  // changes so a stale list never masquerades as this provider's models.
  useEffect(() => {
    setExtra([]);
    setNote(null);
  }, [providerId, baseUrl]);

  const merged = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const m of [...options, ...extra]) {
      if (m && !seen.has(m)) {
        seen.add(m);
        out.push(m);
      }
    }
    return out;
  }, [options, extra]);

  const discover = async () => {
    if (!providerId || discovering) return;
    setDiscovering(true);
    setNote(null);
    try {
      const res = await discoverRuntimeModels(providerId, { baseUrl, apiKey, model: value });
      if (!res.ok) {
        setNote({ kind: "error", text: res.detail || "Discovery failed" });
        return;
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
    } catch (err) {
      setNote({ kind: "error", text: err instanceof Error ? err.message : "Discovery failed" });
    } finally {
      setDiscovering(false);
    }
  };

  return (
    <div className="space-y-2">
      {merged.length > 0 ? (
        <Select
          value={merged.includes(value) ? value : CUSTOM}
          onValueChange={(v) => {
            if (v && v !== CUSTOM) onChange(v);
            else onChange("");
          }}
        >
          <SelectTrigger className="w-full font-mono">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {merged.map((m) => (
              <SelectItem key={m} value={m}>
                {m}
              </SelectItem>
            ))}
            <SelectItem value={CUSTOM}>Custom model id…</SelectItem>
          </SelectContent>
        </Select>
      ) : null}
      <Input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder="Or type a custom model id"
        className="font-mono"
      />
      <div className="flex items-center gap-2 flex-wrap">
        <p className="text-[10px] text-muted-foreground flex items-center gap-1.5">
          {windowKnown ? (
            <span className="text-emerald-400/90">{windowLabel}</span>
          ) : (
            <span className="text-muted-foreground/80">Context window unknown</span>
          )}
          {merged.length > 0 && (
            <span className="text-muted-foreground/60">
              · {merged.length} model{merged.length === 1 ? "" : "s"}
            </span>
          )}
        </p>
        {canDiscover && providerId && (
          <button
            type="button"
            onClick={discover}
            disabled={discovering}
            className="text-[10px] text-primary/90 hover:text-primary disabled:opacity-50 flex items-center gap-1"
          >
            <RefreshCw className={discovering ? "w-3 h-3 animate-spin" : "w-3 h-3"} />
            {discovering ? "Discovering…" : "Discover installed models"}
          </button>
        )}
      </div>
      {note && (
        <p className={note.kind === "ok" ? "text-[10px] text-emerald-400/90" : "text-[10px] text-rose-400/90"}>
          {note.text}
        </p>
      )}
    </div>
  );
}
