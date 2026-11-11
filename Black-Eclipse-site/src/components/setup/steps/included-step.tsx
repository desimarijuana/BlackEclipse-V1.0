"use client";

import { Info, ShieldCheck, WarningCircle } from "@/lib/icons";
import { cn } from "@/lib/utils";
import type { SetupDraft, SetupState } from "../types";
import { LicenseBadge } from "../parts/license-badge";
import { Toggle } from "../parts/switch";

export function IncludedStep({
  state,
  draft,
  setDraft,
}: {
  state: SetupState;
  draft: SetupDraft;
  setDraft: (patch: Partial<SetupDraft>) => void;
}) {
  const includedSources = state.sources.filter((s) => s.tier === "included");
  const includedOn = includedSources.filter((s) => draft.sources[s.id] === true).length;

  const toggle = (id: string, next: boolean) =>
    setDraft({ sources: { ...draft.sources, [id]: next } });

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap gap-2">
        {state.bundles.map((bundle) => (
          <button
            key={bundle.id}
            type="button"
            onClick={() => setDraft({ bundleId: bundle.id })}
            className={cn(
              "rounded-lg border px-2.5 py-1.5 text-[11.5px] cursor-pointer",
              draft.bundleId === bundle.id
                ? "border-primary/50 bg-primary/10 text-foreground"
                : "border-white/10 text-muted-foreground hover:border-white/20",
            )}
          >
            {bundle.label}
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3.5">
        <p className="flex items-center gap-2 text-[12px] font-semibold text-foreground">
          <ShieldCheck size={14} className="text-primary" /> Which ones can you use?
        </p>
        <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted-foreground">
          <span className="font-semibold text-emerald-300">Personal use:</span> you are welcome to
          enable anything below.{" "}
          <span className="font-semibold text-rose-300">Commercial company:</span> only use sources
          marked <span className="font-semibold text-emerald-300">COMMERCIAL USE OK</span> or{" "}
          <span className="font-semibold text-amber-300">COMMERCIAL + ATTRIBUTION</span>. Never use a{" "}
          <span className="font-semibold text-rose-300">PERSONAL USE ONLY</span> source in a product
          you charge for.
        </p>
      </div>

      <div className="grid gap-2.5 sm:grid-cols-2">
        {includedSources.map((source) => (
          <div
            key={source.id}
            className="flex items-start gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-3"
          >
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className="text-[12.5px] font-semibold text-foreground"
                  title={`${source.note ?? ""}${source.attribution ? ` Attribution: ${source.attribution}.` : ""}`}
                >
                  {source.label}
                </span>
                <LicenseBadge status={source.commercial} />
              </div>
              <p className="mt-1 text-[11px] leading-snug text-muted-foreground/70">
                {source.attribution ? source.attribution : source.short}
              </p>
            </div>
            <Toggle
              checked={draft.sources[source.id] === true}
              onChange={(next) => toggle(source.id, next)}
              label={`Enable ${source.label}`}
            />
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-white/10 bg-white/[0.02] p-3.5">
        <p className="flex items-center gap-2 text-[11.5px] font-semibold uppercase tracking-wider text-muted-foreground">
          <Info size={13} /> {includedOn} included source{includedOn === 1 ? "" : "s"} enabled
        </p>
        <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted-foreground">
          Included data powers company research, macro, world events and headlines. Live prices,
          crypto and research search are connected on the next step.
        </p>
      </div>

      <div className="rounded-xl border border-amber-500/20 bg-amber-500/[0.04] p-3.5">
        <p className="flex items-center gap-2 text-[11.5px] font-semibold uppercase tracking-wider text-amber-300">
          <WarningCircle size={13} /> Community sources are on the next step
        </p>
        <p className="mt-1.5 text-[11.5px] leading-relaxed text-muted-foreground">
          TradingView, Yahoo, Binance, CoinGecko Demo and scraper sources are for personal use and
          are not part of Eclipse&apos;s included data. They stay off unless you accept their terms
          on the Providers step.
        </p>
        <p className="mt-2 flex items-center gap-1.5 text-[11px] text-muted-foreground">
          <ShieldCheck size={11} /> Commercial mode never enables these automatically.
        </p>
      </div>
    </div>
  );
}
