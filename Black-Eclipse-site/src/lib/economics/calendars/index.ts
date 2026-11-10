// ── Official schedule fan-out ───────────────────────────────────────────────
// One entry point for every institution-published calendar. Each adapter is
// independent: one institution's outage produces a warning, never a blank
// calendar and never a fabricated date.

import { fetchFomcSchedule } from "./fomc";
import { fetchBlsSchedules } from "./bls";
import { fetchBeaSchedules } from "./bea";
import { fetchEcbSchedule } from "./ecb";
import { fetchBoeSchedule } from "./boe";
import { fetchBojSchedule } from "./boj";
import { fetchCensusRetailSchedule } from "./census";
import { dedupe, type OfficialEvent } from "./types";

export type { OfficialEvent } from "./types";

interface Adapter {
  id: string;
  run: () => Promise<OfficialEvent[]>;
}

function adapters(): Adapter[] {
  return [
    {
      id: "fomc",
      run: async () =>
        (await fetchFomcSchedule()).map((m) => ({
          date: m.date,
          time: m.time,
          title: m.title,
          country: m.country,
          importance: "high" as const,
          confirmed: m.confirmed,
          url: m.url,
        })),
    },
    { id: "bls", run: fetchBlsSchedules },
    { id: "bea", run: fetchBeaSchedules },
    { id: "ecb", run: fetchEcbSchedule },
    { id: "boe", run: fetchBoeSchedule },
    { id: "boj", run: fetchBojSchedule },
    { id: "census-retail", run: fetchCensusRetailSchedule },
  ];
}

export interface OfficialScheduleResult {
  events: OfficialEvent[];
  warnings: string[];
}

export async function fetchOfficialSchedules(): Promise<OfficialScheduleResult> {
  const list = adapters();
  const settled = await Promise.allSettled(list.map((a) => a.run()));
  const events: OfficialEvent[] = [];
  const warnings: string[] = [];
  settled.forEach((result, index) => {
    const id = list[index].id;
    if (result.status === "fulfilled") {
      events.push(...result.value);
    } else {
      const reason = result.reason instanceof Error ? result.reason.message : String(result.reason);
      warnings.push(`${id} schedule failed: ${reason}`);
    }
  });
  return { events: dedupe(events), warnings };
}
