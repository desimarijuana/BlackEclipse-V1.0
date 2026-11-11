"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Brain,
  Check,
  Database,
  ListChecks,
  Loader2,
  Rocket,
  SlidersHorizontal,
} from "@/lib/icons";
import { cn } from "@/lib/utils";
import { safeSourceDefaults } from "@/lib/setup/defaults";
import { bundleSources } from "@/lib/setup/bundles";
import { getLLMPreset } from "@/lib/agent/presets";
import { seedStarterDashboard } from "@/lib/dashboard/use-dashboards";
import { RISK_DISCLOSURE_VERSION } from "@/lib/legal/disclosure";
import type { SetupDraft, SetupKeyStatuses, SetupState } from "./types";
import { draftAiChoice } from "./types";
import { WelcomeStep } from "./steps/welcome-step";
import { AiStep } from "./steps/ai-step";
import { IncludedStep } from "./steps/included-step";
import { ProvidersStep } from "./steps/providers-step";
import { ReviewStep, type CheckItemView } from "./steps/review-step";

const STEPS = [
  {
    id: "welcome",
    title: "Welcome",
    short: "How you'll use Eclipse",
    description: "Pick a starting point. Everything here can be changed later.",
    icon: Rocket,
  },
  {
    id: "ai",
    title: "AI & Chat",
    short: "Power your assistant",
    description: "Connect a model so chat works, or add one later.",
    icon: Brain,
  },
  {
    id: "included",
    title: "Included data",
    short: "Open sources on us",
    description: "Free, open data that ships with Eclipse. No account needed.",
    icon: Database,
  },
  {
    id: "providers",
    title: "Providers",
    short: "Live prices & search",
    description: "Optional providers for quotes, crypto and web search.",
    icon: SlidersHorizontal,
  },
  {
    id: "review",
    title: "Review",
    short: "Check and finish",
    description: "Confirm what will work before you start using Eclipse.",
    icon: ListChecks,
  },
] as const;

const PRICE_ADVANCED = ["tradingview", "yfinance", "http", "browser", "scrapling"];
const PRICE_CONNECTED = ["polygon", "twelvedata", "alphavantage", "marketstack", "finnhub"];

const BUNDLE_TEMPLATE: Record<string, string> = {
  research: "research",
  "personal-trader": "trader-pro",
  commercial: "desk",
  crypto: "chain-desk",
  custom: "research",
};

function initialDraft(state: SetupState): SetupDraft {
  return {
    step: 0,
    mode: state.mode,
    bundleId: state.mode === "commercial" ? "commercial" : "research",
    sources: Object.fromEntries(state.sources.map((s) => [s.id, s.enabled])),
    accepted: state.acceptedRestrictedSources ?? [],
    priceMode:
      state.mode === "commercial"
        ? PRICE_CONNECTED.some(
              (id) => state.sources.find((source) => source.id === id)?.keyConfigured === true,
            )
          ? "licensed"
          : "skip"
        : PRICE_ADVANCED.some(
              (id) => state.sources.find((source) => source.id === id)?.enabled === true,
            )
          ? "community"
          : PRICE_CONNECTED.some(
                (id) => state.sources.find((source) => source.id === id)?.keyConfigured === true,
              )
            ? "licensed"
            : "skip",
    aiKind: state.ai.configured ? "keep" : "skip",
    aiPreset: "openai",
    aiBaseUrl: "",
    aiModel: "",
    aiApiKey: "",
    extraKeys: {},
    riskAck: state.riskAck?.accepted ?? false,
  };
}

export function OnboardingShell({
  state,
  onDone,
}: {
  state: SetupState;
  onDone: () => void;
}) {
  const [draft, setDraft] = useState<SetupDraft>(() => initialDraft(state));
  const [keyStatuses, setKeyStatuses] = useState<SetupKeyStatuses>({});
  const [checking, setChecking] = useState(false);
  const [checkItems, setCheckItems] = useState<CheckItemView[] | null>(
    () => state.lastCheck?.items ?? null,
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshKeys = useCallback(async () => {
    try {
      const res = await fetch("/api/provider-keys", { cache: "no-store" });
      const data = (await res.json()) as { keys?: Array<{ envVar: string } & Record<string, unknown>> };
      if (Array.isArray(data.keys)) {
        setKeyStatuses(
          Object.fromEntries(data.keys.map((k) => [k.envVar, k as never])),
        );
      }
    } catch {
      /* key status is advisory; leave the map empty */
    }
  }, []);

  useEffect(() => {
    void refreshKeys();
  }, [refreshKeys]);

  // Lock the page behind the setup card. Only the card's content area scrolls.
  useEffect(() => {
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
    };
  }, []);

  // Focus trap: the app behind the overlay must not be reachable by Tab.
  const cardRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const root = cardRef.current;
    if (!root) return;
    const focusables = () =>
      Array.from(
        root.querySelectorAll<HTMLElement>(
          'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])',
        ),
      ).filter((el) => el.offsetParent !== null);
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Tab") return;
      const list = focusables();
      if (list.length === 0) return;
      const first = list[0];
      const last = list[list.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    root.focus();
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const updateDraft = (patch: Partial<SetupDraft>) => {
    setDraft((current) => {
      const next = { ...current, ...patch };
      if (patch.mode && patch.mode !== current.mode) {
        next.sources = safeSourceDefaults(patch.mode);
        next.accepted = [];
        next.bundleId = patch.mode === "commercial" ? "commercial" : "research";
        next.priceMode = "skip";
      }
      if (patch.bundleId && patch.bundleId !== current.bundleId) {
        next.sources = bundleSources(patch.bundleId, next.mode);
        next.accepted = [];
      }
      return next;
    });
  };

  const goToStep = (step: number) => {
    if (step < 0 || step >= STEPS.length) return;
    if (step === 0 && !draft.riskAck) return;
    setError(null);
    updateDraft({ step });
  };

  const saveKey = useCallback(async (envVar: string, value: string): Promise<string> => {
    try {
      const res = await fetch("/api/provider-keys", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ envVar, value }),
      });
      const data = (await res.json()) as { error?: string };
      if (!res.ok) return data.error || "Could not save the key.";
      await refreshKeys();
      return "Saved. The provider will be used on the next request.";
    } catch (err) {
      return err instanceof Error ? err.message : "Could not save the key.";
    }
  }, [refreshKeys]);

  const runCheck = async () => {
    setChecking(true);
    setCheckItems(null);
    try {
      const enabled = state.sources
        .filter((s) => draft.sources[s.id] === true)
        .map((s) => s.id);
      const preset = getLLMPreset(draft.aiPreset);
      const aiConfig =
        draft.aiKind === "keep" || draft.aiKind === "skip"
          ? undefined
          : draft.aiKind === "local"
            ? { baseUrl: draft.aiBaseUrl || preset?.baseUrl, model: draft.aiModel || preset?.model }
            : draft.aiKind === "key"
              ? {
                  baseUrl: preset?.baseUrl,
                  model: draft.aiModel || preset?.model,
                  apiKey: draft.aiApiKey || undefined,
                }
              : {
                  baseUrl: draft.aiBaseUrl,
                  model: draft.aiModel,
                  apiKey: draft.aiApiKey || undefined,
                };
      const res = await fetch("/api/setup/check", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          ai: draft.aiKind !== "skip",
          aiConfig,
          sources: enabled,
        }),
      });
      const data = (await res.json()) as { items?: CheckItemView[]; error?: string };
      if (!res.ok) throw new Error(data.error || "Check failed");
      setCheckItems(data.items ?? []);
    } catch (err) {
      setCheckItems([{
        id: "check",
        label: "Check",
        status: "failed",
        message: err instanceof Error ? err.message : "Check failed",
      }]);
    } finally {
      setChecking(false);
    }
  };

  const finish = async (skip = false) => {
    if (!draft.riskAck) {
      setError("Acknowledge the risk notice to continue.");
      setDraft((current) => ({ ...current, step: 0 }));
      return;
    }
    setBusy(true);
    setError(null);
    const riskAck = { version: RISK_DISCLOSURE_VERSION };
    try {
      const body = skip
        ? {
            mode: "personal",
            bundleId: "research",
            sources: safeSourceDefaults("personal"),
            acceptedRestrictedSources: [],
            ai: { kind: "skip" },
            riskAck,
          }
        : {
            mode: draft.mode,
            bundleId: draft.bundleId,
            sources: draft.sources,
            acceptedRestrictedSources: draft.accepted,
            ai: draftAiChoice(draft),
            riskAck,
          };
      const res = await fetch("/api/setup", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = (await res.json()) as { error?: string };
      if (!res.ok) throw new Error(data.error || "Could not save setup");
      seedStarterDashboard(
        BUNDLE_TEMPLATE[skip ? "research" : draft.bundleId] ?? "research",
      );
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save setup");
    } finally {
      setBusy(false);
    }
  };

  const active = STEPS[draft.step];
  const ActiveIcon = active.icon;
  const progress = useMemo(() => ((draft.step + 1) / STEPS.length) * 100, [draft.step]);

  return (
    <div
      className="fixed inset-0 z-[200] overflow-hidden bg-background"
      role="dialog"
      aria-modal="true"
      aria-label="BlackEclipse setup"
    >
      {/* Same launch-page treatment: a masked 44px brand grid and a soft glow. */}
      <div
        className="pointer-events-none fixed inset-0"
        style={{
          backgroundImage:
            "linear-gradient(rgba(180,255,66,0.08) 1px, transparent 1px), linear-gradient(90deg, rgba(180,255,66,0.08) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
          maskImage: "radial-gradient(closest-side at 50% 42%, #000 20%, transparent 100%)",
          WebkitMaskImage: "radial-gradient(closest-side at 50% 42%, #000 20%, transparent 100%)",
        }}
      />
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(closest-side_at_50%_30%,rgba(180,255,66,0.13),transparent_72%)]" />

      <div className="relative flex min-h-full items-center justify-center p-3 sm:p-6">
        <main className="w-full max-w-[1060px]">
          <div
            ref={cardRef}
            tabIndex={-1}
            className="glass-card-strong relative flex max-h-[calc(100dvh-1.5rem)] flex-col overflow-hidden rounded-2xl border border-white/12 outline-none sm:max-h-[calc(100dvh-3rem)]"
          >
            <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/50 to-transparent" />

            <div className="grid min-h-0 flex-1 md:grid-cols-[300px_minmax(0,1fr)]">
              {/* ── Left rail: brand + stepper ───────────────────────────── */}
              <aside className="hidden flex-col border-r border-white/[0.07] bg-white/[0.025] px-6 py-7 md:flex">
                <img
                  src="/branding/LOGO-WORDMARK.svg"
                  alt="BlackEclipse"
                  className="h-[24px] w-auto self-start"
                />

                <ol className="relative mb-auto mt-9">
                  {/* One continuous rail behind the discs: the icons are opaque,
                      so the line can never show through a glyph. */}
                  <span
                    aria-hidden
                    className="absolute left-[19.5px] top-5 bottom-5 w-px bg-white/[0.08]"
                  />
                  <span
                    aria-hidden
                    className="absolute left-[19.5px] top-5 w-px bg-primary/50"
                    style={{
                      height: `calc(${draft.step / (STEPS.length - 1)} * (100% - 2.5rem))`,
                    }}
                  />
                  {STEPS.map((step, index) => {
                    const done = index < draft.step;
                    const isActive = index === draft.step;
                    const Icon = step.icon;
                    const reachable = index === 0 ? draft.riskAck : index < draft.step + 1;
                    return (
                      <li key={step.id} className="relative flex gap-3.5 pb-7 last:pb-0">
                        <span
                          className={cn(
                            "relative z-10 flex h-10 w-10 shrink-0 items-center justify-center rounded-full border transition-colors",
                            isActive
                              ? "border-primary bg-primary text-primary-foreground shadow-[0_0_0_5px_color-mix(in_srgb,var(--primary)_14%,transparent)]"
                              : done
                                ? "border-primary/40 bg-[color-mix(in_srgb,var(--primary)_16%,var(--card))] text-primary"
                                : "border-white/12 bg-[color-mix(in_srgb,white_4%,var(--card))] text-muted-foreground/70",
                          )}
                        >
                          {done ? <Check size={16} weight="bold" /> : <Icon size={16} />}
                        </span>
                        <span className="min-w-0 pt-0.5">
                          <button
                            type="button"
                            disabled={!reachable || index === draft.step}
                            onClick={() => goToStep(index)}
                            className={cn(
                              "block text-left text-[13.5px] font-semibold leading-tight transition-colors",
                              isActive
                                ? "text-foreground"
                                : done
                                  ? "text-foreground/80 hover:text-foreground"
                                  : "text-muted-foreground/60",
                              reachable && !isActive ? "cursor-pointer" : "cursor-default",
                            )}
                          >
                            {step.title}
                          </button>
                          <span
                            className={cn(
                              "mt-1 block text-[11.5px] leading-snug",
                              isActive ? "text-muted-foreground" : "text-muted-foreground/55",
                            )}
                          >
                            {step.short}
                          </span>
                        </span>
                      </li>
                    );
                  })}
                </ol>

                <div className="mt-8 space-y-1 border-t border-white/[0.07] pt-4">
                  <p className="font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground/40">
                    Local setup · 127.0.0.1
                  </p>
                  <p className="text-[11px] leading-relaxed text-muted-foreground/50">
                    Your keys stay on this machine.
                  </p>
                </div>
              </aside>

              {/* ── Right panel: step content + actions ──────────────────── */}
              <section className="flex min-h-0 flex-col">
                {/* Mobile brand + progress (rail is hidden below md). */}
                <div className="flex items-center gap-3 border-b border-white/[0.07] px-5 py-3 md:hidden">
                  <img
                    src="/branding/LOGO-WORDMARK.svg"
                    alt="BlackEclipse"
                    className="h-[20px] w-auto"
                  />
                  <span className="ml-auto text-[11px] text-muted-foreground">
                    Step {draft.step + 1} of {STEPS.length}
                  </span>
                </div>
                <div className="px-5 pt-4 md:hidden">
                  <div className="h-[3px] overflow-hidden rounded-full bg-white/[0.08]">
                    <div
                      className="h-full rounded-full bg-primary transition-[width] duration-500"
                      style={{ width: `${progress}%` }}
                    />
                  </div>
                </div>

                <header className="flex items-start gap-3.5 px-5 pb-1 pt-6 sm:px-8">
                  <span className="mt-0.5 hidden h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-primary/25 bg-primary/12 text-primary sm:flex">
                    <ActiveIcon size={20} />
                  </span>
                  <div className="min-w-0">
                    <h1 className="font-serif text-[22px] font-semibold leading-[1.25] tracking-[-0.01em] text-foreground">
                      {active.title}
                    </h1>
                    <p className="mt-1 max-w-[56ch] text-[13px] leading-relaxed text-muted-foreground">
                      {active.description}
                    </p>
                  </div>
                </header>

                <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain px-5 pb-6 pt-5 sm:px-8">
                  {draft.step === 0 && (
                    <WelcomeStep state={state} draft={draft} setDraft={updateDraft} />
                  )}
                  {draft.step === 1 && (
                    <AiStep state={state} draft={draft} setDraft={updateDraft} />
                  )}
                  {draft.step === 2 && (
                    <IncludedStep state={state} draft={draft} setDraft={updateDraft} />
                  )}
                  {draft.step === 3 && (
                    <ProvidersStep
                      state={state}
                      draft={draft}
                      setDraft={updateDraft}
                      keyStatuses={keyStatuses}
                      onSaveKey={saveKey}
                    />
                  )}
                  {draft.step === 4 && (
                    <ReviewStep
                      state={state}
                      draft={draft}
                      keyStatuses={keyStatuses}
                      checking={checking}
                      checkItems={checkItems}
                      onCheck={() => void runCheck()}
                      error={error}
                    />
                  )}
                </div>

                <div className="flex items-center gap-2 border-t border-white/[0.07] bg-white/[0.015] px-5 py-3.5 sm:px-8">
                  {draft.step === 0 ? (
                    <button
                      type="button"
                      className="rounded-lg px-2 py-1.5 text-[12px] font-medium text-muted-foreground transition-colors hover:text-foreground disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
                      disabled={!draft.riskAck}
                      title={draft.riskAck ? undefined : "Acknowledge the risk notice first"}
                      onClick={() => void finish(true)}
                    >
                      Skip for now
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="inline-flex items-center gap-1.5 rounded-lg px-2 py-1.5 text-[12px] font-medium text-muted-foreground transition-colors hover:text-foreground cursor-pointer"
                      onClick={() => goToStep(draft.step - 1)}
                    >
                      <ArrowLeft size={13} /> Back
                    </button>
                  )}

                  <span className="flex-1" />

                  {draft.step < STEPS.length - 1 ? (
                    <button
                      type="button"
                      className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-[12.5px] font-semibold text-primary-foreground transition-colors hover:bg-primary/85 disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
                      disabled={draft.step === 0 && !draft.riskAck}
                      title={
                        draft.step === 0 && !draft.riskAck
                          ? "Acknowledge the risk notice first"
                          : undefined
                      }
                      onClick={() => goToStep(draft.step + 1)}
                    >
                      Continue <ArrowRight size={13} />
                    </button>
                  ) : (
                    <button
                      type="button"
                      className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-2 text-[12.5px] font-semibold text-primary-foreground transition-colors hover:bg-primary/85 disabled:cursor-not-allowed disabled:opacity-40 cursor-pointer"
                      disabled={busy || !draft.riskAck}
                      title={draft.riskAck ? undefined : "Acknowledge the risk notice first"}
                      onClick={() => void finish(false)}
                    >
                      {busy ? (
                        <Loader2 size={13} className="animate-spin" />
                      ) : (
                        <Check size={13} weight="bold" />
                      )}
                      {busy ? "Saving…" : "Finish setup"}
                    </button>
                  )}
                </div>
              </section>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}
