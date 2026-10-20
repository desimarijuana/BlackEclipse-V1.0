"use client";

// RSL operator tools: adopt a verified lesson and run one bounded recursive
// experiment. Both call the Next.js proxy; the Python runtime owns validation
// and verification. Nothing here applies a change.

import { useCallback, useEffect, useState } from "react";
import { useT } from "@/lib/i18n/use-t";
import {
  activateEvolutionSurfaceStateBrowser,
  adoptEvolutionLessonBrowser,
  createEvolutionSurfaceExperimentBrowser,
  getEvolutionCandidateStateBrowser,
  getEvolutionSurfacePreviewBrowser,
  listEvolutionLessonsBrowser,
  runEvolutionRecursiveBrowser,
} from "@/lib/harness/evolution-browser";
import type {
  EvolutionHarnessState,
  EvolutionLesson,
  EvolutionRecursiveResult,
  EvolutionRecursiveVariant,
  EvolutionSurfaceExperimentInput,
  EvolutionSurfaceExperimentResult,
  EvolutionSurfacePreview,
  EvolutionSurfaceSnapshot,
} from "@/lib/harness/evolution-client";
import { SurfaceActivationCard } from "./surface-activation-card";

const SAMPLE_VARIANTS = JSON.stringify(
  [
    {
      kind: "invariant",
      targetPath: "python/harness/rsl_fixture.py",
      ops: [
        {
          op: "create",
          path: "python/harness/rsl_fixture.py",
          content: "VALUE = 1\n",
          reason: "invariant fixture",
        },
      ],
    },
    {
      kind: "domain",
      targetPath: "python/harness/rsl_fixture_domain.py",
      ops: [
        {
          op: "create",
          path: "python/harness/rsl_fixture_domain.py",
          content: "VALUE = 1\n",
          reason: "domain fixture",
        },
      ],
    },
  ],
  null,
  2,
);

const SAMPLE_BASE_SNAPSHOT = JSON.stringify(
  {
    systemPrompt: "You are Eclipse.",
    toolNames: [],
    maxSteps: 8,
    maxToolCalls: 8,
  },
  null,
  2,
);

const SAMPLE_CANDIDATE_SNAPSHOT = JSON.stringify(
  {
    systemPrompt: "You are Eclipse. Prefer the deterministic evaluation tools.",
    toolNames: [],
    maxSteps: 8,
    maxToolCalls: 8,
  },
  null,
  2,
);

function parseJson(text: string): unknown {
  if (!text.trim()) return undefined;
  return JSON.parse(text);
}

export function RslOperatorPanel() {
  const t = useT();
  const [lessons, setLessons] = useState<EvolutionLesson[]>([]);
  const [lessonError, setLessonError] = useState<string | null>(null);

  const [candidateId, setCandidateId] = useState("");
  const [validationRunId, setValidationRunId] = useState("");
  const [cue, setCue] = useState("");
  const [lessonText, setLessonText] = useState("");
  const [evidence, setEvidence] = useState("");
  const [scope, setScope] = useState("");
  const [adopting, setAdopting] = useState(false);
  const [adopted, setAdopted] = useState<string | null>(null);

  const [recursiveCandidateId, setRecursiveCandidateId] = useState("");
  const [variants, setVariants] = useState(SAMPLE_VARIANTS);
  const [seed, setSeed] = useState("0");
  const [running, setRunning] = useState(false);
  const [recursiveResult, setRecursiveResult] = useState<EvolutionRecursiveResult | null>(null);
  const [recursiveError, setRecursiveError] = useState<string | null>(null);

  const [surfaceBase, setSurfaceBase] = useState(SAMPLE_BASE_SNAPSHOT);
  const [surfaceCandidate, setSurfaceCandidate] = useState(SAMPLE_CANDIDATE_SNAPSHOT);
  const [surfaceScope, setSurfaceScope] = useState("global");
  const [surfaceDataset, setSurfaceDataset] = useState("benchmark_v1");
  const [surfaceSplit, setSurfaceSplit] = useState("validation");
  const [surfaceTarget, setSurfaceTarget] = useState("task_success");
  const [surfaceTrials, setSurfaceTrials] = useState("1");
  const [surfaceSeed, setSurfaceSeed] = useState("0");
  const [surfaceProblem, setSurfaceProblem] = useState("");
  const [surfaceRunning, setSurfaceRunning] = useState(false);
  const [surfaceResult, setSurfaceResult] = useState<EvolutionSurfaceExperimentResult | null>(null);
  const [surfaceError, setSurfaceError] = useState<string | null>(null);
  const [derivedState, setDerivedState] = useState<EvolutionHarnessState | null>(null);
  const [derivedPreview, setDerivedPreview] = useState<EvolutionSurfacePreview | null>(null);
  const [derivedScope, setDerivedScope] = useState("global");
  const [derivedLoading, setDerivedLoading] = useState(false);
  const [derivedActivating, setDerivedActivating] = useState(false);
  const [derivedError, setDerivedError] = useState<string | null>(null);

  const loadLessons = useCallback(async () => {
    setLessonError(null);
    try {
      setLessons(await listEvolutionLessonsBrowser());
    } catch (err) {
      setLessonError(err instanceof Error ? err.message : "failed to load lessons");
    }
  }, []);
  useEffect(() => { void loadLessons(); }, [loadLessons]);

  const adopt = useCallback(async () => {
    setAdopting(true);
    setAdopted(null);
    setLessonError(null);
    try {
      let parsedEvidence: unknown;
      try {
        parsedEvidence = parseJson(evidence);
      } catch {
        throw new Error(t("evolution.lesson.invalidJson"));
      }
      let parsedScope: Record<string, unknown> | undefined;
      try {
        const value = parseJson(scope);
        parsedScope = value && typeof value === "object" ? value as Record<string, unknown> : undefined;
      } catch {
        throw new Error(t("evolution.lesson.invalidJson"));
      }
      const result = await adoptEvolutionLessonBrowser(candidateId.trim(), {
        cue: cue.trim(),
        lesson: lessonText.trim(),
        evidence: parsedEvidence,
        scope: parsedScope,
        validationRunId: validationRunId.trim(),
      });
      setAdopted(result.lesson?.id ?? null);
      await loadLessons();
    } catch (err) {
      setLessonError(err instanceof Error ? err.message : "lesson adoption failed");
    } finally {
      setAdopting(false);
    }
  }, [adoptEvolutionLessonBrowser, candidateId, cue, evidence, lessonText, loadLessons, scope, t, validationRunId]);

  const runRecursive = useCallback(async () => {
    setRunning(true);
    setRecursiveError(null);
    setRecursiveResult(null);
    try {
      let parsed: unknown;
      try {
        parsed = parseJson(variants);
      } catch {
        throw new Error(t("evolution.recursive.invalidJson"));
      }
      if (!Array.isArray(parsed) || parsed.length === 0) {
        throw new Error(t("evolution.recursive.invalidJson"));
      }
      const result = await runEvolutionRecursiveBrowser(recursiveCandidateId.trim(), {
        variants: parsed as EvolutionRecursiveVariant[],
        seed: Number.isFinite(Number(seed)) ? Number(seed) : 0,
      });
      setRecursiveResult(result);
    } catch (err) {
      setRecursiveError(err instanceof Error ? err.message : "recursive experiment failed");
    } finally {
      setRunning(false);
    }
  }, [recursiveCandidateId, seed, t, variants]);

  const runSurface = useCallback(async () => {
    setSurfaceRunning(true);
    setSurfaceError(null);
    setSurfaceResult(null);
    try {
      let parsedBase: unknown;
      let parsedCandidate: unknown;
      try {
        parsedBase = parseJson(surfaceBase);
        parsedCandidate = parseJson(surfaceCandidate);
      } catch {
        throw new Error(t("evolution.surface.invalidJson"));
      }
      if (!parsedCandidate || typeof parsedCandidate !== "object") {
        throw new Error(t("evolution.surface.invalidJson"));
      }
      const input: EvolutionSurfaceExperimentInput = {
        candidate: parsedCandidate as EvolutionSurfaceSnapshot,
        scope: surfaceScope.trim() || "global",
        dataset: surfaceDataset.trim() || "benchmark_v1",
        split: surfaceSplit as EvolutionSurfaceExperimentInput["split"],
        targetDimension: surfaceTarget.trim() || "task_success",
        trials: Number.isFinite(Number(surfaceTrials)) ? Number(surfaceTrials) : 1,
        seed: Number.isFinite(Number(surfaceSeed)) ? Number(surfaceSeed) : 0,
        problemStatement: surfaceProblem.trim() || undefined,
      };
      if (parsedBase && typeof parsedBase === "object") {
        input.base = parsedBase as EvolutionSurfaceSnapshot;
      }
      setSurfaceResult(await createEvolutionSurfaceExperimentBrowser(input));
    } catch (err) {
      setSurfaceError(err instanceof Error ? err.message : "surface experiment failed");
    } finally {
      setSurfaceRunning(false);
    }
  }, [
    surfaceBase, surfaceCandidate, surfaceDataset, surfaceProblem, surfaceSeed,
    surfaceScope, surfaceSplit, surfaceTarget, surfaceTrials, t,
  ]);

  const findDerivedState = useCallback(async (candidateId: string, scope: string) => {
    setDerivedLoading(true);
    setDerivedError(null);
    setDerivedState(null);
    setDerivedPreview(null);
    try {
      const result = await getEvolutionCandidateStateBrowser(candidateId);
      if (!result.state) {
        setDerivedError(t("evolution.surface.stateMissing"));
        return;
      }
      setDerivedState(result.state);
      const preview = await getEvolutionSurfacePreviewBrowser(
        result.state.id, scope || result.state.scope,
      );
      setDerivedPreview(preview);
      setDerivedScope(preview.scope);
    } catch (err) {
      setDerivedError(err instanceof Error ? err.message : "state lookup failed");
    } finally {
      setDerivedLoading(false);
    }
  }, [t]);

  const activateDerived = useCallback(async () => {
    if (!derivedState) return;
    setDerivedActivating(true);
    setDerivedError(null);
    try {
      await activateEvolutionSurfaceStateBrowser(derivedState.id, derivedScope);
      await findDerivedState(derivedState.candidateId ?? "", derivedScope);
    } catch (err) {
      setDerivedError(err instanceof Error ? err.message : "activation failed");
    } finally {
      setDerivedActivating(false);
    }
  }, [derivedScope, derivedState, findDerivedState]);

  const inputClass =
    "w-full rounded-lg border border-border/50 bg-background/40 px-2.5 py-1.5 text-[11px] text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-primary/40";

  return (
    <div className="mt-5 space-y-4">
      <section className="glass-card-subtle p-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <div>
            <h4 className="text-xs font-semibold text-foreground">{t("evolution.lesson.title")}</h4>
            <p className="mt-1 text-[10px] text-muted-foreground">{t("evolution.lesson.subtitle")}</p>
          </div>
          <button
            type="button"
            onClick={() => void loadLessons()}
            className="rounded-lg border border-border/50 px-2 py-1 text-[10px] text-muted-foreground transition hover:text-foreground"
          >
            {t("evolution.lesson.refresh")}
          </button>
        </div>
        {lessonError && (
          <p className="mb-2 rounded-lg border border-rose-400/30 bg-rose-400/5 px-2 py-1 text-[10px] text-rose-300">
            {lessonError}
          </p>
        )}
        {lessons.length === 0 ? (
          <p className="text-[11px] text-muted-foreground">{t("evolution.lesson.empty")}</p>
        ) : (
          <ul className="space-y-2">
            {lessons.map((lesson) => (
              <li key={lesson.id} className="rounded-lg border border-border/40 bg-background/30 p-2">
                <p className="text-[11px] font-medium text-foreground">{lesson.cue ?? lesson.id}</p>
                <p className="mt-0.5 text-[10px] text-muted-foreground">{lesson.proposedLesson}</p>
                <p className="mt-1 text-[10px] text-muted-foreground">
                  {lesson.validationRunId ?? t("evolution.lesson.unvalidated")}
                  {lesson.adoptedArtifactId ? ` · ${lesson.adoptedArtifactId}` : ""}
                </p>
              </li>
            ))}
          </ul>
        )}

        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <input
            className={inputClass}
            placeholder={t("evolution.lesson.candidate")}
            value={candidateId}
            onChange={(event) => setCandidateId(event.target.value)}
          />
          <input
            className={inputClass}
            placeholder={t("evolution.lesson.validationRun")}
            value={validationRunId}
            onChange={(event) => setValidationRunId(event.target.value)}
          />
          <input
            className={`${inputClass} sm:col-span-2`}
            placeholder={t("evolution.lesson.cue")}
            value={cue}
            onChange={(event) => setCue(event.target.value)}
          />
          <textarea
            className={`${inputClass} sm:col-span-2`}
            rows={2}
            placeholder={t("evolution.lesson.body")}
            value={lessonText}
            onChange={(event) => setLessonText(event.target.value)}
          />
          <textarea
            className={inputClass}
            rows={2}
            placeholder={t("evolution.lesson.evidence")}
            value={evidence}
            onChange={(event) => setEvidence(event.target.value)}
          />
          <textarea
            className={inputClass}
            rows={2}
            placeholder={t("evolution.lesson.scope")}
            value={scope}
            onChange={(event) => setScope(event.target.value)}
          />
        </div>
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            onClick={() => void adopt()}
            disabled={adopting || !candidateId.trim() || !validationRunId.trim() || !cue.trim() || !lessonText.trim()}
            className="rounded-lg border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] text-primary transition hover:bg-primary/15 disabled:opacity-50"
          >
            {adopting ? t("evolution.lesson.adopting") : t("evolution.lesson.adopt")}
          </button>
          {adopted && <span className="text-[10px] text-emerald-300">{t("evolution.lesson.adopted")}</span>}
        </div>
      </section>

      <section className="glass-card-subtle p-4">
        <h4 className="text-xs font-semibold text-foreground">{t("evolution.recursive.title")}</h4>
        <p className="mt-1 text-[10px] text-muted-foreground">{t("evolution.recursive.subtitle")}</p>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <input
            className={inputClass}
            placeholder={t("evolution.recursive.candidate")}
            value={recursiveCandidateId}
            onChange={(event) => setRecursiveCandidateId(event.target.value)}
          />
          <input
            className={inputClass}
            placeholder={t("evolution.recursive.seed")}
            value={seed}
            onChange={(event) => setSeed(event.target.value)}
          />
          <textarea
            className={`${inputClass} font-mono sm:col-span-2`}
            rows={8}
            aria-label={t("evolution.recursive.variants")}
            value={variants}
            onChange={(event) => setVariants(event.target.value)}
          />
        </div>
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            onClick={() => void runRecursive()}
            disabled={running || !recursiveCandidateId.trim()}
            className="rounded-lg border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] text-primary transition hover:bg-primary/15 disabled:opacity-50"
          >
            {running ? t("evolution.recursive.running") : t("evolution.recursive.run")}
          </button>
          {recursiveError && <span className="text-[10px] text-rose-300">{recursiveError}</span>}
          {recursiveResult && (
            <span className="text-[10px] text-muted-foreground">
              {t("evolution.recursive.result", {
                k: recursiveResult.k,
                decision: String(
                  (recursiveResult.composition as { decision?: string } | null)?.decision
                    ?? "no_gain",
                ),
                benchmark: recursiveResult.benchmark,
              })}
            </span>
          )}
        </div>
      </section>

      <section className="glass-card-subtle p-4">
        <h4 className="text-xs font-semibold text-foreground">{t("evolution.surface.title")}</h4>
        <p className="mt-1 text-[10px] text-muted-foreground">{t("evolution.surface.subtitle")}</p>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          <textarea
            className={`${inputClass} font-mono`}
            rows={5}
            aria-label={t("evolution.surface.base")}
            value={surfaceBase}
            onChange={(event) => setSurfaceBase(event.target.value)}
          />
          <textarea
            className={`${inputClass} font-mono`}
            rows={5}
            aria-label={t("evolution.surface.candidate")}
            value={surfaceCandidate}
            onChange={(event) => setSurfaceCandidate(event.target.value)}
          />
          <input
            className={inputClass}
            placeholder={t("evolution.surface.scope")}
            value={surfaceScope}
            onChange={(event) => setSurfaceScope(event.target.value)}
          />
          <input
            className={inputClass}
            placeholder={t("evolution.surface.dataset")}
            value={surfaceDataset}
            onChange={(event) => setSurfaceDataset(event.target.value)}
          />
          <input
            className={inputClass}
            placeholder={t("evolution.surface.split")}
            value={surfaceSplit}
            onChange={(event) => setSurfaceSplit(event.target.value)}
          />
          <input
            className={inputClass}
            placeholder={t("evolution.surface.target")}
            value={surfaceTarget}
            onChange={(event) => setSurfaceTarget(event.target.value)}
          />
          <input
            className={inputClass}
            placeholder={t("evolution.surface.trials")}
            value={surfaceTrials}
            onChange={(event) => setSurfaceTrials(event.target.value)}
          />
          <input
            className={inputClass}
            placeholder={t("evolution.surface.seed")}
            value={surfaceSeed}
            onChange={(event) => setSurfaceSeed(event.target.value)}
          />
          <input
            className={inputClass}
            placeholder={t("evolution.surface.problem")}
            value={surfaceProblem}
            onChange={(event) => setSurfaceProblem(event.target.value)}
          />
        </div>
        <div className="mt-2 flex items-center gap-2">
          <button
            type="button"
            onClick={() => void runSurface()}
            disabled={surfaceRunning || !surfaceCandidate.trim()}
            className="rounded-lg border border-primary/30 bg-primary/10 px-2.5 py-1 text-[11px] text-primary transition hover:bg-primary/15 disabled:opacity-50"
          >
            {surfaceRunning ? t("evolution.surface.running") : t("evolution.surface.run")}
          </button>
          {surfaceError && <span className="text-[10px] text-rose-300">{surfaceError}</span>}
          {surfaceResult && (
            <>
              <span className="text-[10px] text-muted-foreground">
                {surfaceResult.queued
                  ? t("evolution.surface.queued", { id: surfaceResult.candidate.id })
                  : t("evolution.surface.existing", { id: surfaceResult.candidate.id })}
              </span>
              <button
                type="button"
                onClick={() => void findDerivedState(surfaceResult.candidate.id, surfaceScope)}
                disabled={derivedLoading}
                className="rounded-lg border border-sky-400/30 bg-sky-400/10 px-2.5 py-1 text-[10px] text-sky-300 transition hover:bg-sky-400/15 disabled:opacity-50"
              >
                {derivedLoading
                  ? t("evolution.surface.findingState")
                  : t("evolution.surface.findState")}
              </button>
            </>
          )}
        </div>
        {derivedError && (
          <p className="mt-2 rounded-lg border border-rose-400/30 bg-rose-400/5 px-2 py-1 text-[10px] text-rose-300">
            {derivedError}
          </p>
        )}
        {derivedState && derivedPreview && (
          <div className="mt-2">
            <SurfaceActivationCard
              state={derivedState}
              preview={derivedPreview}
              scope={derivedScope}
              onScopeChange={(next) => {
                setDerivedScope(next);
                void findDerivedState(derivedState.candidateId ?? "", next);
              }}
              onActivate={() => void activateDerived()}
              activating={derivedActivating}
            />
          </div>
        )}
      </section>
    </div>
  );
}
