"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, ArrowRight, Loader2 } from "@/lib/icons";
import { safeSourceDefaults } from "@/lib/setup/defaults";
import { bundleSources } from "@/lib/setup/bundles";
import { getLLMPreset } from "@/lib/agent/presets";
import type { SetupDraft, SetupKeyStatuses, SetupState } from "./types";
import { draftAiChoice } from "./types";
import { WelcomeStep } from "./steps/welcome-step";
import { AiStep } from "./steps/ai-step";
import { IncludedStep } from "./steps/included-step";
import { ProvidersStep } from "./steps/providers-step";
import { ReviewStep, type CheckItemView } from "./steps/review-step";

const STEPS = ["Welcome", "AI", "Included", "Providers", "Review"];

const PRICE_ADVANCED = ["tradingview", "yfinance", "http", "browser", "scrapling"];
const PRICE_CONNECTED = ["polygon", "twelvedata", "alphavantage", "marketstack", "finnhub"];

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
    setBusy(true);
    setError(null);
    try {
      const body = skip
        ? {
            mode: "personal",
            bundleId: "research",
            sources: safeSourceDefaults("personal"),
            acceptedRestrictedSources: [],
            ai: { kind: "skip" },
          }
        : {
            mode: draft.mode,
            bundleId: draft.bundleId,
            sources: draft.sources,
            acceptedRestrictedSources: draft.accepted,
            ai: draftAiChoice(draft),
          };
      const res = await fetch("/api/setup", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = (await res.json()) as { error?: string };
      if (!res.ok) throw new Error(data.error || "Could not save setup");
      onDone();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save setup");
    } finally {
      setBusy(false);
    }
  };

  const progress = useMemo(() => ((draft.step + 1) / STEPS.length) * 100, [draft.step]);

  const stepTitle = [
    "Welcome to BlackEclipse",
    "Choose your AI",
    "Included data",
    "Connect providers",
    "Ready to start",
  ][draft.step];

  const stepPhase = [
    "Connect your AI and data. This takes about a minute.",
    "Chat is the home surface. Connect a model now, or add one later.",
    "Open sources that ship with Eclipse. No account, no key, no charge.",
    "Live prices need a provider you are licensed to use.",
    "Check what will work before you finish.",
  ][draft.step];

  return (
    <div
      className="fixed inset-0 z-[200] overflow-hidden bg-background"
      role="dialog"
      aria-modal="true"
      aria-label="BlackEclipse setup"
    >
      {/* Exact treatment of the production launch page: a masked 44px brand
          grid, a soft top glow, and the narrow 580px launch card. */}
      <div
        className="pointer-events-none fixed inset-0"
        style={{
          backgroundImage:
            "linear-gradient(rgba(180,255,66,0.10) 1px, transparent 1px), linear-gradient(90deg, rgba(180,255,66,0.10) 1px, transparent 1px)",
          backgroundSize: "44px 44px",
          maskImage: "radial-gradient(closest-side at 50% 42%, #000 25%, transparent 100%)",
          WebkitMaskImage: "radial-gradient(closest-side at 50% 42%, #000 25%, transparent 100%)",
        }}
      />
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(closest-side_at_50%_34%,rgba(180,255,66,0.16),transparent_72%)]" />

      <div className="relative flex min-h-full items-center justify-center p-4">
        <main className="w-full max-w-[720px]">
          <div
            ref={cardRef}
            tabIndex={-1}
            className="glass-card-strong relative flex max-h-[calc(100dvh-2rem)] flex-col overflow-hidden rounded-xl border border-white/15 px-6 pb-[18px] pt-[22px] outline-none"
          >
            {/* Top brand hairline, same as the launch card. */}
            <div className="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-primary/60 to-transparent opacity-80" />

            <header className="flex min-h-[23px] items-center">
              <img
                src="/branding/LOGO-WORDMARK.svg"
                alt="BlackEclipse"
                className="block h-[22px] w-auto"
              />
            </header>

            <h1 className="mt-5 font-serif text-[20px] font-semibold leading-[1.3] tracking-[-0.01em] text-foreground">
              {stepTitle}
            </h1>
            <p className="min-h-[42px] text-[13.5px] leading-[1.55] text-muted-foreground/70">
              {stepPhase}
            </p>

            <div className="relative my-1 h-[3px] overflow-hidden rounded-full bg-white/[0.08]">
              <div
                className="relative h-full rounded-full bg-gradient-to-r from-primary to-[color-mix(in_oklch,var(--primary),white_20%)] transition-[width] duration-700"
                style={{ width: `${progress}%` }}
              >
                <span className="be-setup-sweep absolute inset-y-0 w-[45%] bg-gradient-to-r from-transparent via-white/55 to-transparent" />
              </div>
            </div>
            <div className="mt-2 flex justify-between gap-4 font-mono text-[10.5px] uppercase tracking-[0.08em] text-muted-foreground/40">
              <span>
                STEP {String(draft.step + 1).padStart(2, "0")} / {String(STEPS.length).padStart(2, "0")}
              </span>
              <span>{STEPS[draft.step]}</span>
            </div>

            <div className="mt-4 min-h-0 flex-1 overflow-y-auto overscroll-contain pr-1">
              {draft.step === 0 && <WelcomeStep state={state} draft={draft} setDraft={updateDraft} />}
              {draft.step === 1 && <AiStep state={state} draft={draft} setDraft={updateDraft} />}
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
                  onFinish={() => void finish(false)}
                  busy={busy}
                  error={error}
                />
              )}
            </div>

            <div className="mt-4 flex items-center gap-2 border-t border-white/[0.07] pt-3">
              {draft.step > 0 ? (
                <button
                  type="button"
                  className="inline-flex items-center gap-1 text-[11px] text-muted-foreground hover:text-foreground cursor-pointer"
                  onClick={() => updateDraft({ step: draft.step - 1 })}
                >
                  <ArrowLeft size={12} /> Back
                </button>
              ) : (
                <button
                  type="button"
                  className="text-[11px] text-muted-foreground underline-offset-2 hover:text-foreground hover:underline cursor-pointer"
                  onClick={() => void finish(true)}
                >
                  Skip for now
                </button>
              )}

              <span className="flex-1" />

              {draft.step < 4 && (
                <button
                  type="button"
                  className="inline-flex items-center gap-1.5 rounded-md bg-primary px-3.5 py-1.5 text-[12px] font-semibold text-primary-foreground hover:bg-primary/85 cursor-pointer"
                  onClick={() => updateDraft({ step: draft.step + 1 })}
                >
                  Continue <ArrowRight size={12} />
                </button>
              )}
              {draft.step === 4 && busy && (
                <span className="inline-flex items-center gap-1 text-[10px] text-muted-foreground">
                  <Loader2 size={12} className="animate-spin" /> Saving
                </span>
              )}
            </div>

            <footer className="mt-3 flex justify-between gap-3 border-t border-white/[0.07] pt-3 font-mono text-[10px] uppercase tracking-[0.12em] text-muted-foreground/30">
              <span>Local setup · 127.0.0.1</span>
              <span>First run</span>
            </footer>
          </div>
        </main>
      </div>
    </div>
  );
}
