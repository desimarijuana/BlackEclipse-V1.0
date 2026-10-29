// ── Paper windows ───────────────────────────────────────────────────────────
// A "paper deployment" used to replay the research window and call it paper.
// This module makes the distinction explicit:
//
//   forward — start the day after the research window ends, run to today
//   replay  — the research window itself, labelled as a replay
//
// A forward window that would start after today is NOT available; the caller
// must say so rather than quietly falling back to a replay.

export type PaperMode = "forward" | "replay";

export interface PaperWindow {
  mode: PaperMode;
  start: string;
  end: string;
  days: number;
  available: boolean;
  reason?: string;
}

const DAY = 86_400_000;

export function isoToday(now: Date = new Date()): string {
  return now.toISOString().slice(0, 10);
}

export function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return new Date(date.getTime() + days * DAY).toISOString().slice(0, 10);
}

export function daysBetween(start: string, end: string): number {
  const a = new Date(`${start}T00:00:00Z`).getTime();
  const b = new Date(`${end}T00:00:00Z`).getTime();
  if (Number.isNaN(a) || Number.isNaN(b)) return 0;
  return Math.max(0, Math.round((b - a) / DAY));
}

export function computePaperWindow(input: {
  mode: PaperMode;
  researchStart: string;
  researchEnd: string;
  today?: string;
}): PaperWindow {
  const today = input.today ?? isoToday();
  const valid = Boolean(input.researchStart) && Boolean(input.researchEnd);
  if (!valid) {
    return {
      mode: input.mode,
      start: "",
      end: "",
      days: 0,
      available: false,
      reason: "The research window is not set.",
    };
  }
  if (input.mode === "replay") {
    return {
      mode: "replay",
      start: input.researchStart,
      end: input.researchEnd,
      days: daysBetween(input.researchStart, input.researchEnd),
      available: true,
      reason: "Replays the same window as the backtest; it is not forward-looking.",
    };
  }
  const start = addDays(input.researchEnd, 1);
  if (start > today) {
    return {
      mode: "forward",
      start,
      end: today,
      days: 0,
      available: false,
      reason:
        "The research window ends today, so there is no forward period yet. End the backtest earlier, or use a replay.",
    };
  }
  return {
    mode: "forward",
    start,
    end: today,
    days: daysBetween(start, today) + 1,
    available: true,
  };
}

/** The mode to offer first: forward when there is a forward window, else replay. */
export function defaultPaperMode(researchEnd: string, today: string = isoToday()): PaperMode {
  return addDays(researchEnd, 1) <= today ? "forward" : "replay";
}
