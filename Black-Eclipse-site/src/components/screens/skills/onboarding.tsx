"use client";

// ── Cold-start onboarding (Phase 13) ────────────────────────────────────────
// A read-only first-run explanation of Facts / Session History / Skills, plus
// the bundled starter skills. It NEVER writes durable memory or enables a skill;
// starter content carries visible `bundled` provenance and is removable.

import { useEffect, useState } from "react";
import { GraduationCap, Sparkles, X } from "lucide-react";
import { getOnboarding } from "@/lib/harness/skills-browser";
import type { OnboardingContent } from "@/lib/harness/skills-types";
import { LoadingState } from "./skill-ui";

export function OnboardingPanel({ onClose }: { onClose?: () => void }) {
  const [content, setContent] = useState<OnboardingContent | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getOnboarding()
      .then((c) => { if (!cancelled) { setContent(c); setLoading(false); } })
      .catch((err) => { if (!cancelled) { setError(err instanceof Error ? err.message : "failed"); setLoading(false); } });
    return () => { cancelled = true; };
  }, []);

  if (loading) return <LoadingState label="Loading…" />;
  if (error) return <p className="py-4 text-[11px] text-rose-300">{error}</p>;
  if (!content) return null;

  return (
    <div className="animate-fade-in-up">
      <div className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h3 className="font-serif text-sm font-semibold tracking-tight text-foreground">Start here</h3>
          <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">
            How the memory and skills system works. This page explains only — it does not write
            anything to memory or enable a skill.
          </p>
        </div>
        {onClose && (
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground cursor-pointer"><X size={14} /></button>
        )}
      </div>

      <div className="space-y-2">
        {content.steps.map((step) => (
          <div key={step.id} className="rounded-2xl border border-white/10 glass-card p-3.5">
            <p className="text-[12px] font-semibold text-foreground">{step.title}</p>
            <p className="mt-1 text-[11px] text-muted-foreground leading-relaxed">{step.body}</p>
          </div>
        ))}
      </div>

      {content.starterSkills.length > 0 && (
        <div className="mt-4 rounded-2xl border border-white/10 glass-card p-3.5">
          <div className="flex items-center gap-2">
            <GraduationCap size={13} className="text-primary" />
            <p className="text-[12px] font-semibold text-foreground">Starter skills ({content.starterSkills.length})</p>
          </div>
          <p className="mt-1 text-[10px] text-muted-foreground">
            Bundled procedures shipped with the app. They are clearly distinct from learned skills and can be
            disabled or removed through the normal skill lifecycle.
          </p>
          <div className="mt-2 space-y-1">
            {content.starterSkills.map((s) => (
              <div key={s.id} className="flex items-start gap-2 text-[11px]">
                <Sparkles size={11} className="mt-0.5 text-primary shrink-0" />
                <span className="text-foreground">{s.name}</span>
                <span className="rounded-md border border-border/30 bg-accent/30 px-1.5 py-0.5 text-[9px] uppercase text-muted-foreground">{s.provenance}</span>
                <span className="text-muted-foreground line-clamp-1">{s.description}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <p className="mt-3 text-[10px] text-muted-foreground/80">{content.note}</p>
    </div>
  );
}
