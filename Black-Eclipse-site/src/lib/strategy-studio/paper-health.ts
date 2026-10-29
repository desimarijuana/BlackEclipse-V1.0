// ── Paper health ────────────────────────────────────────────────────────────
// "Is the paper track record still meaningful?" A run that is months old, or a
// run whose metrics have drifted far from the research window, is reported as
// such. Thresholds are explicit constants and every one is printed in the
// detail, so the badge is a statement about the data, not a hidden score.
//
// This is NOT an alert engine: it reads the runs the runtime already recorded.

export type PaperHealthState = "none" | "fresh" | "stale" | "drifting";

export const STALE_AFTER_DAYS = 30;
export const DRIFT_RETURN_POINTS = 10;
export const DRIFT_SHARPE = 0.5;

export interface PaperDrift {
  metric: string;
  paper: number | null;
  baseline: number | null;
  delta: number | null;
}

export interface PaperHealth {
  state: PaperHealthState;
  stalenessDays: number | null;
  headline: string;
  detail: string;
  drift: PaperDrift[];
}

const DRIFT_METRICS = ["total_return", "sharpe", "max_drawdown"] as const;

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function delta(paper: unknown, baseline: unknown): number | null {
  const a = numberOrNull(paper);
  const b = numberOrNull(baseline);
  return a === null || b === null ? null : a - b;
}

export function paperHealth(input: {
  lastRunAt?: string | null;
  paperMetrics?: Record<string, number | null> | null;
  baselineMetrics?: Record<string, number | null> | null;
  now?: Date;
}): PaperHealth {
  const now = input.now ?? new Date();
  if (!input.lastRunAt) {
    return {
      state: "none",
      stalenessDays: null,
      headline: "No paper run yet",
      detail: "Deploy a paper run to start a track record.",
      drift: [],
    };
  }

  const then = new Date(input.lastRunAt).getTime();
  const stalenessDays = Number.isNaN(then)
    ? null
    : Math.max(0, Math.floor((now.getTime() - then) / 86_400_000));

  const drift: PaperDrift[] = DRIFT_METRICS.map((metric) => ({
    metric,
    paper: numberOrNull(input.paperMetrics?.[metric]),
    baseline: numberOrNull(input.baselineMetrics?.[metric]),
    delta: delta(input.paperMetrics?.[metric], input.baselineMetrics?.[metric]),
  }));

  const returnDrift = Math.abs(drift[0].delta ?? 0);
  const sharpeDrift = Math.abs(drift[1].delta ?? 0);
  const drifting =
    (drift[0].delta !== null && returnDrift >= DRIFT_RETURN_POINTS) ||
    (drift[1].delta !== null && sharpeDrift >= DRIFT_SHARPE);

  if (stalenessDays !== null && stalenessDays >= STALE_AFTER_DAYS) {
    return {
      state: "stale",
      stalenessDays,
      headline: `Last paper run was ${stalenessDays} days ago`,
      detail: `A run older than ${STALE_AFTER_DAYS} days no longer describes current conditions.${
        drifting ? " Its metrics also differ from the research window." : ""
      }`,
      drift,
    };
  }

  if (drifting) {
    return {
      state: "drifting",
      stalenessDays,
      headline: "Paper is diverging from the research window",
      detail: `Drift beyond ${DRIFT_RETURN_POINTS} return points or ${DRIFT_SHARPE} Sharpe is flagged. This is descriptive, not a significance test.`,
      drift,
    };
  }

  return {
    state: "fresh",
    stalenessDays,
    headline:
      stalenessDays === null
        ? "Paper run recorded"
        : `Last paper run was ${stalenessDays} day${stalenessDays === 1 ? "" : "s"} ago`,
    detail: "The track record is recent and within the stated drift limits.",
    drift,
  };
}
