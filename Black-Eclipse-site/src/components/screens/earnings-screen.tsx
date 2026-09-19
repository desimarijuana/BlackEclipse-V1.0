'use client';

// ── EarningsScreen — full-page earnings calendar ─────────────────────────────
// The full-page counterpart to the Command Center `earnings-calendar` widget.
// Both render the same `EarningsCalendar` from `./earnings-calendar`; this is
// the roomy layout with the standard page header used across the app.

import { CalendarClock } from 'lucide-react';
import { EarningsCalendar } from './earnings-calendar';

export function EarningsScreen() {
  return (
    <div className="animate-fade-in-up w-full h-full flex flex-col px-4 md:px-8 py-8">
      <div className="mb-6 flex items-center gap-2 border-b border-border/10 pb-3">
        <div className="flex h-14 w-14 shrink-0 items-center justify-center rounded-2xl border border-primary/25 bg-primary/15 shadow-lg shadow-primary/10">
          <CalendarClock className="text-primary" size={30} />
        </div>
        <div>
          <h1 className="font-serif text-2xl font-semibold tracking-tight text-foreground">Earnings Calendar</h1>
          <p className="text-muted-foreground text-xs mt-0.5">
            Upcoming company earnings by day — BMO/AMC session and EPS estimate. Click a row to open its chart.
          </p>
        </div>
      </div>
      <EarningsCalendar />
    </div>
  );
}
