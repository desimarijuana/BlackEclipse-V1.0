"use client";

import { Check, ShieldCheck, Sparkles } from "@/lib/icons";
import { cn } from "@/lib/utils";
import type { SetupBundleRow, SetupDraft, SetupState } from "../types";
import { bundleHighlights } from "@/lib/setup/bundles";

export function WelcomeStep({
  state,
  draft,
  setDraft,
}: {
  state: SetupState;
  draft: SetupDraft;
  setDraft: (patch: Partial<SetupDraft>) => void;
}) {
  const modes = [
    {
      id: "personal" as const,
      title: "Personal / research",
      body: "For your own analysis. You can enable free community sources, with their terms shown.",
    },
    {
      id: "commercial" as const,
      title: "Commercial / product",
      body: "For work you charge for. We only enable open-licensed data and ask you to connect your own licensed providers.",
    },
  ];

  return (
    <div className="space-y-5">
      <div className="grid gap-2.5">
        {modes.map((mode) => {
          const active = draft.mode === mode.id;
          return (
            <button
              key={mode.id}
              type="button"
              onClick={() => setDraft({ mode: mode.id })}
              className={cn(
                "flex flex-col items-start gap-1.5 rounded-2xl border p-3.5 text-left transition-all cursor-pointer",
                active
                  ? "border-primary/50 bg-primary/10"
                  : "border-white/10 bg-white/[0.02] hover:border-primary/40 hover:bg-white/[0.04]",
              )}
            >
              <span className={cn("flex h-8 w-8 items-center justify-center rounded-xl border", active ? "border-primary/40 bg-primary/15 text-primary" : "border-white/10 bg-white/[0.04] text-muted-foreground")}>
                {mode.id === "commercial" ? <ShieldCheck size={15} /> : <Sparkles size={15} />}
              </span>
              <span className="text-[12px] font-bold text-foreground">{mode.title}</span>
              <span className="text-[10px] leading-snug text-muted-foreground">{mode.body}</span>
            </button>
          );
        })}
      </div>

      <div>
        <p className="text-[9px] font-bold uppercase tracking-wider text-muted-foreground">Start from a bundle</p>
        <div className="mt-2 flex flex-wrap gap-2">
          {state.bundles.map((bundle: SetupBundleRow) => {
            const active = draft.bundleId === bundle.id;
            return (
              <button
                key={bundle.id}
                type="button"
                onClick={() => setDraft({ bundleId: bundle.id })}
                className={cn(
                  "rounded-xl border px-2.5 py-1.5 text-left transition-colors cursor-pointer",
                  active ? "border-primary/50 bg-primary/10" : "border-white/10 bg-white/[0.02] hover:border-white/20",
                )}
              >
                <span className="flex items-center gap-1.5 text-[10px] font-bold text-foreground">
                  {active && <Check size={10} className="text-primary" />}
                  {bundle.label}
                </span>
                <span className="mt-0.5 block max-w-[190px] text-[9px] leading-snug text-muted-foreground">
                  {bundle.description}
                </span>
              </button>
            );
          })}
        </div>
        <ul className="mt-2 flex flex-wrap gap-x-3 gap-y-1">
          {bundleHighlights(draft.bundleId).map((item) => (
            <li key={item} className="flex items-center gap-1 text-[9px] text-muted-foreground">
              <Check size={9} className="text-emerald-400" /> {item}
            </li>
          ))}
        </ul>
      </div>

      <p className="rounded-xl border border-white/10 bg-white/[0.02] p-2.5 text-[9px] leading-relaxed text-muted-foreground">
        Data-source labels are an informational snapshot, not legal advice. Verify each provider&apos;s
        current terms before a paid launch.
      </p>
    </div>
  );
}
