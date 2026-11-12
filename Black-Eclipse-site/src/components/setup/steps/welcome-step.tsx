"use client";

import { Briefcase, Check, User } from "@/lib/icons";
import { cn } from "@/lib/utils";
import type { SetupBundleRow, SetupDraft, SetupState } from "../types";
import { bundleHighlights } from "@/lib/setup/bundles";
import { RISK_ACK_LABEL, RESPONSIBILITY_SHORT, RISK_DISCLOSURE_FULL } from "@/lib/legal/disclosure";

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
      body: "For your own analysis. Free community sources can be enabled on request.",
      icon: User,
    },
    {
      id: "commercial" as const,
      title: "Commercial / product",
      body: "For work you charge for. Only open-licensed data and your own licensed providers.",
      icon: Briefcase,
    },
  ];

  return (
    <div className="space-y-6">
      <section>
        <p className="text-[12px] font-semibold text-foreground">How will you use Eclipse?</p>
        <div className="mt-2.5 grid gap-2.5 sm:grid-cols-2">
          {modes.map((mode) => {
            const active = draft.mode === mode.id;
            const Icon = mode.icon;
            return (
              <button
                key={mode.id}
                type="button"
                aria-pressed={active}
                onClick={() => setDraft({ mode: mode.id })}
                className={cn(
                  "flex flex-col gap-2 rounded-xl border p-3.5 text-left transition-colors cursor-pointer",
                  active
                    ? "border-primary/50 bg-primary/[0.08]"
                    : "border-white/10 bg-white/[0.02] hover:border-white/20 hover:bg-white/[0.04]",
                )}
              >
                <span className="flex items-center gap-2">
                  <span
                    className={cn(
                      "flex h-8 w-8 items-center justify-center rounded-lg border",
                      active
                        ? "border-primary/40 bg-primary/15 text-primary"
                        : "border-white/10 bg-white/[0.04] text-muted-foreground",
                    )}
                  >
                    <Icon size={15} />
                  </span>
                  <span className="text-[13px] font-semibold text-foreground">{mode.title}</span>
                  <span
                    className={cn(
                      "ml-auto flex h-4 w-4 items-center justify-center rounded-full border",
                      active ? "border-primary bg-primary" : "border-white/25",
                    )}
                    style={active ? { color: "var(--primary-foreground)" } : undefined}
                  >
                    {active && <Check size={10} weight="bold" />}
                  </span>
                </span>
                <span className="text-[11.5px] leading-relaxed text-muted-foreground">
                  {mode.body}
                </span>
              </button>
            );
          })}
        </div>
      </section>

      <section>
        <p className="text-[12px] font-semibold text-foreground">Start from a bundle</p>
        <p className="mt-0.5 text-[11.5px] text-muted-foreground">
          A starting point for your data sources. You can fine-tune it on the next steps.
        </p>
        <div className="mt-2.5 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          {state.bundles.map((bundle: SetupBundleRow) => {
            const active = draft.bundleId === bundle.id;
            return (
              <button
                key={bundle.id}
                type="button"
                aria-pressed={active}
                onClick={() => setDraft({ bundleId: bundle.id })}
                className={cn(
                  "rounded-lg border px-3 py-2.5 text-left transition-colors cursor-pointer",
                  active
                    ? "border-primary/50 bg-primary/[0.08]"
                    : "border-white/10 bg-white/[0.02] hover:border-white/20",
                )}
              >
                <span className="flex items-center gap-1.5 text-[12px] font-semibold text-foreground">
                  {active && <Check size={11} className="text-primary" weight="bold" />}
                  {bundle.label}
                </span>
                <span className="mt-0.5 block text-[11px] leading-snug text-muted-foreground">
                  {bundle.description}
                </span>
              </button>
            );
          })}
        </div>
        <ul className="mt-3 flex flex-wrap gap-x-4 gap-y-1.5">
          {bundleHighlights(draft.bundleId).map((item) => (
            <li
              key={item}
              className="flex items-center gap-1.5 text-[11px] text-muted-foreground"
            >
              <Check size={10} className="text-emerald-400" /> {item}
            </li>
          ))}
        </ul>
      </section>

      <section className="rounded-xl border border-amber-500/25 bg-amber-500/[0.05] p-3.5">
        <label className="flex cursor-pointer items-start gap-2.5">
          <input
            type="checkbox"
            className="mt-0.5 h-4 w-4 shrink-0 accent-primary"
            checked={draft.riskAck}
            onChange={(event) => setDraft({ riskAck: event.target.checked })}
          />
          <span className="min-w-0">
            <span className="block text-[12px] font-semibold text-foreground">
              Before you start
            </span>
            <span className="mt-0.5 block text-[11.5px] font-medium text-foreground">
              {RESPONSIBILITY_SHORT}
            </span>
            <span className="mt-0.5 block text-[11.5px] leading-relaxed text-muted-foreground">
              {RISK_ACK_LABEL}
            </span>
          </span>
        </label>
        <details className="ml-[26px] mt-2">
          <summary className="cursor-pointer text-[11px] text-muted-foreground/70 underline decoration-dotted underline-offset-2 hover:text-foreground">
            Read the full notice
          </summary>
          <p className="mt-1.5 text-[11px] leading-relaxed text-muted-foreground/70">
            {RISK_DISCLOSURE_FULL}
          </p>
        </details>
      </section>

      <p className="rounded-xl border border-white/10 bg-white/[0.02] p-3 text-[11px] leading-relaxed text-muted-foreground">
        Data-source labels are an informational snapshot, not legal advice. Verify each
        provider&apos;s current terms before a paid launch.
      </p>
    </div>
  );
}
