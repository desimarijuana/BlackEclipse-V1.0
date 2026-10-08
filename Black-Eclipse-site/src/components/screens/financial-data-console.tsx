"use client";

// ── Financial Data Console ───────────────────────────────────────────────────
// The operator surface for the Financial Data Gateway. One card per provider,
// rendered INSIDE the existing "Data & providers" (data) settings section — no
// new design system, no new store.
//
// It reads the gateway's provider registry through the front door
// (`GET /api/harness/financial/providers`), which merges credential PRESENCE from
// the vault. Honesty rules, unchanged from the rest of Settings:
//   * a provider only reads "connected" when its credential is really resolvable,
//   * a "declared" provider has NO runnable adapter yet — the dependency is named,
//     never faked,
//   * an API secret is never rendered back; only a presence flag crosses.
//
// This panel is read-only: it DESCRIBES routing, authority, rate limits and
// licensing. It does not edit keys — those live in the provider sections that own
// them (Market / Investor Eye), so a key has exactly one home.

import { useCallback, useEffect, useState } from "react";
import {
  AlertCircle,
  Check,
  Loader2,
  Plug,
  RefreshCcw,
  ShieldCheck,
  Unplug,
} from "@/lib/icons";
import { cn } from "@/lib/utils";
import { Panel } from "./settings-ui";
import { MarketDataConsole } from "./market-data-console";

type ProviderState = "connected" | "declared" | "keyless";

interface ProviderRow {
  id: string;
  label: string;
  tier: string;
  capabilities: string[];
  datasets?: string[];
  credentialRef?: string | null;
  configured?: boolean | null;
  implemented: boolean;
  sourceName?: string | null;
  notes?: string | null;
  rateLimit?: {
    requestsPerMinute?: number | null;
    requestsPerDay?: number | null;
    concurrency?: number;
    costTier?: string;
  };
  usage?: {
    license?: string;
    attribution?: string | null;
    redistribution?: string;
    storage?: string;
    notes?: string | null;
  };
}

interface RegistryPayload {
  status?: string;
  providerCount?: number;
  implementedCount?: number;
  capabilities?: string[];
  providers?: ProviderRow[];
  error?: string;
}

const TIER_STYLE: Record<string, string> = {
  primary: "text-emerald-400/90 border-emerald-400/30 bg-emerald-400/10",
  structured: "text-sky-400/90 border-sky-400/30 bg-sky-400/10",
  secondary: "text-amber-400/90 border-amber-400/30 bg-amber-400/10",
};

function stateOf(p: ProviderRow): ProviderState {
  if (!p.implemented) return "declared";
  if (p.credentialRef) return p.configured ? "connected" : "keyless";
  return "connected";
}

function StateBadge({ p }: { p: ProviderRow }) {
  const state = stateOf(p);
  if (state === "declared") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-muted-foreground">
        <AlertCircle className="h-3 w-3" /> declared
      </span>
    );
  }
  if (state === "keyless") {
    return (
      <span className="inline-flex items-center gap-1 rounded-full border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 text-[10px] text-amber-400/90">
        <Unplug className="h-3 w-3" /> key missing
      </span>
    );
  }
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-emerald-400/30 bg-emerald-400/10 px-2 py-0.5 text-[10px] text-emerald-400/90">
      <Check className="h-3 w-3" /> connected
    </span>
  );
}

export function FinancialDataConsole() {
  const [payload, setPayload] = useState<RegistryPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/harness/financial/providers", { cache: "no-store" });
      const json = (await res.json()) as RegistryPayload;
      if (!res.ok) {
        setError(json.error ?? `request failed (${res.status})`);
        setPayload(null);
      } else {
        setPayload(json);
      }
    } catch {
      setError("Could not reach the gateway registry.");
      setPayload(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const providers = payload?.providers ?? [];
  const implemented = providers.filter((p) => p.implemented);
  const declared = providers.filter((p) => !p.implemented);

  return (
    <>
    <Panel className="p-5 md:p-6" data-anchor="financial-gateway">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-sm font-medium">
            <ShieldCheck className="h-4 w-4 text-muted-foreground" />
            Financial Data Gateway
          </h3>
          <p className="mt-1 max-w-2xl text-[10px] leading-relaxed text-muted-foreground">
            Agents request an objective; the gateway selects, normalizes, validates and
            reconciles across providers. Credentials are shown only as presence — never a value.
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="inline-flex items-center gap-1 rounded-lg border border-white/10 px-2 py-1 text-[10px] text-muted-foreground hover:bg-white/5 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCcw className="h-3 w-3" />}
          Refresh
        </button>
      </div>

      {error && (
        <div className="mt-3 flex items-center gap-2 rounded-lg border border-amber-400/20 bg-amber-400/5 px-3 py-2 text-[10px] text-amber-400/90">
          <AlertCircle className="h-3 w-3" /> {error}
        </div>
      )}

      {!error && loading && providers.length === 0 && (
        <div className="mt-4 flex items-center gap-2 text-[10px] text-muted-foreground">
          <Loader2 className="h-3 w-3 animate-spin" /> Loading provider registry…
        </div>
      )}

      {providers.length > 0 && (
        <>
          <div className="mt-4 grid grid-cols-3 gap-2">
            <Stat label="Providers" value={String(payload?.providerCount ?? providers.length)} />
            <Stat label="Implemented" value={String(payload?.implementedCount ?? implemented.length)} />
            <Stat label="Capabilities" value={String(payload?.capabilities?.length ?? 0)} />
          </div>

          <div className="mt-4 space-y-2">
            {implemented.map((p) => (
              <ProviderCard key={p.id} p={p} />
            ))}
          </div>

          {declared.length > 0 && (
            <div className="mt-5">
              <p className="flex items-center gap-1.5 text-[10px] font-medium uppercase tracking-wide text-muted-foreground">
                <Plug className="h-3 w-3" /> Credential-ready (no adapter yet)
              </p>
              <div className="mt-2 space-y-2">
                {declared.map((p) => (
                  <ProviderCard key={p.id} p={p} />
                ))}
              </div>
            </div>
          )}

          <p className="mt-4 text-[10px] leading-relaxed text-muted-foreground/70">
            A provider marked declared has no runnable adapter: its dependency is named, not
            faked. Attribution, redistribution and storage terms are recorded per provider —
            review them before redistributing any data.
          </p>
        </>
      )}
    </Panel>
    <MarketDataConsole />
    </>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl border border-white/10 glass-card-subtle px-3 py-2">
      <p className="text-[9px] uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-0.5 text-sm font-medium tabular-nums">{value}</p>
    </div>
  );
}

function ProviderCard({ p }: { p: ProviderRow }) {
  const [open, setOpen] = useState(false);
  const rate = p.rateLimit;
  return (
    <div className="rounded-xl border border-white/10 glass-card-subtle">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-3 px-3 py-2.5 text-left"
      >
        <span
          className={cn(
            "rounded-md border px-1.5 py-0.5 text-[9px] uppercase tracking-wide",
            TIER_STYLE[p.tier] ?? "text-muted-foreground border-white/10",
          )}
        >
          {p.tier}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-xs font-medium">{p.label}</span>
          <span className="block truncate text-[10px] text-muted-foreground">
            {p.capabilities.slice(0, 6).join(" · ")}
            {p.capabilities.length > 6 ? ` +${p.capabilities.length - 6}` : ""}
          </span>
        </span>
        <StateBadge p={p} />
      </button>

      {open && (
        <div className="border-t border-white/5 px-3 py-2.5 text-[10px] leading-relaxed text-muted-foreground">
          <Row label="Capabilities" value={p.capabilities.join(", ")} />
          {p.datasets?.length ? <Row label="Datasets" value={p.datasets.join(", ")} /> : null}
          {p.credentialRef ? (
            <Row label="Credential" value={p.credentialRef + (p.configured ? " (configured)" : " (missing)")} />
          ) : (
            <Row label="Credential" value="not required (keyless)" />
          )}
          <Row
            label="Rate limit"
            value={
              [
                rate?.requestsPerMinute ? `${rate.requestsPerMinute}/min` : null,
                rate?.requestsPerDay ? `${rate.requestsPerDay}/day` : null,
                rate?.concurrency ? `concurrency ${rate.concurrency}` : null,
                rate?.costTier ? `cost: ${rate.costTier}` : null,
              ]
                .filter(Boolean)
                .join(" · ") || "unspecified"
            }
          />
          {p.usage ? (
            <Row
              label="Usage terms"
              value={[
                p.usage.license,
                p.usage.attribution ? `attribution: ${p.usage.attribution}` : null,
                p.usage.redistribution !== "unspecified" ? `redistribution: ${p.usage.redistribution}` : null,
                p.usage.storage !== "unspecified" ? `storage: ${p.usage.storage}` : null,
              ]
                .filter(Boolean)
                .join(" · ")}
            />
          ) : null}
          {p.notes ? <p className="mt-1.5 text-muted-foreground/80">{p.notes}</p> : null}
        </div>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-2">
      <span className="w-24 shrink-0 text-muted-foreground/60">{label}</span>
      <span className="min-w-0 flex-1 break-words">{value}</span>
    </div>
  );
}

export default FinancialDataConsole;
