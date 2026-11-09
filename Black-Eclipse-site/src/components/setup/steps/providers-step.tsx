"use client";

import { Check, CircleSlash, Info, Wallet, WarningCircle } from "@/lib/icons";
import { cn } from "@/lib/utils";
import { CAPABILITY_BY_ID } from "@/lib/setup/capabilities";
import { commercialSentence } from "@/lib/setup/source-catalog";
import type { SetupDraft, SetupKeyStatuses, SetupState } from "../types";
import { ProviderCard } from "../parts/provider-card";
import { Toggle } from "../parts/switch";
import { CheckRow } from "../parts/check-row";

const ADVANCED_PRICE = CAPABILITY_BY_ID.prices.advanced;
const ADVANCED_CRYPTO = CAPABILITY_BY_ID.crypto.advanced;
const ADVANCED_SEARCH = CAPABILITY_BY_ID.search.advanced;

function Section({
  title,
  hint,
  children,
}: {
  title: string;
  hint: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.02] p-3">
      <p className="text-[11px] font-bold text-foreground">{title}</p>
      <p className="mt-0.5 text-[10px] leading-relaxed text-muted-foreground">{hint}</p>
      <div className="mt-2.5 space-y-2">{children}</div>
    </div>
  );
}

function AdvancedToggle({
  id,
  label,
  note,
  status,
  enabled,
  accepted,
  onToggle,
}: {
  id: string;
  label: string;
  note: string;
  status: "ok" | "attribution" | "personal-only" | "verify";
  enabled: boolean;
  accepted: boolean;
  onToggle: (next: boolean) => void;
}) {
  return (
    <div className="flex items-start gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-2.5">
      <div className="min-w-0 flex-1">
        <p className="text-[10px] font-semibold text-foreground">{label}</p>
        <p
          className={cn(
            "text-[9px] font-semibold leading-snug",
            status === "personal-only"
              ? "text-rose-300"
              : status === "verify"
                ? "text-amber-300"
                : "text-emerald-300/90",
          )}
        >
          {commercialSentence(status)}
        </p>
        <p className="text-[9px] leading-snug text-muted-foreground">{note}</p>
      </div>
      <Toggle
        checked={enabled}
        onChange={onToggle}
        label={`Enable ${label}`}
        disabled={!accepted}
      />
    </div>
  );
}

export function ProvidersStep({
  state,
  draft,
  setDraft,
  keyStatuses,
  onSaveKey,
}: {
  state: SetupState;
  draft: SetupDraft;
  setDraft: (patch: Partial<SetupDraft>) => void;
  keyStatuses: SetupKeyStatuses;
  onSaveKey: (envVar: string, value: string) => Promise<string>;
}) {
  const byId = Object.fromEntries(state.sources.map((s) => [s.id, s]));
  const isCommercial = draft.mode === "commercial";
  const advancedAccepted = (ids: string[]) => ids.every((id) => draft.accepted.includes(id));

  const toggle = (id: string, next: boolean) =>
    setDraft({ sources: { ...draft.sources, [id]: next } });

  const setPriceMode = (mode: SetupDraft["priceMode"]) => {
    const sources = { ...draft.sources };
    if (mode !== "community") {
      for (const id of ADVANCED_PRICE) sources[id] = false;
    }
    if (mode === "skip") {
      // Connected providers keep their saved key, but nothing is enabled by the
      // wizard's price mode; capability status still reflects a configured key.
      for (const id of CAPABILITY_BY_ID.prices.connected) sources[id] = false;
    }
    setDraft({ priceMode: mode, sources });
  };

  const communityAck = advancedAccepted(ADVANCED_PRICE);
  const cryptoAck = advancedAccepted(ADVANCED_CRYPTO);
  const searchAck = advancedAccepted(ADVANCED_SEARCH);

  const setGroupAccepted = (ids: string[], on: boolean) => {
    const sources = { ...draft.sources };
    if (!on) {
      for (const id of ids) sources[id] = false;
    }
    setDraft({
      accepted: on
        ? [...new Set([...draft.accepted, ...ids])]
        : draft.accepted.filter((id) => !ids.some((sourceId) => sourceId === id)),
      sources,
    });
  };

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
        <p className="flex items-center gap-1.5 text-[10px] font-bold text-foreground">
          <Info size={12} className="text-primary" /> Can you use this?
        </p>
        <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
          <span className="font-semibold text-emerald-300">Personal use:</span> you are welcome to
          connect anything here.{" "}
          <span className="font-semibold text-rose-300">Commercial company:</span> only use providers
          labelled <span className="font-semibold text-emerald-300">COMMERCIAL USE OK</span>. The
          community sources (TradingView, Yahoo, Binance, CoinGecko Demo) are{" "}
          <span className="font-semibold text-rose-300">personal use only</span>.
        </p>
      </div>

      <div className="space-y-1.5">
        {[
          {
            id: "licensed" as const,
            title: "Licensed provider",
            body: "Recommended for commercial use. Paste your own key.",
            icon: Wallet,
          },
          {
            id: "community" as const,
            title: "Community sources",
            body: "TradingView, Yahoo, Binance. Personal use only.",
            icon: Info,
          },
          {
            id: "skip" as const,
            title: "Skip for now",
            body: "Charts show UNAVAILABLE. Everything else still works.",
            icon: CircleSlash,
          },
        ]
          .filter((option) => !isCommercial || option.id !== "community")
          .map((option) => {
          const active = draft.priceMode === option.id;
          const Icon = option.icon;
          return (
            <button
              key={option.id}
              type="button"
              onClick={() => setPriceMode(option.id)}
              className={cn(
                "flex w-full items-center gap-2.5 rounded-lg border px-3 py-2 text-left transition-colors cursor-pointer",
                active
                  ? "border-primary/50 bg-primary/10"
                  : "border-white/10 bg-white/[0.02] hover:border-white/20",
              )}
            >
              <span
                className={cn(
                  "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border",
                  active ? "border-primary bg-primary" : "border-white/25",
                )}
              >
                {active && <span className="h-1.5 w-1.5 rounded-full bg-primary-foreground" />}
              </span>
              <Icon size={13} className={active ? "text-primary" : "text-muted-foreground"} />
              <span className="min-w-0 flex-1">
                <span className="block text-[11px] font-bold text-foreground">{option.title}</span>
                <span className="block text-[9px] leading-snug text-muted-foreground">{option.body}</span>
              </span>
            </button>
          );
        })}
      </div>

      {draft.priceMode === "licensed" && (
        <Section title="Live prices & charts" hint="Connect one or more. Keys are stored encrypted in JDDS.">
          {CAPABILITY_BY_ID.prices.connected.map((id) => {
            const source = byId[id];
            if (!source) return null;
            return (
              <ProviderCard
                key={id}
                source={source}
                status={keyStatuses[source.envVar ?? ""]}
                onSaveKey={onSaveKey}
                compact
              />
            );
          })}
        </Section>
      )}

      {draft.priceMode === "community" && (
        <div className="rounded-2xl border border-amber-500/20 bg-amber-500/[0.04] p-3">
          <p className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-wider text-amber-300">
            <WarningCircle size={12} /> Personal use only
          </p>
          <p className="mt-1 text-[10px] leading-relaxed text-muted-foreground">
            These sources do not grant commercial redistribution rights. Do not enable them for a
            product you charge for.
          </p>
          <div className="mt-2">
            <CheckRow
              checked={communityAck}
              onChange={(next) => {
                const sources = { ...draft.sources };
                if (next) {
                  for (const id of ADVANCED_PRICE) sources[id] = true;
                  setDraft({
                    accepted: [...new Set([...draft.accepted, ...ADVANCED_PRICE])],
                    sources,
                  });
                } else {
                  for (const id of ADVANCED_PRICE) sources[id] = false;
                  setDraft({
                    accepted: draft.accepted.filter(
                      (id) => !ADVANCED_PRICE.some((sourceId) => sourceId === id),
                    ),
                    sources,
                  });
                }
              }}
            >
              I accept each provider&apos;s terms for personal use.
            </CheckRow>
          </div>
          <div className="mt-2 grid gap-2">
            {ADVANCED_PRICE.map((id) => {
              const source = byId[id];
              if (!source) return null;
              return (
                <AdvancedToggle
                  key={id}
                  id={id}
                  label={source.label}
                  note={source.note ?? ""}
                  status={source.commercial}
                  enabled={draft.sources[id] === true}
                  accepted={communityAck}
                  onToggle={(next) => toggle(id, next)}
                />
              );
            })}
          </div>
        </div>
      )}

      {draft.priceMode === "skip" && (
        <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3 text-[10px] leading-relaxed text-muted-foreground">
          Live prices are off. Quote pages and charts will show <span className="text-foreground/80">UNAVAILABLE</span>.
          You can connect a provider later in Settings → Data &amp; Storage.
        </div>
      )}

      <Section title="Crypto (optional)" hint="Crypto prices need their own provider. Nothing is enabled by default.">
        {CAPABILITY_BY_ID.crypto.connected.map((id) => {
          const source = byId[id];
          if (!source) return null;
          return (
            <ProviderCard
              key={id}
              source={source}
              status={keyStatuses[source.envVar ?? ""]}
              onSaveKey={onSaveKey}
              compact
            />
          );
        })}
        {!isCommercial ? (
          <>
            <CheckRow
              checked={cryptoAck}
              onChange={(next) => setGroupAccepted(ADVANCED_CRYPTO, next)}
            >
              I accept the community crypto sources&apos; terms for personal use.
            </CheckRow>
            <div className="grid gap-2">
              {ADVANCED_CRYPTO.map((id) => {
                const source = byId[id];
                if (!source) return null;
                return (
                  <AdvancedToggle
                    key={id}
                    id={id}
                    label={source.label}
                    note={source.note ?? ""}
                    status={source.commercial}
                    enabled={draft.sources[id] === true}
                    accepted={cryptoAck}
                    onToggle={(next) => toggle(id, next)}
                  />
                );
              })}
            </div>
            {!cryptoAck && (
              <p className="text-[9px] text-muted-foreground">
                Community crypto sources stay locked until you accept their terms.
              </p>
            )}
          </>
        ) : (
          <p className="text-[9px] text-muted-foreground">
            Community crypto sources are hidden in Commercial mode. Connect CoinMarketCap or
            CoinGecko above.
          </p>
        )}
      </Section>

      <Section title="Research search (optional)" hint="A search API gives research and the agent a dependable web source.">
        {CAPABILITY_BY_ID.search.connected.map((id) => {
          const source = byId[id];
          if (!source) return null;
          return (
            <ProviderCard
              key={id}
              source={source}
              status={keyStatuses[source.envVar ?? ""]}
              onSaveKey={onSaveKey}
              compact
            />
          );
        })}
        {!isCommercial ? (
          <>
            <CheckRow
              checked={searchAck}
              onChange={(next) => setGroupAccepted(ADVANCED_SEARCH, next)}
            >
              I accept the keyless community search source&apos;s terms for personal use.
            </CheckRow>
            <div className="grid gap-2">
              {ADVANCED_SEARCH.map((id) => {
                const source = byId[id];
                if (!source) return null;
                return (
                  <AdvancedToggle
                    key={id}
                    id={id}
                    label={source.label}
                    note={source.note ?? ""}
                    status={source.commercial}
                    enabled={draft.sources[id] === true}
                    accepted={searchAck}
                    onToggle={(next) => toggle(id, next)}
                  />
                );
              })}
            </div>
          </>
        ) : (
          <p className="text-[9px] text-muted-foreground">
            The keyless community search source is hidden in Commercial mode. Connect Tavily,
            Brave, Exa or Serper above.
          </p>
        )}
      </Section>

      <Section title="More macro & company" hint="Optional add-ons for global macro, fundamentals and news.">
        {["tradingeconomics", "fmp", "finnhub"].map((id) => {
          const source = byId[id];
          if (!source) return null;
          return (
            <ProviderCard
              key={id}
              source={source}
              status={keyStatuses[source.envVar ?? ""]}
              onSaveKey={onSaveKey}
              compact
            />
          );
        })}
      </Section>

      <p className="flex items-center gap-1.5 text-[9px] text-muted-foreground">
        <Check size={10} /> Anything you skip stays off; its screens show an honest UNAVAILABLE state.
      </p>
    </div>
  );
}
